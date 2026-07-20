import network
import socket
import time
from machine import UART, Pin

# ========== Wi-Fi ==========
WIFI_SSID = "WiresharkAndChill-2.4G"
WIFI_PASSWORD = "Ghost$3c"
WEB_PORT = 80
# ===========================

uart = UART(1, baudrate=256000, tx=Pin(9), rx=Pin(10))

status_text = "Starting..."
distance_cm = 0
move_energy = 0
still_energy = 0
gates_move = [0] * 9
gates_still = [0] * 9
last_update = "-"


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    time.sleep(1)

    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        for _ in range(25):
            if wlan.isconnected():
                break
            time.sleep(0.5)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("Connected!")
        print("Open -> http://" + ip)
        return ip

    print("Wi-Fi failed")
    return None


def enable_engineering_mode():
    cmd = bytes([
        0xFD, 0xFC, 0xFB, 0xFA,
        0x02, 0x00,
        0x62, 0x00,
        0x04, 0x03, 0x02, 0x01
    ])

    uart.write(cmd)
    time.sleep(0.3)
    print("Engineering mode on")


def read_sensor():
    global status_text
    global distance_cm
    global move_energy
    global still_energy
    global gates_move
    global gates_still
    global last_update

    if not uart.any():
        return

    data = uart.read()

    if not data or len(data) < 31:
        return

    for i in range(len(data) - 30):
        if (
            data[i] == 0xF4
            and data[i + 1] == 0xF3
            and data[i + 2] == 0xF2
            and data[i + 3] == 0xF1
        ):
            try:
                state = data[i + 8]
                move_dist = data[i + 9] + (data[i + 10] << 8)
                move_energy = data[i + 11]
                still_dist = data[i + 12] + (data[i + 13] << 8)
                still_energy = data[i + 14]

                if state == 0:
                    status_text = "No one detected"
                    distance_cm = 0
                elif state == 1:
                    status_text = "Moving target"
                    distance_cm = move_dist
                elif state == 2:
                    status_text = "Stationary target"
                    distance_cm = still_dist
                else:
                    status_text = "Moving + Stationary"
                    distance_cm = max(move_dist, still_dist)

                base = i + 17

                if len(data) >= base + 18:
                    for gate in range(9):
                        gates_move[gate] = data[base + gate]
                        gates_still[gate] = data[base + 9 + gate]

                now = time.localtime()
                last_update = "{:02d}:{:02d}:{:02d}".format(
                    now[3], now[4], now[5]
                )

            except Exception as error:
                print("Sensor parse error:", error)

            break


def get_status_class():
    if status_text == "No one detected":
        return "status-idle"
    if status_text == "Moving target":
        return "status-moving"
    if status_text == "Stationary target":
        return "status-still"
    if status_text == "Moving + Stationary":
        return "status-both"
    return "status-starting"


def make_energy_bar(value, css_class):
    value = max(0, min(int(value), 100))

    return (
        "<div class='meter'>"
        "<div class='meter-fill {}' style='width:{}%'></div>"
        "</div>"
    ).format(css_class, value)


def web_page(ip_address):
    inches = round(distance_cm / 2.54)
    feet = round(distance_cm / 30.48, 1)
    distance_percent = min(100, max(0, int((feet / 20) * 100)))
    status_class = get_status_class()

    gate_rows = ""

    for gate in range(9):
        moving = min(gates_move[gate], 100)
        stationary = min(gates_still[gate], 100)

        gate_start_ft = round(gate * 2.46, 1)
        gate_end_ft = round((gate + 1) * 2.46, 1)

        gate_rows += (
            "<tr>"
            "<td>"
            "<span class='gate-number'>{}</span>"
            "<span class='gate-range'>{}-{} ft</span>"
            "</td>"
            "<td>"
            "<div class='energy-value'>{}</div>"
            "{}"
            "</td>"
            "<td>"
            "<div class='energy-value'>{}</div>"
            "{}"
            "</td>"
            "</tr>"
        ).format(
            gate,
            gate_start_ft,
            gate_end_ft,
            moving,
            make_energy_bar(moving, "moving-fill"),
            stationary,
            make_energy_bar(stationary, "still-fill"),
        )

    page = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Ryancito Presence Radar</title>

<style>
:root{
    --background:#05080d;
    --panel:#090e16;
    --panel-alt:#0c111a;
    --header:#201a35;
    --cyan:#63f5f0;
    --cyan-muted:#2a6267;
    --purple:#c36dff;
    --text-muted:#78aeb1;
    --line:#17383d;
    --moving:#63f5f0;
    --stationary:#c36dff;
    --warning:#ffd166;
    --danger:#ff6881;
}

*{box-sizing:border-box;}

html{background:var(--background);}

body{
    margin:0;
    min-height:100vh;
    background:var(--background);
    color:var(--cyan);
    font-family:"Courier New",Courier,monospace;
    font-size:16px;
}

.shell{
    width:100%;
    min-height:100vh;
    border:1px solid #3d3d3d;
    background:var(--background);
}

.topbar{
    min-height:74px;
    display:flex;
    align-items:center;
    justify-content:center;
    border-bottom:1px solid var(--cyan-muted);
    padding:16px;
}

.brand{
    margin:0;
    color:var(--cyan);
    font-size:clamp(1.25rem,3vw,1.8rem);
    font-weight:700;
    text-align:center;
    text-shadow:
        0 0 8px rgba(99,245,240,.8),
        0 0 18px rgba(99,245,240,.35);
}

.content{padding:22px 16px 30px;}

.panel{
    margin:0 auto 22px;
    max-width:1220px;
    padding:22px;
    background:var(--panel);
    border:1px solid var(--cyan-muted);
    border-radius:17px;
}

.section-title{
    margin:0 0 20px;
    color:var(--purple);
    font-size:1.25rem;
    font-weight:700;
}

.status-grid{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:22px 60px;
}

.field{min-width:0;}

.field-label{
    margin-bottom:4px;
    color:var(--purple);
    font-size:.85rem;
    font-weight:700;
}

.field-value{
    color:var(--cyan);
    font-size:1.08rem;
    overflow-wrap:anywhere;
}

.status-indicator{
    display:inline-flex;
    align-items:center;
    gap:8px;
}

.status-indicator::before{
    width:9px;
    height:9px;
    content:"";
    flex:0 0 auto;
    border-radius:50%;
    background:currentColor;
    box-shadow:0 0 9px currentColor;
}

.status-idle{color:var(--text-muted);}
.status-moving{color:var(--moving);}
.status-still{color:var(--stationary);}
.status-both{color:var(--warning);}
.status-starting{color:var(--danger);}

.distance-layout{
    display:grid;
    grid-template-columns:minmax(210px,.75fr) minmax(300px,2fr);
    gap:30px;
    align-items:center;
}

.distance-primary{
    padding-right:30px;
    border-right:1px solid var(--line);
}

.distance-number{
    color:var(--cyan);
    font-size:clamp(2.6rem,7vw,5rem);
    font-weight:700;
    line-height:1;
    text-shadow:0 0 10px rgba(99,245,240,.45);
}

.distance-unit{
    color:var(--purple);
    font-size:1.1rem;
    font-weight:700;
}

.distance-feet{
    margin-top:8px;
    color:var(--text-muted);
    font-size:1rem;
}

.distance-meter-labels{
    display:flex;
    justify-content:space-between;
    margin-top:8px;
    color:var(--text-muted);
    font-size:.78rem;
}

.distance-meter{
    height:22px;
    overflow:hidden;
    background:repeating-linear-gradient(
        90deg,
        #0a171c 0,
        #0a171c calc(10% - 1px),
        var(--line) calc(10% - 1px),
        var(--line) 10%
    );
    border:1px solid var(--cyan-muted);
}

.distance-fill{
    height:100%;
    min-width:0;
    background:var(--cyan);
    box-shadow:0 0 10px rgba(99,245,240,.65);
}

.energy-summary{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:16px;
    margin-top:22px;
}

.summary-box{
    padding:14px;
    border:1px solid var(--line);
    background:var(--panel-alt);
}

.summary-value{
    margin-top:4px;
    color:var(--cyan);
    font-size:1.4rem;
    font-weight:700;
}

.table-wrap{
    width:100%;
    overflow-x:auto;
}

table{
    width:100%;
    min-width:650px;
    border-collapse:collapse;
}

th{
    padding:12px 10px;
    color:var(--purple);
    background:var(--header);
    font-size:.95rem;
    text-align:left;
}

td{
    padding:11px 10px;
    border-bottom:1px solid var(--line);
    color:var(--cyan);
    vertical-align:middle;
}

tr:last-child td{border-bottom:none;}

.gate-number{
    display:inline-block;
    min-width:28px;
    color:var(--cyan);
    font-size:1rem;
    font-weight:700;
}

.gate-range{
    color:var(--text-muted);
    font-size:.8rem;
}

.energy-value{
    display:inline-block;
    width:38px;
    color:var(--cyan);
    font-size:.85rem;
    vertical-align:middle;
}

.meter{
    display:inline-block;
    width:calc(100% - 48px);
    height:13px;
    overflow:hidden;
    border:1px solid var(--cyan-muted);
    background:#071014;
    vertical-align:middle;
}

.meter-fill{
    height:100%;
    min-width:0;
}

.moving-fill{
    background:var(--moving);
    box-shadow:0 0 8px rgba(99,245,240,.65);
}

.still-fill{
    background:var(--stationary);
    box-shadow:0 0 8px rgba(195,109,255,.55);
}

.legend{
    display:flex;
    flex-wrap:wrap;
    gap:20px;
    margin:-7px 0 17px;
    color:var(--text-muted);
    font-size:.86rem;
}

.legend-item{
    display:inline-flex;
    align-items:center;
    gap:7px;
}

.legend-dot{
    width:11px;
    height:11px;
    display:inline-block;
}

.moving-dot{
    background:var(--moving);
    box-shadow:0 0 7px rgba(99,245,240,.65);
}

.still-dot{
    background:var(--stationary);
    box-shadow:0 0 7px rgba(195,109,255,.55);
}

.controls{
    display:flex;
    justify-content:center;
    gap:22px;
    padding:5px 0 15px;
}

.button{
    min-width:128px;
    padding:13px 25px;
    color:var(--cyan);
    background:var(--panel);
    border:2px solid var(--cyan);
    border-radius:11px;
    font-family:"Courier New",Courier,monospace;
    font-size:1rem;
    text-decoration:none;
    text-align:center;
    cursor:pointer;
}

.button:hover,.button:focus{
    color:var(--background);
    background:var(--cyan);
    box-shadow:0 0 12px rgba(99,245,240,.6);
    outline:none;
}

.footer{
    margin-top:15px;
    color:var(--text-muted);
    font-size:.75rem;
    text-align:center;
}

@media(max-width:760px){
    body{font-size:15px;}

    .topbar{
        min-height:60px;
        padding:12px 10px;
    }

    .content{padding:12px 8px 24px;}

    .panel{
        width:100%;
        padding:16px 13px;
        margin-bottom:14px;
        border-radius:12px;
    }

    .section-title{
        margin-bottom:16px;
        font-size:1.1rem;
    }

    .status-grid{
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:17px 12px;
    }

    .field-value{font-size:.94rem;}

    .distance-layout{
        grid-template-columns:1fr;
        gap:20px;
    }

    .distance-primary{
        padding-right:0;
        padding-bottom:18px;
        border-right:none;
        border-bottom:1px solid var(--line);
    }

    .distance-number{font-size:3.5rem;}

    .energy-summary{
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:10px;
    }

    .table-wrap{overflow-x:visible;}

    table{
        min-width:0;
        table-layout:fixed;
    }

    th,td{padding:10px 6px;}

    th:first-child,td:first-child{width:31%;}

    th:nth-child(2),td:nth-child(2),
    th:nth-child(3),td:nth-child(3){
        width:34.5%;
    }

    .gate-number{
        display:block;
        min-width:0;
    }

    .gate-range{
        display:block;
        margin-top:3px;
        font-size:.68rem;
    }

    .energy-value{
        display:block;
        width:auto;
        margin-bottom:4px;
    }

    .meter{
        display:block;
        width:100%;
    }

    .controls{
        position:sticky;
        bottom:0;
        z-index:10;
        gap:10px;
        padding:12px 8px;
        background:rgba(5,8,13,.96);
        border-top:1px solid var(--cyan-muted);
    }

    .button{
        width:50%;
        min-width:0;
        min-height:48px;
        padding:12px 10px;
        touch-action:manipulation;
    }
}

@media(max-width:480px){
    .brand{font-size:1.2rem;}

    .status-grid{
        grid-template-columns:1fr;
        gap:14px;
    }

    .distance-number{font-size:3rem;}
    .energy-summary{grid-template-columns:1fr;}
    .panel{padding:14px 11px;}
    th{font-size:.78rem;}
    td{font-size:.78rem;}

    .legend{
        gap:10px;
        font-size:.75rem;
    }
}

@page{
    size:auto;
    margin:.4in;
}

@media print{
    *{
        color:#000 !important;
        background:#fff !important;
        box-shadow:none !important;
        text-shadow:none !important;
        filter:grayscale(100%) !important;
        -webkit-print-color-adjust:economy !important;
        print-color-adjust:economy !important;
    }

    html,body{
        width:100% !important;
        min-height:auto !important;
        margin:0 !important;
        padding:0 !important;
        overflow:visible !important;
        background:#fff !important;
        color:#000 !important;
        font-size:10pt !important;
    }

    .shell{
        width:100% !important;
        min-height:auto !important;
        border:none !important;
        background:#fff !important;
    }

    .topbar{
        min-height:auto !important;
        padding:0 0 12px !important;
        border:none !important;
        border-bottom:2px solid #000 !important;
    }

    .brand{
        color:#000 !important;
        font-size:18pt !important;
        text-align:left !important;
    }

    .content{
        width:100% !important;
        padding:12px 0 0 !important;
    }

    .panel{
        width:100% !important;
        max-width:none !important;
        margin:0 0 14px !important;
        padding:12px !important;
        border:1px solid #000 !important;
        border-radius:0 !important;
        break-inside:avoid;
        page-break-inside:avoid;
    }

    .section-title{
        margin-bottom:10px !important;
        color:#000 !important;
        font-size:13pt !important;
        border-bottom:1px solid #000 !important;
        padding-bottom:4px !important;
    }

    .field-label,
    .field-value,
    .distance-number,
    .distance-unit,
    .distance-feet,
    .summary-value,
    .gate-number,
    .gate-range,
    .energy-value,
    td,
    th{
        color:#000 !important;
    }

    .status-indicator::before{
        border:1px solid #000 !important;
        background:#000 !important;
    }

    .distance-primary{border-color:#000 !important;}

    .distance-meter,.meter{
        border:1px solid #000 !important;
        background:#fff !important;
    }

    .distance-fill,.moving-fill,.still-fill{
        background:#000 !important;
        border-right:1px solid #000 !important;
    }

    .summary-box{border:1px solid #000 !important;}

    table{
        width:100% !important;
        min-width:0 !important;
        table-layout:fixed !important;
    }

    th{
        font-weight:700 !important;
        border:1px solid #000 !important;
    }

    td{border:1px solid #000 !important;}

    .legend-dot{
        background:#000 !important;
        border:1px solid #000 !important;
    }

    .controls,.footer{display:none !important;}
}
</style>

<script>
var refreshTimer=null;

function stopRefresh(){
    if(refreshTimer!==null){
        clearTimeout(refreshTimer);
        refreshTimer=null;
    }
}

function startRefresh(){
    stopRefresh();
    refreshTimer=setTimeout(function(){
        window.location.reload();
    },1000);
}

function printPage(){
    stopRefresh();
    setTimeout(function(){
        window.print();
    },150);
}

window.addEventListener("load",function(){
    startRefresh();
});

window.addEventListener("beforeprint",function(){
    stopRefresh();
});

window.addEventListener("afterprint",function(){
    startRefresh();
});

window.addEventListener("focus",function(){
    if(refreshTimer===null){
        startRefresh();
    }
});
</script>
</head>

<body>
<div class="shell">
<header class="topbar">
<h1 class="brand">Ryancito Presence Radar</h1>
</header>

<main class="content">
<section class="panel">
<h2 class="section-title">Status</h2>

<div class="status-grid">
<div class="field">
<div class="field-label">Detection</div>
<div class="field-value">
<span class="status-indicator STATUS_CLASS">STATUS_TEXT</span>
</div>
</div>

<div class="field">
<div class="field-label">IP</div>
<div class="field-value">IP_ADDRESS</div>
</div>

<div class="field">
<div class="field-label">Board</div>
<div class="field-value">Nano ESP32</div>
</div>

<div class="field">
<div class="field-label">SSID</div>
<div class="field-value">SSID_VALUE</div>
</div>

<div class="field">
<div class="field-label">Updated</div>
<div class="field-value">LAST_UPDATE</div>
</div>

<div class="field">
<div class="field-label">Sensor</div>
<div class="field-value">LD2410 Engineering Mode</div>
</div>
</div>
</section>

<section class="panel">
<h2 class="section-title">Target Distance</h2>

<div class="distance-layout">
<div class="distance-primary">
<div>
<span class="distance-number">INCHES</span>
<span class="distance-unit">in</span>
</div>
<div class="distance-feet">FEET feet from sensor</div>
</div>

<div>
<div class="field-label">Distance Scale · 0-20 ft</div>

<div class="distance-meter">
<div class="distance-fill" style="width:DISTANCE_PERCENT%"></div>
</div>

<div class="distance-meter-labels">
<span>0 ft</span>
<span>5 ft</span>
<span>10 ft</span>
<span>15 ft</span>
<span>20 ft</span>
</div>

<div class="energy-summary">
<div class="summary-box">
<div class="field-label">Moving Energy</div>
<div class="summary-value">MOVE_ENERGY</div>
</div>

<div class="summary-box">
<div class="field-label">Stationary Energy</div>
<div class="summary-value">STILL_ENERGY</div>
</div>
</div>
</div>
</div>
</section>

<section class="panel">
<h2 class="section-title">Energy Gates</h2>

<div class="legend">
<span class="legend-item">
<span class="legend-dot moving-dot"></span>
Moving energy
</span>

<span class="legend-item">
<span class="legend-dot still-dot"></span>
Stationary energy
</span>
</div>

<div class="table-wrap">
<table>
<thead>
<tr>
<th>Gate / Range</th>
<th>Moving</th>
<th>Stationary</th>
</tr>
</thead>
<tbody>
GATE_ROWS
</tbody>
</table>
</div>
</section>

<div class="controls">
<button class="button" type="button" onclick="location.reload()">Rescan</button>
<button class="button" type="button" onclick="printPage()">Print</button>
</div>

<div class="footer">LD2410 presence-monitoring dashboard</div>
</main>
</div>
</body>
</html>
"""

    replacements = {
        "STATUS_CLASS": status_class,
        "STATUS_TEXT": status_text,
        "IP_ADDRESS": ip_address,
        "SSID_VALUE": WIFI_SSID,
        "LAST_UPDATE": last_update,
        "INCHES": str(inches),
        "FEET": str(feet),
        "DISTANCE_PERCENT": str(distance_percent),
        "MOVE_ENERGY": str(move_energy),
        "STILL_ENERGY": str(still_energy),
        "GATE_ROWS": gate_rows,
    }

    for old, new in replacements.items():
        page = page.replace(old, new)

    return page


def send_response(client, content):
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=UTF-8\r\n"
        "Cache-Control: no-store, no-cache, must-revalidate\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    client.send(header.encode())
    encoded_content = content.encode()
    chunk_size = 1024

    for position in range(0, len(encoded_content), chunk_size):
        client.send(encoded_content[position:position + chunk_size])


def run_server(ip):
    server = None

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        server.bind(("0.0.0.0", WEB_PORT))
        server.listen(2)

        print("Server running -> http://" + ip)

        while True:
            read_sensor()
            client = None

            try:
                client, address = server.accept()
                client.recv(1024)
                send_response(client, web_page(ip))

            except Exception as error:
                error_text = str(error)

                if (
                    "104" not in error_text
                    and "ECONNRESET" not in error_text
                ):
                    print("Client error:", error)

            finally:
                if client:
                    try:
                        client.close()
                    except:
                        pass

            time.sleep(0.05)

    finally:
        if server:
            try:
                server.close()
            except:
                pass

        print("Web server stopped")


# ========== Main ==========
ip = connect_wifi()

if ip:
    enable_engineering_mode()
    time.sleep(0.4)
    run_server(ip)
else:
    print("Could not connect to Wi-Fi")
