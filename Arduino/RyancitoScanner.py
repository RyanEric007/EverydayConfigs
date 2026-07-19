# main.py - Ryancito WiFi Site Survey Tool
import network
import socket
import time
import machine
import ubinascii

# ================== CONFIGURATION ==================
HOME_SSID = 'Your_SSID'
HOME_PASSWORD = 'Your_Password'
AP_SSID = 'Ryancito-Survey'
AP_PASSWORD = '1337'
# ===================================================

# LEDs
orange = machine.Pin(48, machine.Pin.OUT)
led_r = machine.PWM(machine.Pin(46), freq=1000, duty=0)
led_g = machine.PWM(machine.Pin(0),  freq=1000, duty=0)
led_b = machine.PWM(machine.Pin(45), freq=1000, duty=0)

def set_rgb(r, g, b):
    led_r.duty(1023 - int(r * 4))
    led_g.duty(1023 - int(g * 4))
    led_b.duty(1023 - int(b * 4))

def led_off():
    set_rgb(0, 0, 0)

def orange_on():
    orange.value(1)

def orange_off():
    orange.value(0)

def rainbow_scan(duration=1.4):
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
        hue += 10
        time.sleep_ms(25)
    led_off()

def get_security(authmode):
    modes = {
        0: "Open", 1: "WEP", 2: "WPA", 3: "WPA2",
        4: "WPA/WPA2", 5: "WPA2-Ent", 6: "WPA3", 7: "WPA2/WPA3"
    }
    return modes.get(authmode, "Unknown")

def signal_bar(rssi):
    if rssi >= -45: return "█████"
    if rssi >= -55: return "████ "
    if rssi >= -65: return "███  "
    if rssi >= -75: return "██   "
    if rssi >= -85: return "█    "
    return "     "

# ====================== Smart WiFi Connection ======================
in_ap_mode = False

print("Trying home WiFi...")
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(HOME_SSID, HOME_PASSWORD)

start = time.time()
while not wlan.isconnected():
    if time.time() - start > 12:
        break
    orange_on()
    time.sleep(0.3)
    orange_off()
    time.sleep(0.3)

if wlan.isconnected():
    print("Connected to home WiFi:", wlan.ifconfig()[0])
    orange_on()
    in_ap_mode = False
else:
    print("Home WiFi not found → Starting AP mode")
    wlan.active(False)
    time.sleep(0.5)
    wlan = network.WLAN(network.AP_IF)
    wlan.active(True)
    wlan.config(ssid=AP_SSID, password=AP_PASSWORD, channel=6)
    print("AP started:", AP_SSID, "| IP:", wlan.ifconfig()[0])
    in_ap_mode = True

# ====================== Web Server ======================
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]

while True:
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(addr)
        s.listen(3)
        print("Server ready → http://" + wlan.ifconfig()[0])

        while True:
            if in_ap_mode:
                orange_on()
                time.sleep(0.15)
                orange_off()
                time.sleep(0.15)

            cl, _ = s.accept()
            try:
                cl.recv(1024)

                rainbow_scan(1.3)

                ip = wlan.ifconfig()[0]
                mac = ubinascii.hexlify(wlan.config('mac')).decode()
                my_rssi = wlan.status('rssi') if not in_ap_mode else "N/A"
                my_ch = wlan.config('channel')
                my_ssid = wlan.config('essid') if not in_ap_mode else AP_SSID
                mode_text = "AP Mode (Survey)" if in_ap_mode else "Station Mode (Home WiFi)"

                try:
                    nets = wlan.scan()
                    networks = sorted(nets, key=lambda x: x[3], reverse=True)
                except:
                    networks = []

                # ----- Channel Congestion Table -----
                channel_count = {}
                for net in networks:
                    ch = net[2]
                    channel_count[ch] = channel_count.get(ch, 0) + 1

                congestion_rows = ""
                for ch in sorted(channel_count.keys()):
                    count = channel_count[ch]
                    bar = "█" * min(count, 12)
                    congestion_rows += "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(ch, count, bar)

                if not congestion_rows:
                    congestion_rows = "<tr><td colspan='3' style='text-align:center'>No data</td></tr>"

                # ----- Network Rows -----
                rows = ""
                for net in networks:
                    try:
                        ssid = net[0].decode("utf-8", "ignore") or "Hidden"
                    except:
                        ssid = "Hidden"
                    rssi = net[3]
                    ch = net[2]
                    bssid = ubinascii.hexlify(net[1]).decode()
                    security = get_security(net[4]) if len(net) > 4 else "?"
                    bar = signal_bar(rssi)

                    rows += "<tr>"
                    rows += "<td>{}</td>".format(ssid)
                    rows += "<td>{}</td>".format(rssi)
                    rows += "<td style='letter-spacing:-1px'>{}</td>".format(bar)
                    rows += "<td>{}</td>".format(ch)
                    rows += "<td>{}</td>".format(security)
                    rows += "<td style='font-size:0.82em'>{}</td>".format(bssid)
                    rows += "</tr>"

                if not rows:
                    rows = "<tr><td colspan='6' style='text-align:center;padding:18px'>No networks found</td></tr>"

                # ----- Build HTML -----
                html = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Ryancito Site Survey</title>
<style>
body{background:#05070c;color:#00fff7;font-family:monospace;margin:0}
.header{text-align:center;padding:16px;border-bottom:1px solid rgba(0,255,247,0.2);font-size:1.35em;font-weight:bold;text-shadow:0 0 10px #00fff7}
.container{max-width:980px;margin:0 auto;padding:16px 12px 40px}
.card{background:rgba(10,14,22,0.92);border:1px solid rgba(0,255,247,0.3);border-radius:12px;padding:16px;margin-bottom:16px}
h2{color:#b967ff;font-size:1.1em;margin:0 0 12px 0}
.info{display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:0.95em}
.info strong{color:#b967ff;display:block;font-size:0.8em}
.full{grid-column:1/-1}
table{width:100%;border-collapse:collapse;font-size:0.88em}
th,td{padding:8px 6px;border-bottom:1px solid rgba(0,255,247,0.1);text-align:left}
th{color:#b967ff;background:rgba(185,103,255,0.1)}
.btn-row{text-align:center;margin-top:12px}
.btn{background:transparent;color:#00fff7;border:2px solid #00fff7;padding:10px 20px;border-radius:8px;font-family:inherit;margin:4px}
.footer{text-align:center;padding:14px;font-size:0.8em;color:rgba(0,255,247,0.45)}
@media(max-width:500px){.info{grid-template-columns:1fr}}
@media print{
  body{background:white;color:black}
  .header,.card,h2,th,td,.footer{color:black !important;text-shadow:none !important;background:white !important;border-color:#666 !important}
  .btn{display:none}
  th{background:#eee !important}
}
</style>
</head>
<body>
<div class="header">Ryancito Site Survey</div>
<div class="container">

<div class="card">
<h2>Status</h2>
<div class="info">
<div><strong>Mode</strong>""" + mode_text + """</div>
<div><strong>IP</strong>""" + str(ip) + """</div>
<div><strong>MAC</strong>""" + str(mac) + """</div>
<div><strong>Signal</strong>""" + str(my_rssi) + """ dBm</div>
<div class="full"><strong>SSID</strong>""" + str(my_ssid) + """</div>
</div>
</div>

<div class="card">
<h2>Channel Congestion</h2>
<table>
<thead><tr><th>Channel</th><th>Networks</th><th>Load</th></tr></thead>
<tbody>""" + congestion_rows + """</tbody>
</table>
</div>

<div class="card">
<h2>Nearby Networks (""" + str(len(networks)) + """ found)</h2>
<div style="overflow-x:auto">
<table>
<thead>
<tr>
<th>SSID</th>
<th>RSSI</th>
<th>Signal</th>
<th>Ch</th>
<th>Security</th>
<th>BSSID</th>
</tr>
</thead>
<tbody>""" + rows + """</tbody>
</table>
</div>
</div>

<div class="btn-row">
<button class="btn" onclick="location.reload()">Rescan</button>
<button class="btn" onclick="window.print()">Print</button>
</div>

</div>
<div class="footer">Ryancito WiFi Site Survey Tool</div>
</body>
</html>"""

                cl.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n")
                cl.send(html)

            except Exception as e:
                print("Request error:", e)
            finally:
                cl.close()

    except Exception as e:
        print("Server error:", e)
        time.sleep(1)
    finally:
        try:
            s.close()
        except:
            pass