## ProxyChains and TorSocks

ProxyChains alone cannot guarantee a new Tor exit IP on every run.

With one proxy (Tor) in the list, random_chain vs dynamic_chain makes zero difference. Rotation is controlled by Tor, not ProxyChains.

### Prerequisite

Install required packages:
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

### Step 1 — Backup the config

Copy-paste:
```sh
sudo cp -a /etc/proxychains4.conf /etc/proxychains4.conf.bak.$(date +%F-%H%M%S)
```

Clear the file:
```sh
sudo truncate -s 0 /etc/proxychains4.conf
```

### Step 2 — Correct ProxyChains config

Edit:
```sh
sudo vim /etc/proxychains4.conf
```

Paste exactly this:

```sh
# proxychains4.conf — Kali + Tor (CLI-safe, no DNS leaks)

# ----------------------------
# Chain behavior
# ----------------------------
dynamic_chain
quiet_mode
# random_chain does nothing with a single proxy
# strict_chain breaks when Tor circuits rotate
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
# Local exclusions
# ----------------------------
localnet 127.0.0.0/255.0.0.0

# ----------------------------
# Proxy list (Tor)
# ----------------------------
[ProxyList]
socks5 127.0.0.1 9050
```

**Important**:

ProxyChains is now clean, quiet, and leak-safe.
It still does not rotate IPs by itself.


### Step 3 — Configure Tor for isolation (this is mandatory)

Edit Tor’s config:
```sh
sudo vim /etc/tor/torrc
```

Add this line (anywhere):
```sh
SocksPort 9050 IsolateSOCKSAuth
ControlPort 9051
CookieAuthentication 1
```

Apply changes:
```sh
sudo systemctl restart tor
```

### Step 4 — Configure torsocks for per-process isolation

Edit torsocks config:
```sh
sudo vim /etc/tor/torsocks.conf
```

Uncomment or add:
```sh
IsolatePID 1
```

### Step 5 — Use torsocks correctly (global mode)

Enable torsocks in your current shell:
```sh
. torsocks on
```
You should not see `LD_PRELOAD=""`

Verify:
```sh
torsocks show
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

Optional full cleanup:
```sh
unset LD_PRELOAD
unset TORSOCKS_CONF_FILE
unset TORSOCKS_ISOLATE
```

### Hard rotation
```sh
sudo kill -HUP $(pidof tor)
```

Also a one liner:
```sh
TORSOCKS_ISOLATE=1 torsocks curl https://api.ipify.org
```

---

### Proxy Chain
```sh
proxychains4 -q curl https://checkip.amazonaws.com
```