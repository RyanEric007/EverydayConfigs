# main.py - Ryancito WiFi Scanner
import network
import socket
import time
import machine
import ubinascii

# ================== CONFIGURATION ==================
USE_AP_MODE = False                   # True = AP Mode | False = Connect to your WiFi
SSID = 'Enter_in_your_ssid'
PASSWORD = 'And password'
AP_SSID = 'Ryancito-Scanner'
AP_PASSWORD = 'DontStealMyPassword' #obvous joke :p
# ===================================================

led = machine.Pin(48, machine.Pin.OUT)

def blink_led(times=3, delay=0.2):
    for _ in range(times):
        led.on()
        time.sleep(delay)
        led.off()
        time.sleep(delay)

# ====================== WiFi Setup ======================
if USE_AP_MODE:
    wlan = network.WLAN(network.AP_IF)
    wlan.active(True)
    wlan.ifconfig(('192.168.4.1', '255.255.255.0', '192.168.4.1', '192.168.4.1'))  # IP, Mask, Gateway, DNS
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
    <meta name="color-scheme" content="dark">
    <title>Ryancito WiFi Scanner</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            background: #05070c;
            color: #00fff7;
            font-family: 'Courier New', monospace;
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }}

        /* ===== Particle / Cyber Background ===== */
        .particles {{
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background:
                radial-gradient(circle at 20% 30%, rgba(0, 255, 247, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 80% 70%, rgba(0, 255, 247, 0.06) 0%, transparent 40%);
        }}

        .particles::before {{
            content: "";
            position: absolute;
            inset: 0;
            background-image:
                radial-gradient(1.5px 1.5px at 10% 20%, #00fff7 100%, transparent),
                radial-gradient(1.5px 1.5px at 30% 65%, #00fff7 100%, transparent),
                radial-gradient(1.5px 1.5px at 50% 30%, #00fff7 100%, transparent),
                radial-gradient(1.5px 1.5px at 70% 80%, #00fff7 100%, transparent),
                radial-gradient(1.5px 1.5px at 90% 40%, #00fff7 100%, transparent),
                radial-gradient(1px 1px at 15% 80%, #fff 100%, transparent),
                radial-gradient(1px 1px at 45% 15%, #fff 100%, transparent),
                radial-gradient(1px 1px at 75% 55%, #fff 100%, transparent);
            background-size: 200% 200%;
            animation: particleFloat 40s linear infinite;
            opacity: 0.7;
        }}

        .particles::after {{
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(rgba(0, 255, 247, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 255, 247, 0.04) 1px, transparent 1px);
            background-size: 50px 50px;
            animation: gridDrift 25s linear infinite;
        }}

        @keyframes particleFloat {{
            0%   {{ background-position: 0% 0%; }}
            100% {{ background-position: 100% 100%; }}
        }}

        @keyframes gridDrift {{
            0%   {{ background-position: 0 0; }}
            100% {{ background-position: 50px 50px; }}
        }}

        /* ===== Layout ===== */
        .site-header {{
            position: relative;
            z-index: 10;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 18px 22px;
            border-bottom: 1px solid rgba(0, 255, 247, 0.15);
        }}

        .brand {{
            font-size: 1.5em;
            font-weight: 700;
            letter-spacing: 1.5px;
            color: #00fff7;
            text-shadow: 0 0 12px #00fff7, 0 0 24px rgba(0, 255, 247, 0.4);
        }}

        .container {{
            position: relative;
            z-index: 5;
            max-width: 900px;
            margin: 0 auto;
            padding: 25px 16px 40px;
        }}

        /* ===== Cards ===== */
        .card {{
            background: rgba(10, 14, 22, 0.78);
            border: 1px solid rgba(0, 255, 247, 0.35);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 22px;
            box-shadow: 0 0 30px rgba(0, 255, 247, 0.12);
            backdrop-filter: blur(8px);
        }}

        /* Connection Card */
        .connection-card {{
            text-align: center;
        }}

        .connection-card h2 {{
            color: #b967ff;
            font-size: 1.25em;
            margin-bottom: 20px;
            letter-spacing: 1px;
        }}

        .connection-info {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px 20px;
            max-width: 420px;
            margin: 0 auto;
            text-align: left;
        }}

        .connection-info p {{
            margin: 0;
            font-size: 1.05em;
            line-height: 1.4;
        }}

        .connection-info strong {{
            color: #b967ff;
            display: block;
            font-size: 0.85em;
            margin-bottom: 2px;
            letter-spacing: 0.5px;
        }}

        /* Networks */
        h2.section-title {{
            color: #b967ff;
            font-size: 1.15em;
            margin-bottom: 16px;
            letter-spacing: 0.5px;
        }}

        .table-wrapper {{
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            border-radius: 10px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95em;
        }}

        th, td {{
            padding: 11px 10px;
            border-bottom: 1px solid rgba(0, 255, 247, 0.12);
            text-align: left;
        }}

        th {{
            color: #b967ff;
            background: rgba(185, 103, 255, 0.08);
        }}

        /* Buttons */
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
            transition: all 0.2s;
            min-width: 150px;
        }}

        .btn:hover {{
            background: #00fff7;
            color: #05070c;
            box-shadow: 0 0 18px #00fff7;
        }}

        /* Footer */
        .site-footer {{
            text-align: center;
            padding: 20px;
            font-size: 0.85em;
            color: rgba(0, 255, 247, 0.5);
            position: relative;
            z-index: 5;
        }}

        /* Mobile */
        @media (max-width: 520px) {{
            .connection-info {{
                grid-template-columns: 1fr;
                gap: 14px;
                text-align: center;
            }}
            .connection-info strong {{
                display: inline;
                margin-right: 6px;
            }}
            .brand {{
                font-size: 1.3em;
            }}
        }}

        /* Print */
        @media print {{
            body {{ background: white; color: black; }}
            .particles {{ display: none; }}
            .card {{
                background: white;
                border: 1px solid #666;
                box-shadow: none;
                color: black;
            }}
            th {{ background: #eee; color: black; }}
            th, td {{ border-color: #999; color: black; }}
            .btn {{ display: none; }}
            .brand, h2 {{ color: black; text-shadow: none; }}
            .site-footer {{ color: #666; }}
        }}
    </style>
</head>
<body>
    <div class="particles"></div>

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
                <p><strong>SSID</strong>{current_ssid}</p>
            </div>
        </div>

        <div class="card">
            <h2 class="section-title">Nearby Networks ({len(networks)} found)</h2>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>SSID</th>
                            <th>Signal</th>
                            <th>Ch</th>
                            <th>BSSID</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="btn-row">
            <button class="btn" onclick="location.reload()">🔄 Refresh Scan</button>
            <button class="btn" onclick="window.print()">🖨️ Print</button>
        </div>
    </div>

    <footer class="site-footer">
        Ryancito WiFi Scanner
    </footer>
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