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
import machine
import network
import socket
import time
from machine import Pin, UART

try:
    import ntptime
except ImportError:
    ntptime = None

try:
    from secret import HOME_SSID, HOME_PASSWORD, AP_SSID, AP_PASSWORD
except ImportError:
    raise ImportError(
        "Missing secret.py. Copy secret_template.py to the board as "
        "secret.py and fill in its Wi-Fi values."
    )

try:
    from secret import BLE_PIN
except ImportError:
    BLE_PIN = None

try:
    from secret import TELEMETRY_HOST, TELEMETRY_PORT
except ImportError:
    TELEMETRY_HOST = None
    TELEMETRY_PORT = 5514

try:
    import bluetooth
except ImportError:
    bluetooth = None

WEB_PORT = 80
POLL_MS = 250
BUILD_VERSION = "2026.07.25-r20-journal-caret"

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
    "basic_frames": 0,
    "engineering_frames": 0,
    "engineering_updated_ms": 0,
    "parse_errors": 0,
}

ble = None
ble_connections = set()
ble_status_handle = None
ble_info_handle = None
ble_command_handle = None
ble_pending_command = None
ble_last_frame = -1
ntp_synced = False
ntp_last_sync = 0
sensor_last_recovery = 0
telemetry_last_state = None
watchdog = None


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
font:15px ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{padding:0 0 28px;
background:radial-gradient(circle at 50% -20%,#15243a 0,transparent 38%),var(--bg)}
.top{position:sticky;top:0;z-index:30;padding:17px 64px;text-align:center;border-bottom:1px solid #2a6267;
background:#05080de8;backdrop-filter:blur(14px)}.top h1{margin:0;font-size:clamp(1.25rem,4vw,1.8rem);
text-shadow:0 0 12px #63f5f099}.wrap{width:min(1220px,100%);margin:auto;padding:16px}
.gear{position:absolute;right:18px;top:50%;width:42px;height:42px;transform:translateY(-50%);
padding:0;border-radius:50%;font-size:1.35rem;display:grid;place-items:center}
.panel{background:var(--panel);border:1px solid #2a6267;border-radius:16px;padding:18px;
margin-bottom:16px;box-shadow:0 15px 40px #0003}.title{margin:0 0 15px;color:var(--purple);
font-size:1.1rem;letter-spacing:.02em}
.panel>.title{position:relative;padding-right:30px;cursor:pointer;user-select:none}
.panel>.title:after{content:"⌃";position:absolute;right:3px;top:-5px;color:var(--cyan);
font-size:1.55rem;line-height:1}.panel.collapsed>.title{margin-bottom:0}
.panel.collapsed>.title:after{content:"⌄";top:-8px}
.panel.collapsed>:not(.title){display:none}.panel>.title:focus{outline:1px dashed var(--cyan);
outline-offset:6px}
.status-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;
border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}
.status-item{min-width:0;padding:13px 15px;border-right:1px solid var(--line)}
.status-item:last-child{border-right:0}.status-sub{margin-top:4px;color:var(--muted);
font-size:.72rem;overflow-wrap:anywhere}
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
.echo{position:absolute;left:50%;bottom:0;width:12px;height:12px;border:1px solid currentColor;
border-radius:50%;transform:translate(-50%,50%);pointer-events:none;animation:echoFade 4s linear forwards}
@keyframes echoFade{from{opacity:.65;box-shadow:0 0 9px currentColor}to{opacity:0;transform:translate(-50%,50%) scale(2.4)}}
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
.charts{display:grid;grid-template-columns:1.4fr 1fr;gap:16px}canvas{display:block;width:100%;
height:210px;border:1px solid var(--line);background:#071014}.heatmap{display:grid;
grid-template-columns:repeat(9,1fr);gap:4px;height:210px}.heat-cell{position:relative;min-width:0;
border:1px solid var(--line);background:#071014;overflow:hidden}.heat-m,.heat-s{position:absolute;
left:0;right:0;bottom:0;height:0;transition:height .18s}.heat-m{background:#63f5f0bb}
.heat-s{background:#c36dffaa;mix-blend-mode:screen}.heat-label{position:absolute;z-index:2;
left:0;right:0;bottom:5px;text-align:center;font-size:.65rem;color:#fff}.diagnostics{display:grid;
grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:10px}.diag{min-width:0;
padding:11px 13px;border:1px solid var(--line);border-radius:10px;background:#071014}
.diag-value{font-size:1rem;font-weight:bold;margin-top:4px}.diag-sub{margin-top:5px;
color:var(--muted);font-size:.7rem;line-height:1.35}
.settings{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-top:14px}.settings label{
color:var(--purple);font-size:.75rem}.settings select{display:block;margin-top:4px;color:var(--cyan);
background:#071014;border:1px solid #2a6267;padding:7px;font:inherit}
.analytics{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.analytics .box{min-height:76px}
.cal-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cal-copy{color:var(--muted);
line-height:1.45}.progress{height:14px;border:1px solid #2a6267;background:#071014;margin:12px 0}
.progress-fill{height:100%;width:0;background:var(--cyan);box-shadow:0 0 8px #63f5f099;
transition:width .2s}.recommendations{display:grid;grid-template-columns:repeat(9,1fr);gap:5px}
.recommendation{padding:8px 4px;border:1px solid var(--line);text-align:center;font-size:.68rem}
.recommendation b{display:block;color:var(--purple);margin-bottom:4px}.cal-actions{display:flex;
flex-wrap:wrap;gap:8px}.notice{color:var(--warn);font-size:.75rem;margin-top:10px}
.modal{position:fixed;inset:0;z-index:100;
display:grid;place-items:center;padding:16px;background:#000a;backdrop-filter:blur(8px)}.modal[hidden]{display:none}
.modal-card{width:min(760px,100%);max-height:90vh;overflow:auto;padding:20px;border:1px solid #2a6267;
border-radius:18px;background:#090e16;box-shadow:0 25px 80px #000}.modal-head{display:flex;
align-items:center;justify-content:space-between;margin-bottom:18px}.modal-head h2{margin:0;color:var(--purple)}
.close{width:38px;height:38px;padding:0;border-radius:50%;font-size:1.25rem}.modal .settings{
display:grid;grid-template-columns:1fr 1fr;margin:0}.modal .settings select{width:100%}
.modal-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.settings-section{margin-top:22px;padding-top:20px;border-top:1px solid var(--line)}
.settings-section h3{margin:0 0 12px;color:var(--purple)}
.event-list{display:grid;gap:7px;max-height:360px;overflow-y:auto;overscroll-behavior:contain;
padding-right:6px;scrollbar-color:#2a6267 #071014;scrollbar-width:thin}
.event-list::-webkit-scrollbar{width:9px}.event-list::-webkit-scrollbar-track{background:#071014}
.event-list::-webkit-scrollbar-thumb{background:#2a6267;border:2px solid #071014;border-radius:9px}
.event-row{display:grid;grid-template-columns:150px 1fr 110px;
gap:12px;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel2)}
.event-time,.event-detail{color:var(--muted);font-size:.8rem}.event-name{font-weight:700}
.journal{margin-top:16px;border:1px solid var(--line);border-radius:10px;background:#071014}
.journal summary{position:relative;padding:12px 46px 12px 14px;color:var(--purple);font-weight:700;cursor:pointer;
list-style:none}.journal summary::-webkit-details-marker{display:none}.journal summary:after{
content:"⌄";position:absolute;right:15px;top:50%;transform:translateY(-50%);
color:var(--cyan);font-size:1.2rem;line-height:1}.journal[open] summary:after{content:"⌃"}
.journal-summary{display:block;margin-top:3px;color:var(--muted);font-size:.72rem;font-weight:400}
.journal .event-list{margin:0 10px 10px}
.print-meta{display:none}
@media(max-width:760px){.wrap{padding:10px}.panel{padding:14px;border-radius:12px}
.status-grid{grid-template-columns:repeat(2,1fr)}.status-item:nth-child(2){border-right:0}
.status-item:nth-child(-n+2){border-bottom:1px solid var(--line)}.radar-layout{grid-template-columns:1fr}
.gates{grid-template-columns:repeat(2,1fr)}.charts{grid-template-columns:1fr}
.diagnostics{grid-template-columns:repeat(2,1fr)}.analytics{grid-template-columns:repeat(2,1fr)}
.cal-grid{grid-template-columns:1fr}.event-row{grid-template-columns:1fr;gap:4px}}@media(max-width:460px){
.status-grid,.gates{grid-template-columns:1fr}.status-item{border-right:0!important;
border-bottom:1px solid var(--line)}.status-item:last-child{border-bottom:0}.top{padding:14px 58px}.gear{right:10px}.big{font-size:3.2rem}
.modal .settings{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.sweep{animation:none}.blip,.fill{transition:none}}
@page{size:letter portrait;margin:.45in}
@media print{*{color:#000!important;background:#fff!important;box-shadow:none!important;
text-shadow:none!important}.top{text-align:left}.wrap{width:100%;padding:8px}.panel{border:1px solid #000;
break-inside:avoid}.gear,.modal,.gate-tools,.settings,.sweep,.echo,.offline{display:none!important}.scope,.meter,.gate,.box{
border-color:#000}.fill,.blip:after{background:#000!important}.gates{grid-template-columns:repeat(3,1fr)}
.panel.collapsed>:not(.title){display:revert!important}.panel>.title:after{display:none}
#gatePanel{break-inside:auto}.gate{break-inside:avoid}.print-meta{display:block!important;
margin:8px 0 0;color:#333!important;font-size:9pt}.footer{display:block!important;margin-top:12px;
border-top:1px solid #000;padding-top:6px}
.scope{background:
radial-gradient(ellipse at 50% 100%,transparent 19%,#555 19.5%,transparent 20%,
transparent 39%,#555 39.5%,transparent 40%,transparent 59%,#555 59.5%,
transparent 60%,transparent 79%,#555 79.5%,transparent 80%),
linear-gradient(90deg,transparent 49.7%,#555 50%,transparent 50.3%),
linear-gradient(27deg,transparent 49.7%,#555 50%,transparent 50.3%),
linear-gradient(-27deg,transparent 49.7%,#555 50%,transparent 50.3%),#fff!important;
-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
.scope-label{color:#000!important;font-weight:700}.blip{border-color:#000!important}}
</style>
</head>
<body>
<header class="top"><h1>Ryancito Presence Radar</h1>
<button class="gear" type="button" aria-label="Open settings" onclick="openSettings()">⚙</button>
<div id="printMeta" class="print-meta"></div>
</header>
<main class="wrap">
<div id="offline" class="offline">Dashboard connection lost — retrying…</div>
<section class="panel">
 <h2 class="title">Status &amp; System Health</h2>
 <div class="status-grid">
  <div class="status-item"><div class="label">Detection</div><div><span id="status" class="dot starting">Starting…</span></div>
   <div class="status-sub">Range <span id="statusDistance">0 ft 0 in</span></div></div>
  <div class="status-item"><div class="label">Sensor</div><div id="sensorMode">Starting…</div>
   <div class="status-sub">Last frame <span id="age">-</span></div></div>
  <div class="status-item"><div class="label">Network</div><div id="ssid" class="value">-</div>
   <div id="ip" class="status-sub">-</div></div>
  <div class="status-item"><div class="label">Device</div><div>Nano ESP32</div>
   <div class="status-sub">LD2410C · UART 256000</div></div>
 </div>
 <div class="diagnostics">
  <div class="diag"><div class="label">Sensor health</div><div id="sensorHealth" class="diag-value">-</div>
   <div class="diag-sub">Engineering frames <span id="engineeringFrames">0</span></div></div>
  <div class="diag"><div class="label">Sensor data</div><div id="fps" class="diag-value">0/s</div>
   <div class="diag-sub"><span id="frames">0</span> frames · <span id="errors">0</span> errors</div></div>
  <div class="diag"><div class="label">Connection</div><div id="rssi" class="diag-value">-</div>
   <div class="diag-sub">Dashboard <span id="latency">-</span></div></div>
  <div class="diag"><div class="label">System</div><div id="memory" class="diag-value">-</div>
   <div class="diag-sub">Clock <span id="timeSync">-</span></div></div>
 </div>
</section>
<section class="panel">
 <h2 class="title">Range Radar</h2>
 <div class="radar-layout">
  <div class="scope" aria-label="Range-only radar visualization">
   <div class="sweep"></div><div id="blip" class="blip" style="opacity:0"></div>
   <span id="range0" class="scope-label l0">0</span><span id="range25" class="scope-label l5">5 ft</span>
   <span id="range50" class="scope-label l10">10</span><span id="range75" class="scope-label l15">15</span>
   <span id="range100" class="scope-label l20">20 ft</span>
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
 </div>
 <div id="gateWarning" class="notice">Waiting for LD2410C engineering frames. The board will retry automatically.</div>
 <div id="gateFilter" class="gate-filter" aria-label="Individual gate visibility"></div>
 <div id="gates" class="gates"></div>
</section>
<section class="panel">
 <h2 class="title">Detection History</h2>
 <div class="charts">
  <div><div class="label">Target distance and state</div><canvas id="history" width="720" height="210"></canvas></div>
  <div><div class="label">Live energy heatmap · Gate 0–8</div><div id="heatmap" class="heatmap"></div></div>
 </div>
</section>
<section class="panel">
 <h2 class="title">Logs</h2>
 <div class="analytics">
  <div class="box"><div class="label">Occupied since</div><div id="occupiedSince">Clear</div></div>
  <div class="box"><div class="label">Current session</div><div id="sessionTime">0:00</div></div>
  <div class="box"><div class="label">Last movement</div><div id="lastMovement">-</div></div>
  <div class="box"><div class="label">Occupied today</div><div id="todayTotal">0 min</div></div>
  <div class="box"><div class="label">Sessions today</div><div id="sessionCount">0</div></div>
 </div>
 <details class="journal">
  <summary>Security Event Journal
   <span id="journalSummary" class="journal-summary">No security events recorded yet.</span>
  </summary>
  <div id="eventList" class="event-list"><div class="event-detail">No events recorded yet.</div></div>
 </details>
</section>
<div class="footer">LD2410 range/presence dashboard · live JSON updates</div>
</main>
<div id="settingsModal" class="modal" hidden onclick="modalBackdrop(event)">
 <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
  <div class="modal-head"><h2 id="settingsTitle">Dashboard Settings</h2>
   <button class="close" type="button" aria-label="Close settings" onclick="closeSettings()">×</button>
  </div>
  <div class="settings">
   <label>Smoothing<select id="smoothSetting"><option value="0">Raw</option>
   <option value=".25">Responsive</option><option value=".12">Smooth</option></select></label>
   <label>Radar range<select id="rangeSetting"><option value="304.8">10 ft</option>
   <option value="609.6">20 ft</option><option value="914.4">30 ft</option></select></label>
   <label>History window<select id="historyWindow"><option value="60000">1 minute</option>
   <option value="3600000">1 hour</option><option value="86400000">24 hours</option></select></label>
  </div>
  <div class="modal-actions">
   <button onclick="clearHistory()">Clear history</button>
   <button onclick="exportEventsCsv()">Export CSV</button>
   <button onclick="exportEvents()">Export JSON Lines</button>
   <button onclick="window.open('/metrics','_blank')">Open metrics</button>
   <button onclick="printDashboard()">Print or save PDF</button>
   <button onclick="resetPanelLayout()">Reset panel layout</button>
  </div>
  <div class="settings-section">
   <h3>Calibration Lab</h3>
   <div class="cal-grid">
    <div class="cal-copy">
     <p>First capture an empty room, then walk and pause at the distances you want detected.
     Calibration runs entirely in this browser and does not change the sensor.</p>
     <div class="cal-actions">
      <button id="emptyButton" onclick="startCalibration('empty')">Capture empty room · 30s</button>
      <button id="walkButton" onclick="startCalibration('walk')" disabled>Capture walk test · 30s</button>
      <button onclick="resetCalibration()">Reset</button>
     </div>
     <div class="progress"><div id="calProgress" class="progress-fill"></div></div>
     <div id="calStatus">Ready to capture the empty-room noise floor.</div>
     <div class="notice">Recommendations are advisory; nothing is written to the LD2410C.</div>
    </div>
    <div>
     <div class="label">Recommended moving / stationary thresholds</div>
     <div id="recommendations" class="recommendations"></div>
    </div>
   </div>
  </div>
 </section>
</div>
<script>
"use strict";
const $=id=>document.getElementById(id);
function openSettings(){$("settingsModal").hidden=false;document.body.style.overflow="hidden";
 $("settingsModal").querySelector(".close").focus()}
function closeSettings(){$("settingsModal").hidden=true;document.body.style.overflow=""}
function modalBackdrop(event){if(event.target===$("settingsModal"))closeSettings()}
function printDashboard(){closeSettings();setTimeout(()=>window.print(),80)}
function resetPanelLayout(){localStorage.removeItem("ryancitoCollapsedPanels");
 document.querySelectorAll(".panel").forEach(panel=>panel.classList.remove("collapsed"));
 document.querySelectorAll(".panel>.title").forEach(title=>title.setAttribute("aria-expanded","true"));
 closeSettings()}
addEventListener("keydown",event=>{if(event.key==="Escape"&&!$("settingsModal").hidden)closeSettings()});
let printCollapsed=[];
addEventListener("beforeprint",()=>{
 printCollapsed=Array.from(document.querySelectorAll(".panel.collapsed"));
 printCollapsed.forEach(panel=>panel.classList.remove("collapsed"));
 const detection=$("status").textContent,distance=$("feet").textContent,ip=$("ip").textContent;
 $("printMeta").textContent="Snapshot: "+new Date().toLocaleString()+" | Detection: "+detection+
  " | Distance: "+distance+" ft | Device: "+ip;
 drawHistory();
});
addEventListener("afterprint",()=>{printCollapsed.forEach(panel=>panel.classList.add("collapsed"));
 printCollapsed=[]});
const collapsedPanels=JSON.parse(localStorage.getItem("ryancitoCollapsedPanels")||"{}");
document.querySelectorAll(".panel>.title").forEach(title=>{
 const panel=title.parentElement,key=title.textContent.trim();
 title.tabIndex=0;title.setAttribute("role","button");title.setAttribute("aria-expanded","true");
 if(collapsedPanels[key]){panel.classList.add("collapsed");title.setAttribute("aria-expanded","false")}
 const toggle=()=>{panel.classList.toggle("collapsed");const closed=panel.classList.contains("collapsed");
  title.setAttribute("aria-expanded",String(!closed));collapsedPanels[key]=closed;
  localStorage.setItem("ryancitoCollapsedPanels",JSON.stringify(collapsedPanels))};
 title.addEventListener("click",toggle);title.addEventListener("keydown",event=>{
  if(event.key==="Enter"||event.key===" "){event.preventDefault();toggle()}});
});
let showMove=true,showStill=true,busy=false,failures=0,smoothedDistance=0,lastEcho=0;
let lastFrameCount=0,lastFrameTime=performance.now();
let latestRender=null,renderPending=false,streamConnected=false,lastStreamMessage=0;
const samples=[],prefs=JSON.parse(localStorage.getItem("ryancitoRadarPrefs")||"{}");
let historyDb=null,lastStored=0,occupiedSince=0,lastMovement=0,previousState=null,previousStale=null;
let calibration=null,emptyCapture=null,walkCapture=null;
const dayKey=()=>new Date().toISOString().slice(0,10);
let daily=JSON.parse(localStorage.getItem("ryancitoDaily")||"{}");
const gates=$("gates"),heatmap=$("heatmap");
const gateVisible=Array(9).fill(true),gateFilter=$("gateFilter");
function feetInches(cm){
 const total=Math.max(0,Math.round((Number(cm)||0)/2.54));
 return Math.floor(total/12)+" ft "+total%12+" in";
}
for(let i=0;i<9;i++){
 const start=feetInches(i*75),end=feetInches((i+1)*75);
 gateFilter.insertAdjacentHTML("beforeend",`<button id="gbtn${i}" class="active" onclick="toggleGate(${i})">G${i}</button>`);
 gates.insertAdjacentHTML("beforeend",`<div id="gate${i}" class="gate"><div class="gate-head">
 <b>Gate ${i}</b><span>${start}–${end}</span></div>
 <div class="row move-row"><span>M</span><div class="meter"><div id="m${i}" class="fill move-fill"></div></div><span id="mv${i}">0</span></div>
 <div class="row still-row"><span>S</span><div class="meter"><div id="s${i}" class="fill still-fill"></div></div><span id="sv${i}">0</span></div></div>`);
 heatmap.insertAdjacentHTML("beforeend",`<div class="heat-cell"><div id="hm${i}" class="heat-m"></div>
 <div id="hs${i}" class="heat-s"></div><span class="heat-label">G${i}</span></div>`);
}
function savePrefs(){localStorage.setItem("ryancitoRadarPrefs",JSON.stringify({
 showMove,showStill,gateVisible,smoothing:$("smoothSetting").value,range:$("rangeSetting").value}))}
function openHistoryDb(){
 const req=indexedDB.open("RyancitoRadar",2);
 req.onupgradeneeded=()=>{const db=req.result;
  if(!db.objectStoreNames.contains("samples")){const store=db.createObjectStore("samples",{keyPath:"t"});
   store.createIndex("time","t")}
  if(!db.objectStoreNames.contains("events")){const events=db.createObjectStore("events",
   {keyPath:"id",autoIncrement:true});events.createIndex("time","t")}};
 req.onsuccess=()=>{historyDb=req.result;pruneHistory();loadHistory();loadEvents()};
}
function storeHistory(d){
 const now=Date.now();if(!historyDb||now-lastStored<1000)return;lastStored=now;
 const tx=historyDb.transaction("samples","readwrite");
 tx.objectStore("samples").put({t:now,s:d.state,d:d.distance_cm,m:d.move_gates,q:d.still_gates});
}
function pruneHistory(){
 if(!historyDb)return;const tx=historyDb.transaction("samples","readwrite");
 const range=IDBKeyRange.upperBound(Date.now()-86400000);tx.objectStore("samples").delete(range);
}
function loadHistory(){
 if(!historyDb)return;const span=+$("historyWindow").value,range=IDBKeyRange.lowerBound(Date.now()-span);
 const req=historyDb.transaction("samples").objectStore("samples").getAll(range);
 req.onsuccess=()=>{samples.length=0;for(const p of req.result)samples.push({t:p.t,d:p.d,s:p.s});drawHistory()};
}
function eventName(previous,current){
 if(previous===0&&current>0)return "presence_started";
 if(previous>0&&current===0)return "presence_cleared";
 if(current===1&&previous!==1)return "movement_started";
 if(current===2&&previous!==2)return "stationary_started";
 if(current===3&&previous!==3)return "combined_presence";
 return "state_changed";
}
function recordEvent(d,previous,forcedName){
 if(!historyDb)return;const event={t:Date.now(),event:forcedName||eventName(previous,d.state),
  previous_state:previous,state:d.state,distance_cm:d.distance_cm,move_energy:d.move_energy,
  still_energy:d.still_energy,move_gates:d.move_gates.slice(),still_gates:d.still_gates.slice()};
 const tx=historyDb.transaction("events","readwrite");tx.objectStore("events").add(event);
 tx.oncomplete=loadEvents;
}
function loadEvents(){
 if(!historyDb)return;const request=historyDb.transaction("events").objectStore("events").getAll();
 request.onsuccess=()=>{const events=request.result.slice(-50).reverse(),list=$("eventList");
  list.replaceChildren();if(!events.length){list.textContent="No events recorded yet.";
   $("journalSummary").textContent="No security events recorded yet.";return}
  const latest=events[0],latestName=latest.event.replaceAll("_"," ");
  $("journalSummary").textContent=events.length+" recent events · Latest: "+latestName+
   " at "+new Date(latest.t).toLocaleTimeString();
  for(const event of events){const row=document.createElement("div");row.className="event-row";
   const stamp=document.createElement("div");stamp.className="event-time";
   stamp.textContent=new Date(event.t).toLocaleString();
   const name=document.createElement("div");name.className="event-name";
   name.textContent=event.event.replaceAll("_"," ");
   const detail=document.createElement("div");detail.className="event-detail";
   detail.textContent=feetInches(event.distance_cm);row.append(stamp,name,detail);list.append(row)}};
}
function exportEvents(){
 if(!historyDb)return;const request=historyDb.transaction("events").objectStore("events").getAll();
 request.onsuccess=()=>{const lines=request.result.map(event=>JSON.stringify(
  Object.assign({time_iso:new Date(event.t).toISOString()},event))).join("\n")+"\n";
  const url=URL.createObjectURL(new Blob([lines],{type:"application/x-ndjson"}));
  const link=document.createElement("a");link.href=url;
  link.download="ryancito-events-"+new Date().toISOString().slice(0,10)+".jsonl";link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000)};
}
function csvCell(value){
 const text=String(value==null?"":value);
 return /[",\r\n]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;
}
function exportEventsCsv(){
 if(!historyDb)return;const request=historyDb.transaction("events").objectStore("events").getAll();
 request.onsuccess=()=>{
  const columns=["time_iso","event","previous_state","state","distance_ft_in","distance_cm",
   "move_energy","still_energy","move_gates","still_gates"];
  const rows=request.result.map(event=>[
   new Date(event.t).toISOString(),event.event,event.previous_state,event.state,
   feetInches(event.distance_cm),event.distance_cm,event.move_energy,event.still_energy,
   (event.move_gates||[]).join("|"),(event.still_gates||[]).join("|")
  ].map(csvCell).join(","));
  const csv=columns.join(",")+"\r\n"+rows.join("\r\n")+"\r\n";
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;
  link.download="ryancito-security-events-"+new Date().toISOString().slice(0,10)+".csv";
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
}
function formatDuration(ms){const min=Math.floor(ms/60000),hr=Math.floor(min/60);
 return hr?hr+"h "+min%60+"m":min+"m"}
function updateOccupancy(d){
 const now=Date.now(),key=dayKey();if(!daily[key])daily[key]={total:0,sessions:0,lastTick:now};
 if(previousState!==null&&previousState!==d.state)recordEvent(d,previousState);
 if(previousStale!==null&&previousStale!==d.sensor_stale)recordEvent(
  d,previousState,d.sensor_stale?"sensor_stale":"sensor_recovered");
 const rec=daily[key];if(d.state){
  if(!occupiedSince){occupiedSince=now;rec.sessions++}
  rec.total+=Math.min(2000,now-rec.lastTick);if(d.state===1||d.state===3)lastMovement=now;
 }else occupiedSince=0;rec.lastTick=now;localStorage.setItem("ryancitoDaily",JSON.stringify(daily));
 $("occupiedSince").textContent=occupiedSince?new Date(occupiedSince).toLocaleTimeString():"Clear";
 $("sessionTime").textContent=occupiedSince?formatDuration(now-occupiedSince):"0 min";
 $("lastMovement").textContent=lastMovement?new Date(lastMovement).toLocaleTimeString():"-";
 $("todayTotal").textContent=formatDuration(rec.total);$("sessionCount").textContent=rec.sessions;
 previousState=d.state;previousStale=d.sensor_stale;
}
function blankCapture(){return Array.from({length:9},()=>({m:[],s:[]}))}
function startCalibration(kind){
 calibration={kind,start:Date.now(),data:blankCapture()};$("emptyButton").disabled=true;$("walkButton").disabled=true;
 $("calStatus").textContent=kind==="empty"?"Keep the room empty…":"Walk, stop, and sit throughout the detection area…";
}
function calibrationSample(d){
 if(!calibration)return;for(let i=0;i<9;i++){calibration.data[i].m.push(d.move_gates[i]||0);
 calibration.data[i].s.push(d.still_gates[i]||0)}
 const elapsed=Date.now()-calibration.start;$("calProgress").style.width=Math.min(100,elapsed/300)+"%";
 if(elapsed<30000)return;const kind=calibration.kind,data=calibration.data;calibration=null;
 if(kind==="empty"){emptyCapture=data;$("walkButton").disabled=false;$("calStatus").textContent="Empty-room capture complete. Start the walk test."}
 else{walkCapture=data;$("emptyButton").disabled=false;$("calStatus").textContent="Calibration complete. Review the recommendations.";showRecommendations()}
 $("calProgress").style.width="0";
}
function percentile(a,p){if(!a.length)return 0;const b=a.slice().sort((x,y)=>x-y);return b[Math.floor((b.length-1)*p)]}
function showRecommendations(){
 if(!emptyCapture||!walkCapture)return;let html="";
 for(let i=0;i<9;i++){const nm=percentile(emptyCapture[i].m,.95),ns=percentile(emptyCapture[i].s,.95);
 const wm=percentile(walkCapture[i].m,.65),ws=percentile(walkCapture[i].s,.65);
 const rm=Math.round(Math.max(nm+8,Math.min(95,(nm+wm)/2)));
 const rs=Math.round(Math.max(ns+8,Math.min(95,(ns+ws)/2)));
 html+=`<div class="recommendation"><b>G${i}</b>M ${rm}<br>S ${rs}</div>`}
 $("recommendations").innerHTML=html;
}
function resetCalibration(){calibration=null;emptyCapture=null;walkCapture=null;$("emptyButton").disabled=false;
 $("walkButton").disabled=true;$("calProgress").style.width="0";$("calStatus").textContent="Ready to capture the empty-room noise floor.";
 $("recommendations").innerHTML=""}
function queueRender(data,latency){
 latestRender={data,latency};if(renderPending)return;renderPending=true;
 requestAnimationFrame(()=>{renderPending=false;if(latestRender){const item=latestRender;latestRender=null;
 render(item.data,item.latency)}});
}
function decodeStream(a){const names=["No one detected","Moving target","Stationary target","Moving + Stationary"];
 return {state:a[0],status:names[a[0]]||"Unknown",distance_cm:a[1],move_distance_cm:a[2],
 still_distance_cm:a[3],move_energy:a[4],still_energy:a[5],move_gates:a[6],still_gates:a[7],
 age_ms:a[8],frames:a[9],parse_errors:a[10],ip:a[11],ssid:a[12],rssi:a[13],mem_free:a[14],
 ntp_synced:!!a[15],sensor_stale:!!a[16],engineering_active:!!a[17],
 engineering_frames:a[18]||0,basic_frames:a[19]||0}}
function startStream(){
 if(!window.EventSource)return;const source=new EventSource("/api/stream");
 source.onopen=()=>{streamConnected=true;failures=0;$("offline").style.display="none"};
 source.onmessage=event=>{lastStreamMessage=Date.now();queueRender(decodeStream(JSON.parse(event.data)),0)};
 source.onerror=()=>{streamConnected=false;if(Date.now()-lastStreamMessage>3000)$("offline").style.display="block"};
}
function toggleKind(kind){
 if(kind==="move"){showMove=!showMove;$("moveToggle").classList.toggle("active",showMove)}
 else{showStill=!showStill;$("stillToggle").classList.toggle("active",showStill)}
 $("gatePanel").classList.toggle("hide-move",!showMove);
 $("gatePanel").classList.toggle("hide-still",!showStill);
 savePrefs();
}
function toggleGate(i){
 gateVisible[i]=!gateVisible[i];
 $("gate"+i).style.display=gateVisible[i]?"":"none";
 $("gbtn"+i).classList.toggle("active",gateVisible[i]);
 savePrefs();
}
function addEcho(distance,state,range){
 const now=performance.now();if(!state||now-lastEcho<750)return;lastEcho=now;
 const e=document.createElement("i");e.className="echo";e.style.bottom=Math.min(100,distance/range*100)+"%";
 e.style.color=state===2?"var(--purple)":state===3?"var(--warn)":"var(--cyan)";
 document.querySelector(".scope").appendChild(e);setTimeout(()=>e.remove(),4100);
}
function clearHistory(){
 if(!confirm("Clear radar history and the security event journal in this browser?"))return;
 samples.length=0;drawHistory();daily={};localStorage.removeItem("ryancitoDaily");
 occupiedSince=0;lastMovement=0;previousState=0;previousStale=null;
 if(historyDb){const tx=historyDb.transaction(["samples","events"],"readwrite");
  tx.objectStore("samples").clear();tx.objectStore("events").clear();
  tx.oncomplete=()=>{loadEvents();$("todayTotal").textContent="0 min";
   $("sessionCount").textContent="0";$("occupiedSince").textContent="Clear";
   $("sessionTime").textContent="0 min";$("lastMovement").textContent="-"}}
}
function updateRadarLabels(){
 const feet=+$("rangeSetting").value/30.48;
 const label=value=>Number.isInteger(value)?String(value):value.toFixed(1);
 $("range0").textContent="0";
 $("range25").textContent=label(feet*.25)+" ft";
 $("range50").textContent=label(feet*.5);
 $("range75").textContent=label(feet*.75);
 $("range100").textContent=label(feet)+" ft";
}
function drawHistory(){
 const c=$("history"),x=c.getContext("2d"),w=c.width,h=c.height,range=+$("rangeSetting").value;
 x.clearRect(0,0,w,h);x.strokeStyle="#17383d";x.fillStyle="#78aeb1";x.font="10px monospace";
 for(let i=0;i<=4;i++){const y=8+(h-24)*i/4;x.beginPath();x.moveTo(0,y);x.lineTo(w,y);x.stroke();
 x.fillText(Math.round(range/30.48*(1-i/4))+"ft",4,y-2)}
 if(samples.length<2)return;const span=+$("historyWindow").value,cutoff=Date.now()-span;x.beginPath();
 samples.forEach((p,i)=>{const px=(p.t-cutoff)/span*w,py=8+(h-24)*(1-Math.min(1,p.d/range));
 i?x.lineTo(px,py):x.moveTo(px,py)});x.strokeStyle="#63f5f0";x.lineWidth=2;
 x.shadowColor="#63f5f0";x.shadowBlur=5;x.stroke();x.shadowBlur=0;
 for(const p of samples){if(!p.s)continue;const px=(p.t-cutoff)/60000*w;
 const py=8+(h-24)*(1-Math.min(1,p.d/range));x.fillStyle=p.s===2?"#c36dff":p.s===3?"#ffd166":"#63f5f0";
 x.fillRect(px-1,py-1,3,3)}
}
function render(d,latency){
 $("ip").textContent=d.ip;$("ssid").textContent=d.ssid;
 $("status").textContent=d.status;
 $("status").className="dot "+(["idle","moving","still","both"][d.state]||"starting");
 const alpha=+$("smoothSetting").value;
 smoothedDistance=alpha?(smoothedDistance?smoothedDistance+(d.distance_cm-smoothedDistance)*alpha:d.distance_cm):d.distance_cm;
 $("inches").textContent=Math.round(smoothedDistance/2.54);
 $("feet").textContent=(smoothedDistance/30.48).toFixed(1);
 $("statusDistance").textContent=feetInches(smoothedDistance);
 $("me").textContent=d.move_energy;$("se").textContent=d.still_energy;
 $("age").textContent=d.age_ms<1500?"now":(d.age_ms/1000).toFixed(1)+" s ago";
 const range=+$("rangeSetting").value,blip=$("blip"),pct=Math.min(100,Math.max(0,smoothedDistance/range*100));
 blip.style.bottom=pct+"%";blip.style.opacity=d.state===0?"0":"1";
 blip.style.color=d.state===2?"var(--purple)":d.state===3?"var(--warn)":"var(--cyan)";
 addEcho(smoothedDistance,d.state,range);
 for(let i=0;i<9;i++){
  const m=Math.min(100,d.move_gates[i]||0),s=Math.min(100,d.still_gates[i]||0);
  $("m"+i).style.width=m+"%";$("mv"+i).textContent=m;
  $("s"+i).style.width=s+"%";$("sv"+i).textContent=s;
  $("hm"+i).style.height=(showMove?m:0)+"%";$("hs"+i).style.height=(showStill?s:0)+"%";
 }
 const now=performance.now(),elapsed=(now-lastFrameTime)/1000;
 if(elapsed>=1){$("fps").textContent=((d.frames-lastFrameCount)/elapsed).toFixed(1)+"/s";
 lastFrameCount=d.frames;lastFrameTime=now}
 $("frames").textContent=d.frames;$("errors").textContent=d.parse_errors;
 $("rssi").textContent=d.rssi==null?"AP mode":d.rssi+" dBm";
 $("latency").textContent=latency===0?"LIVE":Math.round(latency)+" ms";
 $("memory").textContent=d.mem_free==null?"-":Math.round(d.mem_free/1024)+" KB";
 $("timeSync").textContent=d.ntp_synced?"NTP synced":"Not synced";
 const engineering=!!d.engineering_active;
 $("sensorMode").textContent=engineering?"Engineering mode":"Basic mode · retrying";
 $("sensorMode").style.color=engineering?"var(--cyan)":"var(--warn)";
 $("engineeringFrames").textContent=d.engineering_frames||0;
 $("gateWarning").style.display=engineering?"none":"block";
 $("sensorHealth").textContent=d.sensor_stale?"STALE":engineering?"Healthy":"Gate data unavailable";
 $("sensorHealth").style.color=d.sensor_stale?"var(--danger)":engineering?"var(--cyan)":"var(--warn)";
 samples.push({t:Date.now(),d:smoothedDistance,s:d.state});
 while(samples.length&&samples[0].t<Date.now()-+$("historyWindow").value)samples.shift();drawHistory();
 storeHistory(d);updateOccupancy(d);calibrationSample(d);
}
async function update(){
 if(busy||document.hidden)return;busy=true;
 try{
  const started=performance.now();
  const r=await fetch("/api/status?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw Error(r.status);queueRender(await r.json(),performance.now()-started);
  failures=0;$("offline").style.display="none";
 }catch(e){if(++failures>2)$("offline").style.display="block"}
 finally{busy=false}
}
$("smoothSetting").value=prefs.smoothing||".25";$("rangeSetting").value=prefs.range||"609.6";
$("smoothSetting").onchange=savePrefs;$("rangeSetting").onchange=()=>{
 savePrefs();updateRadarLabels();drawHistory()};
$("historyWindow").onchange=loadHistory;
if(prefs.showMove===false)toggleKind("move");if(prefs.showStill===false)toggleKind("still");
if(Array.isArray(prefs.gateVisible))for(let i=0;i<9;i++)if(prefs.gateVisible[i]===false)toggleGate(i);
updateRadarLabels();
for(let i=0;i<9;i++)$("recommendations").insertAdjacentHTML("beforeend",
 `<div class="recommendation"><b>G${i}</b>M -<br>S -</div>`);
openHistoryDb();startStream();
(function fallbackLoop(){if(!streamConnected)update();setTimeout(fallbackLoop,document.hidden?2000:500)})();
addEventListener("resize",drawHistory);
</script>
</body>
</html>
""".replace("__POLL_MS__", str(POLL_MS))


def ticks_age(now, then):
    if not then:
        return 0
    return max(0, time.ticks_diff(now, then))


def ble_advertising_payload(name):
    encoded_name = name.encode()
    return b"\x02\x01\x06" + bytes(
        (len(encoded_name) + 1, 0x09)
    ) + encoded_name


def start_ble_advertising():
    if ble is not None:
        try:
            ble.gap_advertise(
                500000,
                adv_data=ble_advertising_payload("Ryancito Radar"),
            )
        except Exception as error:
            print("BLE advertising failed:", error)


def ble_irq(event, data):
    global ble_pending_command
    if event == 1:
        connection_handle, address_type, address = data
        ble_connections.add(connection_handle)
    elif event == 2:
        connection_handle, address_type, address = data
        ble_connections.discard(connection_handle)
        start_ble_advertising()
    elif event == 3:
        connection_handle, value_handle = data
        if value_handle == ble_command_handle:
            try:
                ble_pending_command = (
                    ble.gatts_read(value_handle).decode().strip()
                )
            except Exception:
                ble_pending_command = ""


def set_ble_info(message):
    if ble is not None and ble_info_handle is not None:
        try:
            ble.gatts_write(ble_info_handle, message.encode())
        except Exception:
            pass


def init_phone_ble(ip):
    global ble, ble_status_handle, ble_info_handle, ble_command_handle
    if bluetooth is None:
        print("BLE peripheral unavailable in this MicroPython build")
        return
    try:
        ble = bluetooth.BLE()
        ble.active(True)
        ble.irq(ble_irq)

        service_uuid = bluetooth.UUID(
            "7A100001-52A1-4DAD-A8B9-21C255D0B700"
        )
        status_uuid = bluetooth.UUID(
            "7A100002-52A1-4DAD-A8B9-21C255D0B700"
        )
        info_uuid = bluetooth.UUID(
            "7A100003-52A1-4DAD-A8B9-21C255D0B700"
        )
        command_uuid = bluetooth.UUID(
            "7A100004-52A1-4DAD-A8B9-21C255D0B700"
        )
        service = (
            service_uuid,
            (
                (
                    status_uuid,
                    bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
                ),
                (info_uuid, bluetooth.FLAG_READ),
                (command_uuid, bluetooth.FLAG_WRITE),
            ),
        )
        ((ble_status_handle, ble_info_handle, ble_command_handle),) = (
            ble.gatts_register_services((service,))
        )
        ble.gatts_set_buffer(ble_info_handle, 128)
        ble.gatts_set_buffer(ble_command_handle, 96)
        ble.gatts_write(ble_status_handle, b"0,0,0,0")
        set_ble_info("Ryancito Radar | " + BUILD_VERSION + " | " + ip)
        start_ble_advertising()
        mode = "protected commands" if BLE_PIN is not None else "read-only"
        print("Phone BLE ready as 'Ryancito Radar' (" + mode + ")")
    except Exception as error:
        ble = None
        print("BLE peripheral initialization failed:", error)


def service_phone_ble():
    global ble_last_frame, ble_pending_command
    if ble is None:
        return

    if radar["frames"] != ble_last_frame:
        ble_last_frame = radar["frames"]
        packet = "{},{},{},{}".format(
            radar["state"],
            radar["distance_cm"],
            radar["move_energy"],
            radar["still_energy"],
        ).encode()
        try:
            ble.gatts_write(ble_status_handle, packet)
            for connection_handle in tuple(ble_connections):
                try:
                    ble.gatts_notify(
                        connection_handle,
                        ble_status_handle,
                        packet,
                    )
                except Exception:
                    ble_connections.discard(connection_handle)
        except Exception:
            pass

    if ble_pending_command is None:
        return
    request = ble_pending_command
    ble_pending_command = None

    if BLE_PIN is None:
        set_ble_info("Commands disabled: BLE_PIN is not configured")
        return
    expected_prefix = str(BLE_PIN) + "|"
    if not request.startswith(expected_prefix):
        set_ble_info("Command rejected")
        return

    command = request[len(expected_prefix):].lower()
    if command == "ping":
        set_ble_info("PONG | " + BUILD_VERSION)
    elif command == "engineering":
        enable_engineering_mode()
        set_ble_info("Engineering mode requested")
    elif command == "reboot":
        set_ble_info("Rebooting")
        time.sleep_ms(250)
        machine.reset()
    else:
        set_ble_info("Unknown command")


def sync_device_time():
    global ntp_synced, ntp_last_sync
    if ntptime is None:
        return
    ntp_last_sync = time.ticks_ms()
    try:
        ntptime.settime()
        ntp_synced = True
        print("NTP time synchronized")
    except Exception as error:
        print("NTP synchronization failed:", error)


def sensor_is_stale():
    if not radar["updated_ms"]:
        return True
    return time.ticks_diff(
        time.ticks_ms(),
        radar["updated_ms"],
    ) > 5000


def engineering_is_stale():
    if not radar["engineering_updated_ms"]:
        return True
    return time.ticks_diff(
        time.ticks_ms(),
        radar["engineering_updated_ms"],
    ) > 5000


def service_sensor_recovery():
    global sensor_last_recovery
    sensor_stale = sensor_is_stale()
    engineering_stale = engineering_is_stale()
    if not sensor_stale and not engineering_stale:
        return
    now = time.ticks_ms()
    if sensor_last_recovery and time.ticks_diff(
        now,
        sensor_last_recovery,
    ) < 10000:
        return
    sensor_last_recovery = now
    if sensor_stale:
        print("Sensor data stale; requesting engineering mode")
    else:
        print("Basic LD2410C frames received; retrying engineering mode for gate data")
    enable_engineering_mode()


def service_time_sync():
    if ntptime is None:
        return
    if not ntp_last_sync or time.ticks_diff(
        time.ticks_ms(),
        ntp_last_sync,
    ) >= 21600000:
        sync_device_time()


def service_udp_telemetry():
    global telemetry_last_state
    if not TELEMETRY_HOST or not radar["frames"]:
        return
    current_state = radar["state"]
    current_signature = (current_state, sensor_is_stale())
    if current_signature == telemetry_last_state:
        return
    telemetry_last_state = current_signature
    event = {
        "source": "ryancito-radar",
        "version": BUILD_VERSION,
        "time": time.time(),
        "state": current_state,
        "status": radar["status"],
        "distance_cm": radar["distance_cm"],
        "move_energy": radar["move_energy"],
        "still_energy": radar["still_energy"],
        "sensor_stale": sensor_is_stale(),
    }
    telemetry_socket = None
    try:
        telemetry_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        telemetry_socket.sendto(
            json.dumps(event).encode(),
            (TELEMETRY_HOST, TELEMETRY_PORT),
        )
    except Exception as error:
        print("UDP telemetry error:", error)
    finally:
        if telemetry_socket:
            try:
                telemetry_socket.close()
            except Exception:
                pass


def metrics_text(wlan, ip):
    try:
        rssi = wlan.status("rssi") if wlan.isconnected() else 0
    except Exception:
        rssi = 0
    free_memory = gc.mem_free() if hasattr(gc, "mem_free") else 0
    lines = (
        "# HELP ryancito_presence Presence detected by the radar.",
        "# TYPE ryancito_presence gauge",
        "ryancito_presence {}".format(1 if radar["state"] else 0),
        "# HELP ryancito_detection_state LD2410 target state 0-3.",
        "# TYPE ryancito_detection_state gauge",
        "ryancito_detection_state {}".format(radar["state"]),
        "# HELP ryancito_distance_cm Current target distance.",
        "# TYPE ryancito_distance_cm gauge",
        "ryancito_distance_cm {}".format(radar["distance_cm"]),
        "# HELP ryancito_uart_frames_total Valid UART frames parsed.",
        "# TYPE ryancito_uart_frames_total counter",
        "ryancito_uart_frames_total {}".format(radar["frames"]),
        "# HELP ryancito_parse_errors_total UART parse errors.",
        "# TYPE ryancito_parse_errors_total counter",
        "ryancito_parse_errors_total {}".format(radar["parse_errors"]),
        "# HELP ryancito_sensor_stale Sensor data older than five seconds.",
        "# TYPE ryancito_sensor_stale gauge",
        "ryancito_sensor_stale {}".format(1 if sensor_is_stale() else 0),
        "# HELP ryancito_wifi_rssi_dbm Wi-Fi signal strength.",
        "# TYPE ryancito_wifi_rssi_dbm gauge",
        "ryancito_wifi_rssi_dbm {}".format(rssi),
        "# HELP ryancito_free_memory_bytes MicroPython free heap.",
        "# TYPE ryancito_free_memory_bytes gauge",
        "ryancito_free_memory_bytes {}".format(free_memory),
        "# HELP ryancito_ntp_synced Whether NTP has synchronized.",
        "# TYPE ryancito_ntp_synced gauge",
        "ryancito_ntp_synced {}".format(1 if ntp_synced else 0),
        'ryancito_build_info{{version="{}",ip="{}"}} 1'.format(
            BUILD_VERSION,
            ip,
        ),
    )
    return "\n".join(lines) + "\n"


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
        radar["engineering_frames"] += 1
        radar["engineering_updated_ms"] = time.ticks_ms()
        for gate in range(9):
            radar["move_gates"][gate] = frame[19 + gate]
            radar["still_gates"][gate] = frame[28 + gate]
    else:
        radar["basic_frames"] += 1

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
        "basic_frames": radar["basic_frames"],
        "engineering_frames": radar["engineering_frames"],
        "engineering_active": not engineering_is_stale(),
        "parse_errors": radar["parse_errors"],
        "ip": ip,
        "ssid": active_ssid,
        "network_mode": network_mode,
        "rssi": wlan.status("rssi") if wlan.isconnected() else None,
        "mem_free": gc.mem_free() if hasattr(gc, "mem_free") else None,
        "ntp_synced": ntp_synced,
        "sensor_stale": sensor_is_stale(),
    }
    return json.dumps(data)

def compact_status(ip, wlan, active_ssid):
    """Small positional packet for the persistent browser stream."""
    return json.dumps([
        radar["state"],
        radar["distance_cm"],
        radar["move_distance_cm"],
        radar["still_distance_cm"],
        radar["move_energy"],
        radar["still_energy"],
        radar["move_gates"],
        radar["still_gates"],
        ticks_age(time.ticks_ms(), radar["updated_ms"]),
        radar["frames"],
        radar["parse_errors"],
        ip,
        active_ssid,
        wlan.status("rssi") if wlan.isconnected() else None,
        gc.mem_free() if hasattr(gc, "mem_free") else None,
        1 if ntp_synced else 0,
        1 if sensor_is_stale() else 0,
        1 if not engineering_is_stale() else 0,
        radar["engineering_frames"],
        radar["basic_frames"],
    ])


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
        return False
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
    elif path == b"/api/stream":
        send_all(
            client,
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/event-stream\r\n"
            b"Cache-Control: no-cache\r\n"
            b"Connection: keep-alive\r\n"
            b"X-Accel-Buffering: no\r\n\r\n"
            b"retry: 1000\r\n\r\n",
        )
        client.settimeout(0.08)
        return True
    elif path == b"/metrics":
        send_response(
            client,
            metrics_text(wlan, ip),
            "text/plain; version=0.0.4; charset=utf-8",
        )
    elif path == b"/favicon.ico":
        send_response(client, b"", "image/x-icon", "204 No Content")
    else:
        send_response(client, "Not found", "text/plain; charset=utf-8", "404 Not Found")
    return False


def run_server(wlan, ip, active_ssid, network_mode):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", WEB_PORT))
    server.listen(4)
    server.settimeout(0)
    print("Radar server running at http://" + ip)

    last_gc = time.ticks_ms()
    last_stream = time.ticks_ms()
    stream_clients = []
    while True:
        service_sensor()
        service_phone_ble()
        service_sensor_recovery()
        service_time_sync()
        service_udp_telemetry()
        if watchdog is not None:
            watchdog.feed()
        client = None
        try:
            client, _ = server.accept()
        except OSError:
            pass

        if client:
            keep_open = False
            try:
                keep_open = handle_client(client, ip, wlan, active_ssid, network_mode)
                if keep_open:
                    if len(stream_clients) >= 2:
                        old_client = stream_clients.pop(0)
                        try:
                            old_client.close()
                        except Exception:
                            pass
                    stream_clients.append(client)
            except OSError as error:
                # Browser cancellations and timeouts are routine during polling.
                error_number = error.args[0] if error.args else None
                if error_number not in (11, 104, 110, 116, 128):
                    print("Client socket error:", error)
            except Exception as error:
                print("Client error:", error)
            finally:
                if not keep_open:
                    try:
                        client.close()
                    except Exception:
                        pass

        now = time.ticks_ms()
        if stream_clients and time.ticks_diff(now, last_stream) >= 100:
            event = ("data:" + compact_status(ip, wlan, active_ssid) + "\n\n").encode()
            live_clients = []
            for stream_client in stream_clients:
                try:
                    send_all(stream_client, event)
                    live_clients.append(stream_client)
                except Exception:
                    try:
                        stream_client.close()
                    except Exception:
                        pass
            stream_clients = live_clients
            last_stream = now
        if time.ticks_diff(now, last_gc) >= 30000:
            gc.collect()
            last_gc = now
        time.sleep_ms(5)


def main():
    global watchdog
    print("Ryancito Presence Radar build:", BUILD_VERSION)
    wlan, _ap, ip, active_ssid, network_mode = connect_wifi()
    enable_engineering_mode()
    init_phone_ble(ip)
    sync_device_time()
    try:
        watchdog = machine.WDT(timeout=30000)
        print("Hardware watchdog enabled")
    except Exception as error:
        print("Watchdog unavailable:", error)
    time.sleep_ms(400)
    run_server(wlan, ip, active_ssid, network_mode)


try:
    main()
except Exception as fatal:
    print("Fatal error:", fatal)
    raise
