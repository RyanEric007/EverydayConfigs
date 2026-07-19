# main.py - Ryancito Wi-Fi Site Survey Tool
# Arduino Nano ESP32 (ESP32-S3), MicroPython 1.28.x

import gc
import machine
import network
import socket
import sys
import time
import ubinascii

# ========================== CONFIGURATION ==========================
try:
    from secret import HOME_SSID, HOME_PASSWORD, AP_SSID, AP_PASSWORD
except ImportError:
    HOME_SSID = 'CHANGE_ME'
    HOME_PASSWORD = 'CHANGE_ME'
    AP_SSID = 'Ryancito-Survey'
    AP_PASSWORD = '1337'

HTTP_PORT = 80
CONNECT_TIMEOUT_MS = 12_000
CLIENT_TIMEOUT_SECONDS = 5
AP_CHANNEL = 6
MAX_NETWORKS = 64

ORANGE_PIN = 48
RGB_RED_PIN = 46
RGB_GREEN_PIN = 0
RGB_BLUE_PIN = 45
# =================================================================

BOOT_MS = time.ticks_ms()

orange = machine.Pin(ORANGE_PIN, machine.Pin.OUT)
led_r = machine.PWM(machine.Pin(RGB_RED_PIN), freq=1000, duty=1023)
led_g = machine.PWM(machine.Pin(RGB_GREEN_PIN), freq=1000, duty=1023)
led_b = machine.PWM(machine.Pin(RGB_BLUE_PIN), freq=1000, duty=1023)

sta = network.WLAN(network.STA_IF)
ap = network.WLAN(network.AP_IF)
in_ap_mode = False

def print_exception(label, exception):
    print(label)
    sys.print_exception(exception)

def clamp_8bit(value):
    value = int(value)
    if value < 0: return 0
    if value > 255: return 255
    return value

def set_rgb(red, green, blue):
    red = clamp_8bit(red)
    green = clamp_8bit(green)
    blue = clamp_8bit(blue)
    led_r.duty(1023 - (red * 1023 // 255))
    led_g.duty(1023 - (green * 1023 // 255))
    led_b.duty(1023 - (blue * 1023 // 255))

def led_off():
    set_rgb(0, 0, 0)

def orange_on():
    orange.value(1)

def orange_off():
    orange.value(0)

def rainbow_scan(duration=1.5):
    start = time.ticks_ms()
    hue = 0
    while time.ticks_diff(time.ticks_ms(), start) < duration * 1000:
        h = hue % 360
        if h < 60:
            r, g, b = 255, int(255 * h / 60), 0
        elif h < 120:
            r, g, b = int(255 * (120 - h) / 60), 255, 0
        elif h < 180:
            r, g, b = 0, 255, int(255 * (h - 120) / 60)
        elif h < 240:
            r, g, b = 0, int(255 * (240 - h) / 60), 255
        elif h < 300:
            r, g, b = int(255 * (h - 240) / 60), 0, 255
        else:
            r, g, b = 255, 0, int(255 * (360 - h) / 60)
        set_rgb(r // 2, g // 2, b // 2)
        hue += 12
        time.sleep_ms(25)
    led_off()

def html_escape(value):
    return (str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))

def format_mac(raw_mac):
    if not raw_mac:
        return "Unavailable"
    value = ubinascii.hexlify(raw_mac).decode()
    return ":".join(value[i:i+2] for i in range(0, len(value), 2))

def format_bytes(num):
    num = int(num)
    if num < 1024:
        return "{} B".format(num)
    elif num < 1024 * 1024:
        return "{:.1f} KB".format(num / 1024)
    else:
        return "{:.2f} MB".format(num / (1024 * 1024))

def get_config(interface, *names):
    for name in names:
        try:
            return interface.config(name)
        except Exception:
            pass
    return None

def get_network_constant(name):
    for owner in (sta, ap, network.WLAN, network):
        try:
            return getattr(owner, name)
        except (AttributeError, TypeError):
            pass
    return None

def build_security_map():
    security_map = {0: "Open", 1: "WEP", 2: "WPA", 3: "WPA2", 4: "WPA/WPA2"}
    known = (
        ("SEC_OPEN", "Open"), ("SEC_WEP", "WEP"), ("SEC_WPA", "WPA"),
        ("SEC_WPA2", "WPA2"), ("SEC_WPA_WPA2", "WPA/WPA2"),
        ("SEC_WPA3", "WPA3"), ("SEC_WPA2_WPA3", "WPA2/WPA3"),
    )
    for const, name in known:
        val = get_network_constant(const)
        if val is not None:
            security_map[val] = name
    return security_map

SECURITY_MAP = build_security_map()

def get_security(authmode):
    return SECURITY_MAP.get(authmode, "Unknown ({})".format(authmode))

def signal_bar(rssi):
    if rssi >= -45: return "█████"
    if rssi >= -55: return "████ "
    if rssi >= -65: return "███  "
    if rssi >= -75: return "██   "
    if rssi >= -85: return "█    "
    return "     "

def reset_wifi():
    for iface in (sta, ap):
        try: iface.active(False)
        except: pass
    time.sleep_ms(250)
    sta.active(True)

def connect_to_home():
    if not HOME_SSID or HOME_SSID == "CHANGE_ME":
        return False
    print("Connecting to home Wi-Fi...")
    set_rgb(0, 0, 80)
    try:
        sta.config(reconnects=3)
    except: pass
    try:
        sta.connect(HOME_SSID, HOME_PASSWORD)
    except Exception as e:
        print_exception("Connect failed:", e)
        led_off()
        return False

    deadline = time.ticks_add(time.ticks_ms(), CONNECT_TIMEOUT_MS)
    blink = False
    while not sta.isconnected() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        blink = not blink
        orange.value(1 if blink else 0)
        time.sleep_ms(200)

    orange_off()
    led_off()

    if sta.isconnected():
        print("Connected:", sta.ifconfig()[0])
        orange_on()
        return True
    return False

def start_survey_ap():
    print("Starting AP mode...")
    try: sta.disconnect()
    except: pass
    try: sta.config(reconnects=0)
    except: pass
    sta.active(True)
    ap.active(True)
    try:
        ap.config(ssid=AP_SSID, password=AP_PASSWORD, channel=AP_CHANNEL)
    except:
        ap.config(ssid=AP_SSID, key=AP_PASSWORD, channel=AP_CHANNEL)
    orange_on()
    print("AP started:", AP_SSID, ap.ifconfig()[0])

def configure_wifi():
    global in_ap_mode
    reset_wifi()
    if connect_to_home():
        in_ap_mode = False
        try: ap.active(False)
        except: pass
    else:
        start_survey_ap()
        in_ap_mode = True

def active_interface():
    return ap if in_ap_mode else sta

def scan_networks():
    rainbow_scan(1.5)
    gc.collect()

    try:
        raw = sta.scan()
    except Exception as e:
        print_exception("Scan failed:", e)
        return [], str(e)

    networks = []
    for r in raw:
        try:
            raw_ssid = r[0]
            bssid = r[1]
            channel = int(r[2])
            rssi = int(r[3])
            authmode = r[4] if len(r) > 4 else -1
            hidden = bool(r[5]) if len(r) > 5 else False
            if not raw_ssid:
                hidden = True
            try:
                ssid = raw_ssid.decode("utf-8", "ignore")
            except:
                ssid = str(raw_ssid)
            if not ssid:
                ssid = "Hidden"
            networks.append({
                "ssid": ssid,
                "bssid": format_mac(bssid),
                "channel": channel,
                "rssi": rssi,
                "security": get_security(authmode),
                "hidden": hidden,
            })
        except Exception as e:
            print_exception("Bad scan result:", e)

    networks.sort(key=lambda x: x["rssi"], reverse=True)
    return networks[:MAX_NETWORKS], None

def get_device_status():
    iface = active_interface()
    try: ip = iface.ifconfig()[0]
    except: ip = "Unavailable"
    try: mac = format_mac(iface.config("mac"))
    except: mac = "Unavailable"
    channel = get_config(iface, "channel") or "N/A"

    if in_ap_mode:
        mode = "AP Mode (Survey)"
        ssid = AP_SSID
        rssi = "N/A"
    else:
        mode = "Station Mode"
        ssid = get_config(sta, "ssid", "essid") or HOME_SSID
        try: rssi = "{} dBm".format(sta.status("rssi"))
        except: rssi = "N/A"

    try:
        fw = "MP " + ".".join(map(str, sys.implementation.version[:3]))
    except:
        fw = "MicroPython"

    return {
        "mode": mode,
        "ssid": ssid,
        "mac": mac,
        "ip": ip,
        "rssi": rssi,
        "channel": channel,
        "board": "Nano ESP32",
        "firmware": fw,
        "heap": format_bytes(gc.mem_free()),
    }

def build_congestion_rows(networks):
    counts = {}
    for n in networks:
        counts[n["channel"]] = counts.get(n["channel"], 0) + 1
    rows = []
    for ch in sorted(counts):
        bar = "█" * min(counts[ch], 12)
        rows.append("<tr><td>{}</td><td>{}</td><td class='bar'>{}</td></tr>".format(ch, counts[ch], bar))
    if not rows:
        rows.append("<tr><td colspan='3' class='center'>No data</td></tr>")
    return "".join(rows)

def build_network_rows(networks):
    rows = []
    for n in networks:
        note = " <span class='muted'>(hidden)</span>" if n["hidden"] else ""
        rows.append(
            "<tr><td>{}{}</td><td>{}</td><td class='bar'>{}</td><td>{}</td><td>{}</td><td class='small'>{}</td></tr>".format(
                html_escape(n["ssid"]), note, n["rssi"],
                html_escape(signal_bar(n["rssi"])),
                n["channel"], html_escape(n["security"]),
                html_escape(n["bssid"])
            )
        )
    if not rows:
        rows.append("<tr><td colspan='6' class='center'>No networks found</td></tr>")
    return "".join(rows)

def build_html(networks, scan_error=None):
    s = get_device_status()
    congestion = build_congestion_rows(networks)
    net_rows = build_network_rows(networks)

    error_html = ""
    if scan_error:
        error_html = "<div class='error'><strong>Scan error:</strong> {}</div>".format(html_escape(scan_error))

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ryancito Site Survey</title>
<style>
body{{background:#05070c;color:#00fff7;font-family:monospace;margin:0}}
.header{{text-align:center;padding:16px;border-bottom:1px solid rgba(0,255,247,.2);font-size:1.35em;font-weight:bold;text-shadow:0 0 10px #00fff7}}
.container{{max-width:980px;margin:0 auto;padding:16px 12px 40px}}
.card{{background:#0a0e16;border:1px solid rgba(0,255,247,.3);border-radius:12px;padding:16px;margin-bottom:16px}}
h2{{color:#b967ff;font-size:1.1em;margin:0 0 14px}}
.status-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}}
.status-col strong{{color:#b967ff;display:block;font-size:.78em;margin-bottom:2px}}
.status-col div{{margin-bottom:10px;font-size:.95em}}
table{{width:100%;border-collapse:collapse;font-size:.88em}}
th,td{{padding:8px 6px;border-bottom:1px solid rgba(0,255,247,.1);text-align:left}}
th{{color:#b967ff;background:rgba(185,103,255,.1)}}
.bar{{white-space:pre;letter-spacing:-1px}}
.small{{font-size:.82em}}
.center{{text-align:center;padding:18px}}
.muted{{opacity:.55;font-size:.8em}}
.error{{border:1px solid #ff6b6b;color:#ffaaaa;padding:10px;border-radius:8px;margin-bottom:16px}}
.btn-row{{text-align:center;margin-top:10px}}
.btn{{display:inline-block;text-decoration:none;color:#00fff7;border:2px solid #00fff7;padding:10px 22px;border-radius:8px;margin:5px;background:transparent;font-family:inherit;font-size:1em;cursor:pointer}}
.footer{{text-align:center;padding:14px;font-size:.8em;opacity:.45}}
@media(max-width:600px){{.status-grid{{grid-template-columns:1fr}}}}
@media print{{
body{{background:white!important;color:black!important}}
.header{{color:black!important;text-shadow:none!important;border-color:#444!important}}
.card{{background:white!important;border:1px solid #666!important;color:black!important}}
h2,.status-col strong{{color:#333!important}}
th{{background:#eee!important;color:black!important}}
td,.bar{{color:black!important}}
.btn{{display:none!important}}
.footer{{color:#555!important;opacity:1!important}}
}}
</style>
</head>
<body>
<div class="header">Ryancito Site Survey</div>
<div class="container">
{error_html}

<div class="card">
<h2>Status</h2>
<div class="status-grid">
  <div class="status-col">
    <div><strong>Mode</strong>{mode}</div>
    <div><strong>SSID</strong>{ssid}</div>
    <div><strong>MAC</strong>{mac}</div>
  </div>
  <div class="status-col">
    <div><strong>IP</strong>{ip}</div>
    <div><strong>Signal</strong>{rssi}</div>
    <div><strong>Channel</strong>{channel}</div>
  </div>
  <div class="status-col">
    <div><strong>Board</strong>{board}</div>
    <div><strong>Firmware</strong>{firmware}</div>
    <div><strong>Free Heap</strong>{heap}</div>
  </div>
</div>
</div>

<div class="card">
<h2>Channel Congestion</h2>
<table>
<thead><tr><th>Channel</th><th>Networks</th><th>Load</th></tr></thead>
<tbody>{congestion}</tbody>
</table>
</div>

<div class="card">
<h2>Nearby Networks ({count} found)</h2>
<div style="overflow-x:auto">
<table>
<thead>
<tr><th>SSID</th><th>RSSI</th><th>Signal</th><th>Ch</th><th>Security</th><th>BSSID</th></tr>
</thead>
<tbody>{net_rows}</tbody>
</table>
</div>
</div>

<div class="btn-row">
<a class="btn" href="/">Rescan</a>
<button class="btn" onclick="window.print()">Print</button>
</div>
</div>
<div class="footer">Ryancito Wi-Fi Site Survey Tool</div>
</body>
</html>""".format(
        error_html=error_html,
        mode=html_escape(s["mode"]),
        ssid=html_escape(s["ssid"]),
        mac=html_escape(s["mac"]),
        ip=html_escape(s["ip"]),
        rssi=html_escape(s["rssi"]),
        channel=html_escape(s["channel"]),
        board=html_escape(s["board"]),
        firmware=html_escape(s["firmware"]),
        heap=html_escape(s["heap"]),
        congestion=congestion,
        count=len(networks),
        net_rows=net_rows,
    )

def send_response(client, status, content_type, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(
        status, content_type, len(body))
    client.sendall(headers.encode())
    if body:
        client.sendall(body)

def read_request(client):
    data = client.recv(1024)
    if not data:
        return None, None
    line = data.split(b"\r\n", 1)[0]
    parts = line.split()
    if len(parts) < 2:
        return None, None
    try:
        return parts[0].decode(), parts[1].decode().split("?", 1)[0]
    except:
        return None, None

def handle_client(client, addr):
    try:
        client.settimeout(CLIENT_TIMEOUT_SECONDS)
    except Exception:
        pass

    try:
        method, path = read_request(client)
    except OSError as e:
        # Quietly ignore common client disconnect / timeout errors
        if e.args and e.args[0] in (110, 116, 104, 11, 128):
            return
        print("Request error from", addr, "→", e)
        return
    except Exception as e:
        print("Request error from", addr, "→", e)
        return

    if method != "GET":
        send_response(client, "405 Method Not Allowed", "text/plain", "Only GET\n")
        return

    if path != "/favicon.ico":
        print("GET", path, "from", addr)

    if path == "/favicon.ico":
        send_response(client, "204 No Content", "image/x-icon", b"")
        return

    if path != "/":
        send_response(client, "404 Not Found", "text/plain", "Not found\n")
        return

    nets, err = scan_networks()
    html = build_html(nets, err)
    send_response(client, "200 OK", "text/html; charset=utf-8", html)

def serve_forever():
    while True:
        server = None
        try:
            addr = socket.getaddrinfo("0.0.0.0", HTTP_PORT)[0][-1]
            server = socket.socket()
            try:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except: pass
            server.bind(addr)
            server.listen(3)
            ip = active_interface().ifconfig()[0]
            print("Server ready → http://{}:{}/".format(ip, HTTP_PORT))

            while True:
                client = None
                try:
                    client, remote = server.accept()
                    handle_client(client, remote)
                except KeyboardInterrupt:
                    raise
                except OSError as e:
                    if not (e.args and e.args[0] in (110, 116, 104, 11, 128)):
                        print_exception("Request error:", e)
                except Exception as e:
                    print_exception("Request error:", e)
                finally:
                    if client:
                        try: client.close()
                        except: pass
                    gc.collect()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print_exception("Server error:", e)
            time.sleep_ms(1000)
        finally:
            if server:
                try: server.close()
                except: pass

def main():
    orange_off()
    led_off()
    configure_wifi()
    serve_forever()

try:
    main()
except KeyboardInterrupt:
    print("\nStopped.")
except Exception as e:
    print_exception("Fatal:", e)
finally:
    led_off()
    orange_off()