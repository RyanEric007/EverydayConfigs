# main.py - Ryancito WiFi Scanner
import network
import socket
import time
import machine
import ubinascii

# ================== CONFIGURATION ==================
USE_AP_MODE = False
SSID = 'pick_a_ssid'
PASSWORD = 'choose-a-password'
AP_SSID = 'Ryancito-Scanner'
AP_PASSWORD = '1234'
# ===================================================

# RGB LED pins (Active LOW)
led_r = machine.PWM(machine.Pin(46), freq=1000, duty=0)
led_g = machine.PWM(machine.Pin(0),  freq=1000, duty=0)
led_b = machine.PWM(machine.Pin(45), freq=1000, duty=0)

def set_rgb(r, g, b):
    """r, g, b from 0-255. Active LOW so we invert."""
    led_r.duty(1023 - int(r * 4))   # 0-1023 range
    led_g.duty(1023 - int(g * 4))
    led_b.duty(1023 - int(b * 4))

def led_off():
    set_rgb(0, 0, 0)

def blink_led(times=3, delay=0.2):
    for _ in range(times):
        set_rgb(0, 80, 255)   # Cyan
        time.sleep(delay)
        led_off()
        time.sleep(delay)

def rainbow_scan(duration=1.8):
    """Smooth rainbow while scanning"""
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

        # Dim it a bit
        set_rgb(r // 2, g // 2, b // 2)
        hue += 10
        time.sleep_ms(25)

    led_off()

# ====================== WiFi Setup ======================
if USE_AP_MODE:
    wlan = network.WLAN(network.AP_IF)
    wlan.active(True)
    wlan.ifconfig(('10.11.12.1', '255.255.255.0', '10.11.12.1', '10.11.12.1'))
    wlan.config(ssid=AP_SSID, password=AP_PASSWORD, channel=6)
    print("🔥 AP Mode Started - SSID:", AP_SSID)
    print("IP:", wlan.ifconfig()[0])
    blink_led(5, 0.1)
else:
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(0.5)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    print("Connecting to WiFi...")
    
    start_time = time.time()
    while not wlan.isconnected():
        if time.time() - start_time > 30:
            print("❌ Connection timeout!")
            machine.reset()
        blink_led(1, 0.3)
    print("✅ Connected! IP:", wlan.ifconfig()[0])
    blink_led(3, 0.15)

# ====================== Web Server ======================
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]

while True:
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(addr)
        s.listen(5)
        print("🌐 Server running on http://" + wlan.ifconfig()[0])

        while True:
            cl, addr_client = s.accept()
            try:
                request = cl.recv(1024).decode('utf-8', 'ignore')

                # Rainbow while scanning
                rainbow_scan(1.7)

                ip = wlan.ifconfig()[0]
                mac = ubinascii.hexlify(wlan.config('mac')).decode()
                rssi = wlan.status('rssi') if not USE_AP_MODE else "N/A (AP)"
                channel = wlan.config('channel')
                current_ssid = wlan.config('essid') if not USE_AP_MODE else AP_SSID

                try:
                    nets = wlan.scan()
                    networks = sorted(nets, key=lambda x: x[3], reverse=True)
                except:
                    networks = []

                rows = ""
                for net in networks:
                    try:
                        ssid = net[0].decode('utf-8', 'ignore')
                    except:
                        ssid = "Hidden"
                    signal = net[3]
                    ch = net[2]
                    bssid = ubinascii.hexlify(net[1]).decode()
                    rows += f"<tr><td>{ssid}</td><td>{signal} dBm</td><td>{ch}</td><td>{bssid}</td></tr>"

                html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Ryancito WiFi Scanner</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #05070c;
            color: #00fff7;
            font-family: 'Courier New', monospace;
            min-height: 100vh;
        }}
        .site-header {{
            display: flex;
            justify-content: center;
            padding: 18px 22px;
            border-bottom: 1px solid rgba(0, 255, 247, 0.15);
        }}
        .brand {{
            font-size: 1.5em;
            font-weight: 700;
            letter-spacing: 1.5px;
            color: #00fff7;
            text-shadow: 0 0 12px #00fff7;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 25px 16px 40px;
        }}
        .card {{
            background: rgba(10, 14, 22, 0.85);
            border: 1px solid rgba(0, 255, 247, 0.35);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 22px;
        }}
        .connection-card {{ text-align: center; }}
        .connection-card h2 {{
            color: #b967ff;
            font-size: 1.25em;
            margin-bottom: 22px;
        }}
        .connection-info {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px 24px;
            max-width: 440px;
            margin: 0 auto;
            text-align: left;
        }}
        .connection-info p {{ margin: 0; font-size: 1.05em; }}
        .connection-info strong {{
            color: #b967ff;
            display: block;
            font-size: 0.85em;
            margin-bottom: 3px;
        }}
        .ssid-full {{ grid-column: 1 / -1; }}
        h2.section-title {{
            color: #b967ff;
            font-size: 1.15em;
            margin-bottom: 16px;
        }}
        .table-wrapper {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.95em; }}
        th, td {{
            padding: 11px 10px;
            border-bottom: 1px solid rgba(0, 255, 247, 0.12);
            text-align: left;
        }}
        th {{
            color: #b967ff;
            background: rgba(185, 103, 255, 0.08);
        }}
        .btn-row {{
            display: flex;
            justify-content: center;
            gap: 14px;
            flex-wrap: wrap;
            margin-top: 8px;
        }}
        .btn {{
            background: transparent;
            color: #00fff7;
            border: 2px solid #00fff7;
            padding: 12px 26px;
            border-radius: 10px;
            font-family: inherit;
            font-size: 1em;
            cursor: pointer;
            min-width: 150px;
        }}
        .btn:hover {{
            background: #00fff7;
            color: #05070c;
        }}
        .site-footer {{
            text-align: center;
            padding: 20px;
            font-size: 0.85em;
            color: rgba(0, 255, 247, 0.5);
        }}
        @media (max-width: 520px) {{
            .connection-info {{
                grid-template-columns: 1fr;
                text-align: center;
            }}
            .connection-info strong {{ display: inline; margin-right: 6px; }}
        }}
        @media print {{
            body {{ background: white; color: black; }}
            .card {{ background: white; border: 1px solid #666; color: black; }}
            th {{ background: #eee; color: black; }}
            .btn {{ display: none; }}
            .brand, h2 {{ color: black; text-shadow: none; }}
        }}
    </style>
</head>
<body>
    <header class="site-header">
        <div class="brand">Ryancito Scanner</div>
    </header>
    <div class="container">
        <div class="card connection-card">
            <h2>Your Connection</h2>
            <div class="connection-info">
                <p><strong>IP</strong>{ip}</p>
                <p><strong>MAC</strong>{mac}</p>
                <p><strong>Signal</strong>{rssi} dBm</p>
                <p><strong>Channel</strong>{channel}</p>
                <p class="ssid-full"><strong>SSID</strong>{current_ssid}</p>
            </div>
        </div>
        <div class="card">
            <h2 class="section-title">Nearby Networks ({len(networks)} found)</h2>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>SSID</th><th>Signal</th><th>Ch</th><th>BSSID</th></tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>
        <div class="btn-row">
            <button class="btn" onclick="location.reload()">🔄 Refresh Scan</button>
            <button class="btn" onclick="window.print()">🖨️ Print</button>
        </div>
    </div>
    <footer class="site-footer">Ryancito WiFi Scanner</footer>
</body>
</html>"""

                cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n' + html)
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