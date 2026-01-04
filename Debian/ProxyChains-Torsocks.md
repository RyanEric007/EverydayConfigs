## ProxyChains and TorSocks

ProxyChains alone cannot guarantee a new Tor exit IP on every run.
With one proxy (Tor) in the list, random_chain vs dynamic_chain makes zero difference. Rotation is controlled by Tor, not ProxyChains.

### Prerequisite

Install:

```sh
sudo apt install -y tor proxychains4 torsocks curl
```

Enable -> Start -> Enable -> Info:

```sh
sudo systemctl start tor
sudo systemctl enable tor
sudo systemctl status tor --no-pager
sudo ss -lntp | grep -E '(:9050|tor)'
```

### Step 1 — Pack it up (backup the config)

Copy-paste:

```sh
sudo cp -a /etc/proxychains4.conf /etc/proxychains4.conf.bak.$(date +%F-%H%M%S)
```

Truncate with following command:

```sh
sudo truncate -s 0 /etc/proxychains4.conf
```

### Step 2 — The correct ProxyChains config (clean, tight, predictable)

Copy everything below and paste it into `/etc/proxychains4.conf`:

```sh
sudo vim /etc/proxychains4.conf
```

Copy-paste:

```sh
# proxychains4.conf — Kali + Tor (CLI-safe, no DNS leaks)

# ----------------------------
# Chain behavior
# ----------------------------
dynamic_chain
quiet_mode
# random_chain does NOTHING with a single proxy
# strict_chain breaks when Tor rotates
# dynamic_chain is correct here

# ----------------------------
# DNS handling (critical)
# ----------------------------
proxy_dns
remote_dns_subnet 224

# ----------------------------
# Timeouts
# ----------------------------
tcp_read_time_out 15000
tcp_connect_time_out 8000

# ----------------------------
# Local exclusions (DO NOT proxy your LAN)
# ----------------------------
localnet 127.0.0.0/255.0.0.0

# ----------------------------
# Proxy list (Tor)
# ----------------------------
[ProxyList]
socks5  127.0.0.1 9050
```

### Step 3 — How to ACTUALLY rotate IPs every use (the part people get wrong)

Reality:
- Tor rotates circuits, not ProxyChains
- New process ≠ new circuit
- You must force isolation

#### Correct tool for this job: torsocks

Run this once (Tor already running):

Enable “global” torsocks for commands you run in this shell:

```sh
. torsocks on
```

Try commands:

```sh
torsocks curl -s https://check.torproject.org/ ; echo
```
```sh
torsocks curl -s https://checkip.amazonaws.com ; echo
```
```sh
proxychains -q curl -s https://checkip.amazonaws.com ; echo
```

Turn off when done:

```sh
. torsocks off
```

### Proxy Chain
```sh
proxychains4 -q curl https://checkip.amazonaws.com
```

### Hard rotation
```sh
sudo kill -HUP $(pidof tor)
```