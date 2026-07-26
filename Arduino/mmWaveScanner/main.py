"""
Ryancito Presence Radar
Arduino Nano ESP32 + HLK-LD2410, MicroPython

Wiring (cross the UART data lines):
  LD2410 TX -> Nano ESP32 header D10 / ESP32 GPIO21 (UART RX)
  LD2410 RX -> Nano ESP32 header D9  / ESP32 GPIO18 (UART TX)
  LD2410 GND -> Nano ESP32 GND
  LD2410C VCC -> regulated 5V supply (BreadVolt 5V rail)

Important: MicroPython Pin numbers are ESP32 GPIO numbers, not the D-numbers
printed beside the Nano headers.

Copy this file to the board as main.py. Also copy secret.py to the board
after filling in its Wi-Fi and fallback access-point values.
"""

import gc
import json
import network
import socket
import time
from machine import Pin, UART

try:
    from secret import HOME_SSID, HOME_PASSWORD, AP_SSID, AP_PASSWORD
except ImportError:
    raise ImportError(
        "Missing secret.py. Copy secret_template.py to the board as "
        "secret.py and fill in its Wi-Fi values."
    )

WEB_PORT = 80
POLL_MS = 250
BUILD_VERSION = "2026.07.25-r4-gate-copy"

UART_BAUD = 256000
# Physical Nano header D9 = ESP32 GPIO18; header D10 = ESP32 GPIO21.
UART_TX_PIN = 18
UART_RX_PIN = 21
MAX_UART_BUFFER = 1024

DATA_HEADER = b"\xF4\xF3\xF2\xF1"
DATA_FOOTER = b"\xF8\xF7\xF6\xF5"

uart = UART(
    1,
    baudrate=UART_BAUD,
    tx=Pin(UART_TX_PIN),
    rx=Pin(UART_RX_PIN),
    rxbuf=2048,
)

# Use immutable bytes for compatibility with the Arduino Nano ESP32
# MicroPython port, whose bytearray does not support resizing operations.
rx_buffer = b""
radar = {
    "state": 0,
    "status": "Starting...",
    "distance_cm": 0,
    "move_distance_cm": 0,
    "still_distance_cm": 0,
    "move_energy": 0,
    "still_energy": 0,
    "move_gates": [0] * 9,
    "still_gates": [0] * 9,
    "updated_ms": 0,
    "frames": 0,
    "parse_errors": 0,
}


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Ryancito Presence Radar</title>
<style>
:root{--bg:#05080d;--panel:#090e16;--panel2:#0c111a;--cyan:#63f5f0;
--purple:#c36dff;--muted:#78aeb1;--line:#17383d;--warn:#ffd166;--danger:#ff6881}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--cyan);
font:15px "Courier New",monospace}body{padding:0 0 28px}.top{padding:18px;text-align:center;
border-bottom:1px solid #2a6267}.top h1{margin:0;font-size:clamp(1.25rem,4vw,1.8rem);
text-shadow:0 0 12px #63f5f099}.wrap{width:min(1220px,100%);margin:auto;padding:16px}
.panel{background:var(--panel);border:1px solid #2a6267;border-radius:16px;padding:18px;
margin-bottom:16px}.title{margin:0 0 15px;color:var(--purple);font-size:1.1rem}
.status-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px 28px}
.label{color:var(--purple);font-size:.78rem;font-weight:bold;margin-bottom:4px}
.value{overflow-wrap:anywhere}.dot:before{content:"";display:inline-block;width:9px;height:9px;
border-radius:50%;background:currentColor;box-shadow:0 0 9px currentColor;margin-right:8px}
.idle{color:var(--muted)}.moving{color:var(--cyan)}.still{color:var(--purple)}
.both{color:var(--warn)}.starting{color:var(--danger)}
.radar-layout{display:grid;grid-template-columns:minmax(280px,1fr) minmax(240px,.72fr);
gap:22px;align-items:center}.scope{position:relative;aspect-ratio:2/1;overflow:hidden;
border:1px solid #2a6267;border-radius:100% 100% 8px 8px;background:
radial-gradient(ellipse at 50% 100%,transparent 19%,#17383d 19.5%,transparent 20%,
transparent 39%,#17383d 39.5%,transparent 40%,transparent 59%,#17383d 59.5%,
transparent 60%,transparent 79%,#17383d 79.5%,transparent 80%),
linear-gradient(90deg,transparent 49.7%,#17383d 50%,transparent 50.3%),
linear-gradient(27deg,transparent 49.7%,#17383d 50%,transparent 50.3%),
linear-gradient(-27deg,transparent 49.7%,#17383d 50%,transparent 50.3%),#071014}
.sweep{position:absolute;left:50%;bottom:0;width:50%;height:2px;transform-origin:left center;
background:linear-gradient(90deg,#63f5f0,transparent);animation:sweep 2.8s linear infinite;
filter:drop-shadow(0 0 5px var(--cyan))}@keyframes sweep{from{transform:rotate(180deg)}
to{transform:rotate(360deg)}}.blip{position:absolute;left:50%;bottom:0;width:18px;height:18px;
border:2px solid currentColor;border-radius:50%;transform:translate(-50%,50%);
box-shadow:0 0 14px currentColor;transition:bottom .18s ease,color .18s,opacity .18s}
.blip:after{content:"";position:absolute;inset:3px;border-radius:50%;background:currentColor}
.scope-label{position:absolute;color:var(--muted);font-size:.67rem;bottom:3px}
.l0{left:2%}.l5{left:25%}.l10{left:49%}.l15{right:24%}.l20{right:2%}
.big{font-size:clamp(2.6rem,7vw,4.8rem);font-weight:bold;line-height:1;
text-shadow:0 0 10px #63f5f077}.unit{color:var(--purple);font-size:1.1rem}
.feet{color:var(--muted);margin:8px 0 20px}.summary{display:grid;grid-template-columns:1fr 1fr;
gap:10px}.box{padding:12px;background:var(--panel2);border:1px solid var(--line)}
.energy{font-size:1.4rem;font-weight:bold;margin-top:3px}
.gate-tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.gate-filter{display:flex;flex-wrap:wrap;gap:6px;margin:-5px 0 14px}.gate-filter button{
min-width:42px;padding:7px 9px;font-size:.78rem}
button{font:inherit;color:var(--cyan);background:var(--panel2);border:1px solid #2a6267;
border-radius:8px;padding:9px 12px;cursor:pointer}button:hover,button.active{color:var(--bg);
background:var(--cyan);border-color:var(--cyan)}button.secondary.active{background:var(--purple);
border-color:var(--purple)}.gates{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.gate{border:1px solid var(--line);background:var(--panel2);padding:11px;border-radius:8px}
.gate-head{display:flex;justify-content:space-between;color:var(--muted);font-size:.78rem;
margin-bottom:8px}.row{display:grid;grid-template-columns:22px 1fr 28px;gap:7px;
align-items:center;margin-top:7px;font-size:.75rem}.meter{height:10px;border:1px solid #2a6267;
background:#071014}.fill{height:100%;width:0;transition:width .18s ease}.move-fill{background:var(--cyan);
box-shadow:0 0 7px #63f5f099}.still-fill{background:var(--purple);
box-shadow:0 0 7px #c36dff88}.offline{display:none;margin:0 0 16px;padding:10px;
border:1px solid var(--danger);color:var(--danger);text-align:center}.footer{text-align:center;
color:var(--muted);font-size:.72rem}.hide-move .move-row,.hide-still .still-row{display:none}
@media(max-width:760px){.wrap{padding:10px}.panel{padding:14px;border-radius:12px}
.status-grid{grid-template-columns:repeat(2,1fr)}.radar-layout{grid-template-columns:1fr}
.gates{grid-template-columns:repeat(2,1fr)}}@media(max-width:460px){
.status-grid,.gates{grid-template-columns:1fr}.top{padding:14px}.big{font-size:3.2rem}}
@media(prefers-reduced-motion:reduce){.sweep{animation:none}.blip,.fill{transition:none}}
@media print{*{color:#000!important;background:#fff!important;box-shadow:none!important;
text-shadow:none!important}.top{text-align:left}.wrap{width:100%;padding:8px}.panel{border:1px solid #000;
break-inside:avoid}.gate-tools,.sweep,.offline{display:none!important}.scope,.meter,.gate,.box{
border-color:#000}.fill,.blip:after{background:#000!important}.gates{grid-template-columns:repeat(3,1fr)}
.footer{display:none}}
</style>
</head>
<body>
<header class="top"><h1>Ryancito Presence Radar</h1></header>
<main class="wrap">
<div id="offline" class="offline">Dashboard connection lost — retrying…</div>
<section class="panel">
 <h2 class="title">Status</h2>
 <div class="status-grid">
  <div><div class="label">Detection</div><div><span id="status" class="dot starting">Starting…</span></div></div>
  <div><div class="label">IP</div><div id="ip" class="value">-</div></div>
  <div><div class="label">Board</div><div>Nano ESP32</div></div>
  <div><div class="label">SSID</div><div id="ssid" class="value">-</div></div>
  <div><div class="label">Last sensor frame</div><div id="age">-</div></div>
  <div><div class="label">Sensor</div><div>LD2410 Engineering Mode</div></div>
 </div>
</section>
<section class="panel">
 <h2 class="title">Range Radar</h2>
 <div class="radar-layout">
  <div class="scope" aria-label="Range-only radar visualization">
   <div class="sweep"></div><div id="blip" class="blip" style="opacity:0"></div>
   <span class="scope-label l0">0</span><span class="scope-label l5">5 ft</span>
   <span class="scope-label l10">10</span><span class="scope-label l15">15</span>
   <span class="scope-label l20">20 ft</span>
  </div>
  <div>
   <div><span id="inches" class="big">0</span> <span class="unit">in</span></div>
   <div class="feet"><span id="feet">0.0</span> feet from sensor</div>
   <div class="summary">
    <div class="box"><div class="label">Moving Energy</div><div id="me" class="energy">0</div></div>
    <div class="box"><div class="label">Stationary Energy</div><div id="se" class="energy">0</div></div>
   </div>
  </div>
 </div>
</section>
<section id="gatePanel" class="panel">
 <h2 class="title">Energy Gates</h2>
 <div class="gate-tools">
  <button id="moveToggle" class="active" onclick="toggleKind('move')">Moving gates</button>
  <button id="stillToggle" class="secondary active" onclick="toggleKind('still')">Stationary gates</button>
  <button onclick="window.print()">Print</button>
 </div>
 <div id="gateFilter" class="gate-filter" aria-label="Individual gate visibility"></div>
 <div id="gates" class="gates"></div>
</section>
<div class="footer">LD2410 range/presence dashboard · live JSON updates</div>
</main>
<script>
"use strict";
const $=id=>document.getElementById(id);
let showMove=true,showStill=true,busy=false,failures=0;
const gates=$("gates");
const gateVisible=Array(9).fill(true),gateFilter=$("gateFilter");
for(let i=0;i<9;i++){
 const start=(i*.75).toFixed(2),end=((i+1)*.75).toFixed(2);
 gateFilter.insertAdjacentHTML("beforeend",`<button id="gbtn${i}" class="active" onclick="toggleGate(${i})">G${i}</button>`);
 gates.insertAdjacentHTML("beforeend",`<div id="gate${i}" class="gate"><div class="gate-head">
 <b>Gate ${i}</b><span>${start}–${end} m</span></div>
 <div class="row move-row"><span>M</span><div class="meter"><div id="m${i}" class="fill move-fill"></div></div><span id="mv${i}">0</span></div>
 <div class="row still-row"><span>S</span><div class="meter"><div id="s${i}" class="fill still-fill"></div></div><span id="sv${i}">0</span></div></div>`);
}
function toggleKind(kind){
 if(kind==="move"){showMove=!showMove;$("moveToggle").classList.toggle("active",showMove)}
 else{showStill=!showStill;$("stillToggle").classList.toggle("active",showStill)}
 $("gatePanel").classList.toggle("hide-move",!showMove);
 $("gatePanel").classList.toggle("hide-still",!showStill);
}
function toggleGate(i){
 gateVisible[i]=!gateVisible[i];
 $("gate"+i).style.display=gateVisible[i]?"":"none";
 $("gbtn"+i).classList.toggle("active",gateVisible[i]);
}
function render(d){
 $("ip").textContent=d.ip;$("ssid").textContent=d.ssid;
 $("status").textContent=d.status;
 $("status").className="dot "+(["idle","moving","still","both"][d.state]||"starting");
 $("inches").textContent=Math.round(d.distance_cm/2.54);
 $("feet").textContent=(d.distance_cm/30.48).toFixed(1);
 $("me").textContent=d.move_energy;$("se").textContent=d.still_energy;
 $("age").textContent=d.age_ms<1500?"now":(d.age_ms/1000).toFixed(1)+" s ago";
 const blip=$("blip"),pct=Math.min(100,Math.max(0,d.distance_cm/609.6*100));
 blip.style.bottom=pct+"%";blip.style.opacity=d.state===0?"0":"1";
 blip.style.color=d.state===2?"var(--purple)":d.state===3?"var(--warn)":"var(--cyan)";
 for(let i=0;i<9;i++){
  const m=Math.min(100,d.move_gates[i]||0),s=Math.min(100,d.still_gates[i]||0);
  $("m"+i).style.width=m+"%";$("mv"+i).textContent=m;
  $("s"+i).style.width=s+"%";$("sv"+i).textContent=s;
 }
}
async function update(){
 if(busy||document.hidden)return;busy=true;
 try{
  const r=await fetch("/api/status?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw Error(r.status);render(await r.json());failures=0;$("offline").style.display="none";
 }catch(e){if(++failures>2)$("offline").style.display="block"}
 finally{busy=false}
}
update();setInterval(update,__POLL_MS__);
</script>
</body>
</html>
""".replace("__POLL_MS__", str(POLL_MS))


def ticks_age(now, then):
    if not then:
        return 0
    return max(0, time.ticks_diff(now, then))


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep_ms(250)
    wlan.active(True)

    if not wlan.isconnected():
        print("Connecting to home Wi-Fi...")
        wlan.connect(HOME_SSID, HOME_PASSWORD)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while not wlan.isconnected() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            service_sensor()
            time.sleep_ms(100)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("Connected to home Wi-Fi. Open http://" + ip)
        return wlan, None, ip, HOME_SSID, "Home Wi-Fi"

    print("Home Wi-Fi unavailable; starting fallback access point...")
    wlan.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(False)
    time.sleep_ms(250)

    # Nano ESP32 MicroPython accepts these settings through config().
    ap.config(essid=AP_SSID, password=AP_PASSWORD)
    ap.active(True)
    deadline = time.ticks_add(time.ticks_ms(), 5000)
    while not ap.active() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        service_sensor()
        time.sleep_ms(50)

    if not ap.active():
        raise RuntimeError("Could not start fallback access point")

    ip = ap.ifconfig()[0]
    print("Access point ready. Join '" + AP_SSID + "' and open http://" + ip)
    return ap, ap, ip, AP_SSID, "Fallback AP"


def enable_engineering_mode():
    # LD2410C commands must be bracketed by configuration-mode commands.
    enter_configuration = bytes((
        0xFD, 0xFC, 0xFB, 0xFA,
        0x04, 0x00,
        0xFF, 0x00, 0x01, 0x00,
        0x04, 0x03, 0x02, 0x01,
    ))
    enable_engineering = bytes((
        0xFD, 0xFC, 0xFB, 0xFA,
        0x02, 0x00,
        0x62, 0x00,
        0x04, 0x03, 0x02, 0x01,
    ))
    end_configuration = bytes((
        0xFD, 0xFC, 0xFB, 0xFA,
        0x02, 0x00,
        0xFE, 0x00,
        0x04, 0x03, 0x02, 0x01,
    ))

    for command in (
        enter_configuration,
        enable_engineering,
        end_configuration,
    ):
        uart.write(command)
        time.sleep_ms(120)
        service_sensor()
    print("LD2410C engineering mode requested")


def state_name(state):
    return (
        "No one detected",
        "Moving target",
        "Stationary target",
        "Moving + Stationary",
    )[state] if 0 <= state <= 3 else "Unknown"


def parse_data_frame(frame):
    """Parse one length/footer-validated LD2410 report frame."""
    # frame offsets: header[0:4], length[4:6], type[6], 0xAA[7],
    # target state[8], basic target data[8:17].
    if len(frame) < 23 or frame[7] != 0xAA:
        return

    report_type = frame[6]
    if report_type not in (0x01, 0x02):
        return

    state = frame[8]
    if state > 3:
        radar["parse_errors"] += 1
        return

    move_distance = frame[9] | (frame[10] << 8)
    move_energy = frame[11]
    still_distance = frame[12] | (frame[13] << 8)
    still_energy = frame[14]
    detection_distance = frame[15] | (frame[16] << 8)

    radar["state"] = state
    radar["status"] = state_name(state)
    radar["move_distance_cm"] = move_distance
    radar["still_distance_cm"] = still_distance
    radar["move_energy"] = move_energy
    radar["still_energy"] = still_energy

    if state == 1:
        distance = move_distance
    elif state == 2:
        distance = still_distance
    elif state == 3:
        distance = detection_distance or max(move_distance, still_distance)
    else:
        distance = 0
    radar["distance_cm"] = distance

    # Engineering layout: bytes 17/18 are max moving/still gates,
    # bytes 19..27 are moving energies, 28..36 stationary energies.
    if report_type == 0x01 and len(frame) >= 41:
        for gate in range(9):
            radar["move_gates"][gate] = frame[19 + gate]
            radar["still_gates"][gate] = frame[28 + gate]

    radar["updated_ms"] = time.ticks_ms()
    radar["frames"] += 1


def service_sensor():
    """Drain UART and extract every complete report without blocking."""
    global rx_buffer
    waiting = uart.any()
    if waiting:
        incoming = uart.read(min(waiting, 512))
        if incoming:
            rx_buffer = rx_buffer + incoming

    while True:
        start = rx_buffer.find(DATA_HEADER)
        if start < 0:
            # Preserve a possible partial header split across UART reads.
            if len(rx_buffer) > 3:
                rx_buffer = rx_buffer[-3:]
            break
        if start:
            rx_buffer = rx_buffer[start:]
        if len(rx_buffer) < 10:
            break

        payload_length = rx_buffer[4] | (rx_buffer[5] << 8)
        total_length = 4 + 2 + payload_length + 4
        if payload_length < 7 or total_length > MAX_UART_BUFFER:
            radar["parse_errors"] += 1
            rx_buffer = rx_buffer[1:]
            continue
        if len(rx_buffer) < total_length:
            break

        if bytes(rx_buffer[total_length - 4:total_length]) != DATA_FOOTER:
            radar["parse_errors"] += 1
            rx_buffer = rx_buffer[1:]
            continue

        frame = bytes(rx_buffer[:total_length])
        rx_buffer = rx_buffer[total_length:]
        try:
            parse_data_frame(frame)
        except Exception as error:
            radar["parse_errors"] += 1
            print("Sensor frame error:", error)

    if len(rx_buffer) > MAX_UART_BUFFER:
        rx_buffer = rx_buffer[-3:]


def status_json(ip, wlan, active_ssid, network_mode):
    now = time.ticks_ms()
    data = {
        "state": radar["state"],
        "status": radar["status"],
        "distance_cm": radar["distance_cm"],
        "move_distance_cm": radar["move_distance_cm"],
        "still_distance_cm": radar["still_distance_cm"],
        "move_energy": radar["move_energy"],
        "still_energy": radar["still_energy"],
        "move_gates": radar["move_gates"],
        "still_gates": radar["still_gates"],
        "age_ms": ticks_age(now, radar["updated_ms"]),
        "frames": radar["frames"],
        "parse_errors": radar["parse_errors"],
        "ip": ip,
        "ssid": active_ssid,
        "network_mode": network_mode,
        "rssi": wlan.status("rssi") if wlan.isconnected() else None,
    }
    return json.dumps(data)


def send_all(client, data):
    view = memoryview(data)
    sent = 0
    while sent < len(view):
        service_sensor()
        count = client.send(view[sent:sent + 1024])
        if not count:
            raise OSError("socket closed while sending")
        sent += count


def send_response(client, body, content_type, status="200 OK"):
    if isinstance(body, str):
        body = body.encode()
    header = (
        "HTTP/1.1 {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(status, content_type, len(body)).encode()
    send_all(client, header)
    send_all(client, body)


def handle_client(client, ip, wlan, active_ssid, network_mode):
    client.settimeout(0.35)
    request = client.recv(768)
    if not request:
        return
    first_line = request.split(b"\r\n", 1)[0]
    parts = first_line.split()
    path = parts[1].split(b"?", 1)[0] if len(parts) >= 2 else b"/"

    if path == b"/" or path == b"/index.html":
        send_response(client, INDEX_HTML, "text/html; charset=utf-8")
    elif path == b"/api/status":
        send_response(
            client,
            status_json(ip, wlan, active_ssid, network_mode),
            "application/json; charset=utf-8",
        )
    elif path == b"/favicon.ico":
        send_response(client, b"", "image/x-icon", "204 No Content")
    else:
        send_response(client, "Not found", "text/plain; charset=utf-8", "404 Not Found")


def run_server(wlan, ip, active_ssid, network_mode):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", WEB_PORT))
    server.listen(4)
    server.settimeout(0)
    print("Radar server running at http://" + ip)

    last_gc = time.ticks_ms()
    while True:
        service_sensor()
        client = None
        try:
            client, _ = server.accept()
        except OSError:
            pass

        if client:
            try:
                handle_client(client, ip, wlan, active_ssid, network_mode)
            except OSError as error:
                # Browser cancellations and timeouts are routine during polling.
                error_number = error.args[0] if error.args else None
                if error_number not in (11, 104, 110, 116, 128):
                    print("Client socket error:", error)
            except Exception as error:
                print("Client error:", error)
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        now = time.ticks_ms()
        if time.ticks_diff(now, last_gc) >= 30000:
            gc.collect()
            last_gc = now
        time.sleep_ms(5)


def main():
    print("Ryancito Presence Radar build:", BUILD_VERSION)
    wlan, _ap, ip, active_ssid, network_mode = connect_wifi()
    enable_engineering_mode()
    time.sleep_ms(400)
    run_server(wlan, ip, active_ssid, network_mode)


try:
    main()
except Exception as fatal:
    print("Fatal error:", fatal)
    raise
