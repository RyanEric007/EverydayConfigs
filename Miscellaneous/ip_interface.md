# Enable IPv4 forwarding + ensure IPv4 networking via Netplan
## Ubuntu / systemd-networkd (runbook)

### 1) Identify the network interface
```sh
ip link
```

### 2) Enable IPv4 forwarding immediately (runtime)
```sh
sudo sysctl -w net.ipv4.ip_forward=1
```

### 3) Persist IPv4 forwarding across reboots (preferred: /etc/sysctl.d)
```sh
echo "net.ipv4.ip_forward = 1" | sudo tee /etc/sysctl.d/99-ip-forward.conf >/dev/null
sudo chown root:root /etc/sysctl.d/99-ip-forward.conf
sudo chmod 644 /etc/sysctl.d/99-ip-forward.conf
```

### 3a) Optional legacy file (NOT required)
##### Keep empty so `sysctl -p` does not warn.
##### /etc/sysctl.conf is intentionally unused; we standardize on /etc/sysctl.d/*
```sh
sudo touch /etc/sysctl.conf
sudo chown root:root /etc/sysctl.conf
sudo chmod 644 /etc/sysctl.conf
```

### 4) Reload all sysctl configs (preferred method)

```sh
sudo sysctl --system
```

### 5) Configure Netplan for IPv4
#### Edit your existing netplan file and ADD:
####   dhcp4: true
```sh
sudo nano /etc/netplan/00-installer-config.yaml
```

#### Example:
```sh
# ---- Netplan example (for reference only — do not paste blindly) ----
# network:
#   version: 2
#   ethernets:
#     ens33:
#       match:
#         macaddress: 00:0c:29:23:a4:3b
#       set-name: ens33
#       dhcp4: true
#
#   # Static IPv4 example (commented out)
#   # dhcp4: false
#   # addresses:
#   #   - 192.168.1.10/24
#   # gateway4: 192.168.1.1
#   # nameservers:
#   #   addresses:
#   #     - 1.1.1.1
#   #     - 8.8.8.8
# -------------------------------------------------------------------
```

### 6) Apply Netplan
```sh
sudo netplan generate
sudo netplan apply
```

### 7) Validate
```sh
ip -4 a
ip route
sysctl net.ipv4.ip_forward
networkctl status
```