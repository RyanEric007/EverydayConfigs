# Linux System Hardening – Ordered Runbook

This document is a **cut-and-paste operational checklist** for securing a Linux system, executed **in the correct order**.

---

## 1. System Updates & Baseline

Purpose: Eliminate known vulnerabilities immediately.

```bash
# Debian / Ubuntu
sudo apt update && sudo apt -y upgrade
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades
```

```bash
# RHEL / Alma / Rocky
sudo dnf -y update
sudo dnf install -y dnf-automatic
sudo systemctl enable --now dnf-automatic.timer
```

---

## 2. Lock Down Root & Enforce sudo

Purpose: Accountability and privilege control.

```bash
sudo useradd -m -s /bin/bash adminuser
sudo passwd adminuser
sudo usermod -aG sudo adminuser      # Debian/Ubuntu
sudo usermod -aG wheel adminuser     # RHEL-based
sudo passwd -l root
```

---

## 3. Password Policy & Account Aging

Purpose: Stop weak credentials and brute force.

```bash
sudo apt install -y libpam-pwquality || sudo dnf install -y libpwquality
sudo nano /etc/security/pwquality.conf
```

```ini
minlen = 14
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
```

```bash
sudo chage -M 90 -W 14 adminuser
```

---

## 4. PAM Lockout Protection

Purpose: Block automated login attacks.

```ini
# /etc/security/faillock.conf
deny = 5
unlock_time = 1800
fail_interval = 900
```

---

## 5. Home Directory Permissions

Purpose: Prevent user data leakage.

```bash
sudo chmod 700 /home/*
```

---

## 6. SSH Hardening

Purpose: Secure the primary remote entry point.

```bash
sudo nano /etc/ssh/sshd_config
```

```ini
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 60
X11Forwarding no
AllowTcpForwarding no
LogLevel VERBOSE
```

```bash
sudo systemctl restart sshd
```

---

## 7. Firewall (Default Deny)

Purpose: Reduce network attack surface.

### Ubuntu (UFW)
```bash
sudo ufw default deny incoming
sudo ufw allow ssh
sudo ufw enable
```

### RHEL / Alma (firewalld)
```bash
sudo firewall-cmd --add-service=ssh --permanent
sudo firewall-cmd --reload
```

---

## 8. Disk Encryption (LUKS)

Purpose: Protect data at rest.

```bash
sudo cryptsetup luksFormat /dev/sdb1
sudo cryptsetup luksOpen /dev/sdb1 secure_data
sudo mkfs.ext4 /dev/mapper/secure_data
sudo mount /dev/mapper/secure_data /mnt/secure
```

---

## 9. File & Permission Hardening

Purpose: Prevent privilege escalation.

```bash
sudo find / -perm -4000 -type f 2>/dev/null
sudo chmod u-s /path/to/binary
sudo chattr +a /var/log/auth.log
```

---

## 10. Mandatory Access Control

Purpose: Contain compromise.

### SELinux
```bash
sudo setenforce 1
```

### AppArmor
```bash
sudo systemctl enable --now apparmor
```

---

## 11. Kernel Hardening

Purpose: Close low-level attack vectors.

```ini
# /etc/sysctl.d/99-hardening.conf
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
net.ipv4.tcp_syncookies = 1
```

```bash
sudo sysctl --system
```

---

## 12. Execution Whitelisting

Purpose: Block unauthorized binaries.

```bash
sudo dnf install -y fapolicyd
sudo systemctl enable --now fapolicyd
sudo fapolicyd-cli --update
```

---

## 13. Service Auditing

Purpose: Kill unnecessary exposure.

```bash
systemctl list-units --type=service --state=running
sudo systemctl disable --now servicename
```

---

## 14. Logging & Auditing

Purpose: Detection and forensics.

```bash
sudo systemctl enable --now auditd
sudo auditctl -w /etc/passwd -p wa -k passwd_changes
```

---

## 15. Vulnerability Scanning

Purpose: Continuous validation.

```bash
sudo lynis audit system
sudo nmap -sS -sV -p- localhost
```

---

## Final Principle

Security is **process-driven**, not configuration-driven.
Re-audit, re-scan, and re-validate continuously.


# Script

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[*] Starting Linux hardening process..."

# -----------------------------
# Detect OS Family
# -----------------------------
if [ -f /etc/debian_version ]; then
  OS_FAMILY="debian"
elif [ -f /etc/redhat-release ]; then
  OS_FAMILY="rhel"
else
  echo "[!] Unsupported OS"
  exit 1
fi

echo "[*] Detected OS family: $OS_FAMILY"

# -----------------------------
# System Updates
# -----------------------------
echo "[*] Applying system updates..."
if [ "$OS_FAMILY" = "debian" ]; then
  apt update && apt -y upgrade
  apt install -y unattended-upgrades auditd lynis ufw
  dpkg-reconfigure -f noninteractive unattended-upgrades
else
  dnf -y update
  dnf install -y dnf-automatic audit lynis firewalld policycoreutils-python-utils
  systemctl enable --now dnf-automatic.timer
fi

# -----------------------------
# Disable Root Login
# -----------------------------
echo "[*] Locking root account..."
passwd -l root || true

# -----------------------------
# Password Policy
# -----------------------------
echo "[*] Enforcing strong password policy..."
if [ "$OS_FAMILY" = "debian" ]; then
  apt install -y libpam-pwquality
else
  dnf install -y libpwquality
fi

cat >/etc/security/pwquality.conf <<EOF
minlen = 14
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
EOF

# -----------------------------
# PAM Brute-Force Protection
# -----------------------------
echo "[*] Configuring PAM lockout..."
cat >/etc/security/faillock.conf <<EOF
deny = 5
unlock_time = 1800
fail_interval = 900
EOF

# -----------------------------
# SSH Hardening
# -----------------------------
echo "[*] Hardening SSH..."
SSHD_CONFIG="/etc/ssh/sshd_config"

cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.$(date +%F)"

sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' $SSHD_CONFIG
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' $SSHD_CONFIG
sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' $SSHD_CONFIG
sed -i 's/^#\?MaxAuthTries.*/MaxAuthTries 3/' $SSHD_CONFIG
sed -i 's/^#\?LoginGraceTime.*/LoginGraceTime 60/' $SSHD_CONFIG

grep -q "^LogLevel" $SSHD_CONFIG || echo "LogLevel VERBOSE" >> $SSHD_CONFIG

systemctl restart sshd

# -----------------------------
# Firewall
# -----------------------------
echo "[*] Configuring firewall..."
if [ "$OS_FAMILY" = "debian" ]; then
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow ssh
  ufw --force enable
else
  systemctl enable --now firewalld
  firewall-cmd --set-default-zone=public
  firewall-cmd --add-service=ssh --permanent
  firewall-cmd --reload
fi

# -----------------------------
# Kernel Hardening
# -----------------------------
echo "[*] Applying kernel hardening..."
cat >/etc/sysctl.d/99-hardening.conf <<EOF
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.tcp_syncookies = 1
EOF

sysctl --system

# -----------------------------
# SELinux / AppArmor
# -----------------------------
if [ "$OS_FAMILY" = "rhel" ]; then
  echo "[*] Enforcing SELinux..."
  setenforce 1 || true
  sed -i 's/^SELINUX=.*/SELINUX=enforcing/' /etc/selinux/config
else
  echo "[*] Enabling AppArmor..."
  systemctl enable --now apparmor
fi

# -----------------------------
# File Protection
# -----------------------------
echo "[*] Protecting logs..."
chattr +a /var/log/auth.log 2>/dev/null || true
chattr +a /var/log/secure 2>/dev/null || true

# -----------------------------
# Enable Auditing
# -----------------------------
echo "[*] Enabling auditd..."
systemctl enable --now auditd

auditctl -w /etc/passwd -p wa -k passwd_changes || true
auditctl -w /etc/shadow -p wa -k shadow_changes || true
auditctl -w /etc/sudoers -p wa -k sudoers_changes || true

# -----------------------------
# Final Scan
# -----------------------------
echo "[*] Running Lynis audit..."
lynis audit system || true

echo "[✔] Hardening complete. Review Lynis output and reboot if required."
```

```bash
chmod +x linux-harden.sh
sudo ./linux-harden.sh
```