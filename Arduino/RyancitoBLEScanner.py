# main.py - Ryancito BLE Site Survey Tool
# Arduino Nano ESP32 (ESP32-S3), MicroPython with bluetooth support
#
# Passive scanner only: this program listens for BLE advertisements.

import bluetooth
import gc
import machine
import network
import socket
import struct
import sys
import time
import ubinascii

# ========================== CONFIGURATION ==========================
try:
    from secret import HOME_SSID, HOME_PASSWORD, AP_SSID, AP_PASSWORD
except ImportError:
    HOME_SSID = "CHANGE_ME"
    HOME_PASSWORD = "CHANGE_ME"
    AP_SSID = "Ryancito-BLE"
    AP_PASSWORD = "ryancito1337"

HTTP_PORT = 80
CONNECT_TIMEOUT_MS = 12_000
CLIENT_TIMEOUT_SECONDS = 5
AP_CHANNEL = 6

SCAN_SECONDS = 8
SCAN_INTERVAL_US = 30_000
SCAN_WINDOW_US = 30_000
ACTIVE_SCAN = True
MAX_DEVICES = 80

# Approximate BLE proximity thresholds. RSSI is affected by walls, antennas,
# pockets, orientation, and interference, so these are zones—not measurements.
RSSI_15_FEET = -75
RSSI_10_FEET = -70
RSSI_5_FEET = -62
RSSI_NEXT_TO = -50

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
ble = bluetooth.BLE()
devices = {}
scan_done = False
strongest_rssi = -127

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_SHORT_NAME = const(0x08)
_ADV_TYPE_SERVICE_UUID_16_COMPLETE = const(0x03)
_ADV_TYPE_SERVICE_UUID_16_MORE = const(0x02)
_ADV_TYPE_SERVICE_UUID_128_COMPLETE = const(0x07)
_ADV_TYPE_SERVICE_UUID_128_MORE = const(0x06)
_ADV_TYPE_MANUFACTURER = const(0xFF)

COMPANY_NAMES = {
    0x004C: "Apple",
    0x0006: "Microsoft",
    0x000F: "Broadcom",
    0x0059: "Nordic Semiconductor",
    0x0075: "Samsung",
    0x00E0: "Google",
    0x0131: "Cypress",
    0x0499: "Ruuvi",
}

SERVICE_NAMES = {
    0x1800: "Generic Access",
    0x1801: "Generic Attribute",
    0x1809: "Health Thermometer",
    0x180A: "Device Information",
    0x180D: "Heart Rate",
    0x180F: "Battery",
    0x1812: "Human Interface Device",
    0x181A: "Environmental Sensing",
}


def print_exception(label, exception):
    print(label)
    sys.print_exception(exception)


def clamp_8bit(value):
    value = int(value)
    if value < 0:
        return 0
    if value > 255:
        return 255
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


def html_escape(value):
    return (str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def format_bytes(num):
    num = int(num)
    if num < 1024:
        return "{} B".format(num)
    if num < 1024 * 1024:
        return "{:.1f} KB".format(num / 1024)
    return "{:.2f} MB".format(num / (1024 * 1024))


def format_mac(addr):
    value = ubinascii.hexlify(bytes(addr)).decode().upper()
    return ":".join(value[i:i + 2] for i in range(0, 12, 2))


def address_type_name(addr_type):
    return {
        0: "Public",
        1: "Random",
        2: "Public ID",
        3: "Random ID",
    }.get(addr_type, "Type {}".format(addr_type))


def signal_bar(rssi):
    if rssi >= -45:
        return "█████"
    if rssi >= -55:
        return "████ "
    if rssi >= -65:
        return "███  "
    if rssi >= -75:
        return "██   "
    if rssi >= -85:
        return "█    "
    return "     "


def proximity_from_rssi(rssi):
    if rssi < RSSI_15_FEET:
        return "Beyond ~15 ft", "off"
    if rssi < RSSI_10_FEET:
        return "Around 15 ft", "red"
    if rssi < RSSI_5_FEET:
        return "Around 10 ft", "yellow"
    if rssi < RSSI_NEXT_TO:
        return "Around 5 ft", "green"
    return "Right next to it", "blue"


def set_proximity_led(rssi):
    zone, color = proximity_from_rssi(rssi)
    if color == "red":
        set_rgb(255, 0, 0)
    elif color == "yellow":
        set_rgb(255, 150, 0)
    elif color == "green":
        set_rgb(0, 255, 0)
    elif color == "blue":
        set_rgb(0, 0, 255)
    else:
        led_off()
    return zone


def decode_field(payload, wanted_type):
    i = 0
    while i + 1 < len(payload):
        length = payload[i]
        if length == 0:
            break
        end = i + length + 1
        if end > len(payload):
            break
        if payload[i + 1] == wanted_type:
            return payload[i + 2:end]
        i = end
    return None


def decode_name(payload):
    raw = decode_field(payload, _ADV_TYPE_NAME)
    if raw is None:
        raw = decode_field(payload, _ADV_TYPE_SHORT_NAME)
    if not raw:
        return ""
    try:
        return raw.decode("utf-8", "ignore")
    except Exception:
        return ""


def decode_manufacturer(payload):
    raw = decode_field(payload, _ADV_TYPE_MANUFACTURER)
    if not raw or len(raw) < 2:
        return "", ""
    company_id = struct.unpack("<H", raw[:2])[0]
    name = COMPANY_NAMES.get(company_id, "Company 0x{:04X}".format(company_id))
    data = ubinascii.hexlify(raw[2:]).decode().upper()
    if len(data) > 28:
        data = data[:28] + "..."
    return name, data


def decode_services(payload):
    names = []
    for adv_type in (_ADV_TYPE_SERVICE_UUID_16_COMPLETE,
                     _ADV_TYPE_SERVICE_UUID_16_MORE):
        raw = decode_field(payload, adv_type)
        if raw:
            for i in range(0, len(raw) - 1, 2):
                uuid = struct.unpack("<H", raw[i:i + 2])[0]
                names.append(SERVICE_NAMES.get(uuid, "0x{:04X}".format(uuid)))

    for adv_type in (_ADV_TYPE_SERVICE_UUID_128_COMPLETE,
                     _ADV_TYPE_SERVICE_UUID_128_MORE):
        raw = decode_field(payload, adv_type)
        if raw:
            for i in range(0, len(raw) - 15, 16):
                short = ubinascii.hexlify(raw[i:i + 16]).decode().upper()
                names.append(short[:8] + "...")
    return ", ".join(names)


def ble_irq(event, data):
    global scan_done, strongest_rssi
    if event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv_data = data
        mac = format_mac(addr)
        payload = bytes(adv_data)
        name = decode_name(payload)
        manufacturer, manufacturer_data = decode_manufacturer(payload)
        services = decode_services(payload)

        # The strongest signal is normally the closest observed transmitter.
        # Require a 2 dBm improvement to reduce rapid color flicker.
        if rssi >= strongest_rssi + 2:
            strongest_rssi = int(rssi)
            set_proximity_led(strongest_rssi)

        old = devices.get(mac)
        if old is None:
            devices[mac] = {
                "mac": mac,
                "type": address_type_name(addr_type),
                "name": name,
                "rssi": int(rssi),
                "best_rssi": int(rssi),
                "manufacturer": manufacturer,
                "manufacturer_data": manufacturer_data,
                "services": services,
                "seen": 1,
            }
        else:
            old["rssi"] = int(rssi)
            if rssi > old["best_rssi"]:
                old["best_rssi"] = int(rssi)
            old["seen"] += 1
            if name:
                old["name"] = name
            if manufacturer:
                old["manufacturer"] = manufacturer
                old["manufacturer_data"] = manufacturer_data
            if services:
                old["services"] = services

    elif event == _IRQ_SCAN_DONE:
        scan_done = True


def scan_devices():
    global devices, scan_done, strongest_rssi
    devices = {}
    scan_done = False
    strongest_rssi = -127
    gc.collect()
    set_rgb(50, 0, 80)
    orange_off()
    print("Scanning for BLE advertisements for {} seconds...".format(
        SCAN_SECONDS))

    try:
        ble.active(True)
        ble.irq(ble_irq)
        ble.gap_scan(
            SCAN_SECONDS * 1000,
            SCAN_INTERVAL_US,
            SCAN_WINDOW_US,
            ACTIVE_SCAN,
        )

        deadline = time.ticks_add(
            time.ticks_ms(), (SCAN_SECONDS * 1000) + 2000)
        blink = False
        while not scan_done and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            blink = not blink
            orange.value(1 if blink else 0)
            time.sleep_ms(100)

        try:
            ble.gap_scan(None)
        except Exception:
            pass

        result = list(devices.values())
        result.sort(key=lambda item: item["best_rssi"], reverse=True)
        print("Found {} BLE devices.".format(len(result)))
        if result:
            zone = set_proximity_led(result[0]["best_rssi"])
            print("Strongest signal:", result[0]["best_rssi"], "dBm ->", zone)
        return result[:MAX_DEVICES], None
    except Exception as e:
        print_exception("BLE scan failed:", e)
        return [], str(e)
    finally:
        orange_on()
        if strongest_rssi < RSSI_15_FEET:
            led_off()
        gc.collect()


def start_survey_ap():
    print("Starting BLE survey access point...")
    try:
        sta.disconnect()
    except Exception:
        pass
    ap.active(False)
    time.sleep_ms(200)
    ap.active(True)

    if len(AP_PASSWORD) < 8:
        print("WARNING: AP_PASSWORD is shorter than 8 characters.")
        print("Starting an OPEN fallback access point.")
        try:
            ap.config(essid=AP_SSID, authmode=network.AUTH_OPEN,
                      channel=AP_CHANNEL)
        except Exception:
            ap.config(ssid=AP_SSID, channel=AP_CHANNEL)
    else:
        try:
            ap.config(
                essid=AP_SSID,
                password=AP_PASSWORD,
                authmode=network.AUTH_WPA2_PSK,
                channel=AP_CHANNEL,
            )
        except Exception:
            try:
                ap.config(
                    ssid=AP_SSID,
                    password=AP_PASSWORD,
                    channel=AP_CHANNEL,
                )
            except Exception:
                ap.config(
                    ssid=AP_SSID,
                    key=AP_PASSWORD,
                    channel=AP_CHANNEL,
                )

    orange_on()
    print("AP started:", AP_SSID, ap.ifconfig()[0])


def connect_to_home():
    if not HOME_SSID or HOME_SSID == "CHANGE_ME":
        return False

    print("Connecting to home Wi-Fi:", HOME_SSID)
    set_rgb(0, 0, 80)
    sta.active(True)
    try:
        sta.config(reconnects=3)
    except Exception:
        pass

    try:
        sta.connect(HOME_SSID, HOME_PASSWORD)
    except Exception as e:
        print_exception("Home Wi-Fi connection failed:", e)
        led_off()
        return False

    deadline = time.ticks_add(time.ticks_ms(), CONNECT_TIMEOUT_MS)
    blink = False
    while not sta.isconnected() and time.ticks_diff(
            deadline, time.ticks_ms()) > 0:
        blink = not blink
        orange.value(1 if blink else 0)
        time.sleep_ms(200)

    orange_off()
    led_off()
    if sta.isconnected():
        print("Connected to home Wi-Fi:", sta.ifconfig()[0])
        orange_on()
        return True

    print("Could not connect to home Wi-Fi.")
    return False


def configure_wifi():
    global in_ap_mode
    try:
        ap.active(False)
    except Exception:
        pass
    try:
        sta.active(False)
    except Exception:
        pass
    time.sleep_ms(250)

    if connect_to_home():
        in_ap_mode = False
    else:
        start_survey_ap()
        in_ap_mode = True


def active_interface():
    return ap if in_ap_mode else sta


def get_device_status():
    iface = active_interface()
    try:
        ip = iface.ifconfig()[0]
    except Exception:
        ip = "Unavailable"
    try:
        mac = format_mac(iface.config("mac"))
    except Exception:
        mac = "Unavailable"
    try:
        fw = "MP " + ".".join(map(str, sys.implementation.version[:3]))
    except Exception:
        fw = "MicroPython"

    return {
        "mode": ("Fallback AP + passive BLE survey" if in_ap_mode
                 else "Home Wi-Fi + passive BLE survey"),
        "ssid": AP_SSID if in_ap_mode else HOME_SSID,
        "mac": mac,
        "ip": ip,
        "scan_time": "{} seconds".format(SCAN_SECONDS),
        "active_scan": "Yes" if ACTIVE_SCAN else "No",
        "board": "Arduino Nano ESP32",
        "firmware": fw,
        "heap": format_bytes(gc.mem_free()),
        "uptime": "{} seconds".format(
            time.ticks_diff(time.ticks_ms(), BOOT_MS) // 1000),
    }


def build_device_rows(found):
    rows = []
    for item in found:
        name = item["name"] or "Unnamed"
        details = []
        if item["manufacturer"]:
            details.append(item["manufacturer"])
        if item["services"]:
            details.append(item["services"])
        if not details:
            details.append("No decoded data")
        proximity, color = proximity_from_rssi(item["best_rssi"])

        rows.append(
            "<tr>"
            "<td>{}</td><td>{}</td><td class='bar'>{}</td>"
            "<td><span class='dot {}'></span>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "</tr>".format(
                html_escape(name),
                item["best_rssi"],
                html_escape(signal_bar(item["best_rssi"])),
                color,
                html_escape(proximity),
                item["seen"],
                html_escape(item["type"]),
                html_escape(item["mac"]),
                html_escape(" | ".join(details)),
            )
        )
    if not rows:
        rows.append(
            "<tr><td colspan='8' class='center'>No BLE devices found</td></tr>")
    return "".join(rows)


def build_html(found, scan_error=None):
    status = get_device_status()
    error_html = ""
    if scan_error:
        error_html = (
            "<div class='error'><strong>Scan error:</strong> {}</div>"
            .format(html_escape(scan_error)))

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ryancito BLE Survey</title>
<style>
body{{background:#05070c;color:#00fff7;font-family:monospace;margin:0}}
.header{{text-align:center;padding:16px;border-bottom:1px solid rgba(0,255,247,.2);font-size:1.35em;font-weight:bold;text-shadow:0 0 10px #00fff7}}
.container{{max-width:1100px;margin:0 auto;padding:16px 12px 40px}}
.card{{background:#0a0e16;border:1px solid rgba(0,255,247,.3);border-radius:12px;padding:16px;margin-bottom:16px}}
h2{{color:#b967ff;font-size:1.1em;margin:0 0 14px}}
.status-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}}
.status-col strong{{color:#b967ff;display:block;font-size:.78em;margin-bottom:2px}}
.status-col div{{margin-bottom:10px;font-size:.95em}}
table{{width:100%;border-collapse:collapse;font-size:.86em}}
th,td{{padding:8px 6px;border-bottom:1px solid rgba(0,255,247,.1);text-align:left}}
th{{color:#b967ff;background:rgba(185,103,255,.1)}}
.bar{{white-space:pre;letter-spacing:-1px}}
.center{{text-align:center;padding:18px}}
.error{{border:1px solid #ff6b6b;color:#ffaaaa;padding:10px;border-radius:8px;margin-bottom:16px}}
.note{{opacity:.65;font-size:.84em;line-height:1.5}}
.legend{{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0 14px;font-size:.84em}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;box-shadow:0 0 8px currentColor}}
.dot.red{{background:#ff334d;color:#ff334d}}
.dot.yellow{{background:#ffd23f;color:#ffd23f}}
.dot.green{{background:#2cff88;color:#2cff88}}
.dot.blue{{background:#3f8cff;color:#3f8cff}}
.dot.off{{background:#555;color:#555}}
.btn-row{{text-align:center;margin-top:10px}}
.btn{{display:inline-block;text-decoration:none;color:#00fff7;border:2px solid #00fff7;padding:10px 22px;border-radius:8px;margin:5px;background:transparent;font-family:inherit;font-size:1em;cursor:pointer}}
.footer{{text-align:center;padding:14px;font-size:.8em;opacity:.45}}
@media(max-width:650px){{.status-grid{{grid-template-columns:1fr}}}}
@media print{{
body{{background:white!important;color:black!important}}
.header{{color:black!important;text-shadow:none!important;border-color:#444!important}}
.card{{background:white!important;border:1px solid #666!important;color:black!important}}
h2,.status-col strong{{color:#333!important}}
th{{background:#eee!important;color:black!important}}
td,.bar{{color:black!important}}
.btn{{display:none!important}}
}}
</style>
</head>
<body>
<div class="header">Ryancito BLE Site Survey</div>
<div class="container">
{error_html}
<div class="card">
<h2>Status</h2>
<div class="status-grid">
  <div class="status-col">
    <div><strong>Mode</strong>{mode}</div>
    <div><strong>Access Point</strong>{ssid}</div>
    <div><strong>IP</strong>{ip}</div>
  </div>
  <div class="status-col">
    <div><strong>Scan Length</strong>{scan_time}</div>
    <div><strong>Active Scan</strong>{active_scan}</div>
    <div><strong>Uptime</strong>{uptime}</div>
  </div>
  <div class="status-col">
    <div><strong>Board</strong>{board}</div>
    <div><strong>Firmware</strong>{firmware}</div>
    <div><strong>Free Heap</strong>{heap}</div>
  </div>
</div>
</div>

<div class="card">
<h2>Nearby BLE Devices ({count} found)</h2>
<div class="legend">
<span><i class="dot red"></i>~15 ft</span>
<span><i class="dot yellow"></i>~10 ft</span>
<span><i class="dot green"></i>~5 ft</span>
<span><i class="dot blue"></i>right next to it</span>
<span><i class="dot off"></i>beyond ~15 ft</span>
</div>
<div style="overflow-x:auto">
<table>
<thead><tr><th>Name</th><th>RSSI</th><th>Signal</th><th>Proximity</th><th>Seen</th><th>Address Type</th><th>Address</th><th>Advertisement Details</th></tr></thead>
<tbody>{device_rows}</tbody>
</table>
</div>
<p class="note">Many modern devices rotate randomized BLE addresses. A sighting is an observation, not proof of a person's identity or continued presence. Use only where scanning is permitted.</p>
</div>

<div class="btn-row">
<a class="btn" href="/">Rescan</a>
<button class="btn" onclick="window.print()">Print</button>
</div>
</div>
<div class="footer">Ryancito Passive BLE Site Survey Tool</div>
</body>
</html>""".format(
        error_html=error_html,
        mode=html_escape(status["mode"]),
        ssid=html_escape(status["ssid"]),
        ip=html_escape(status["ip"]),
        scan_time=html_escape(status["scan_time"]),
        active_scan=html_escape(status["active_scan"]),
        uptime=html_escape(status["uptime"]),
        board=html_escape(status["board"]),
        firmware=html_escape(status["firmware"]),
        heap=html_escape(status["heap"]),
        count=len(found),
        device_rows=build_device_rows(found),
    )


def send_response(client, status, content_type, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = (
        "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\n"
        "Connection: close\r\n\r\n"
    ).format(status, content_type, len(body))
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
    except Exception:
        return None, None


def handle_client(client, addr):
    try:
        client.settimeout(CLIENT_TIMEOUT_SECONDS)
    except Exception:
        pass

    try:
        method, path = read_request(client)
    except OSError as e:
        if e.args and e.args[0] in (110, 116, 104, 11, 128):
            return
        print("Request error from", addr, "->", e)
        return
    except Exception as e:
        print("Request error from", addr, "->", e)
        return

    if method != "GET":
        send_response(client, "405 Method Not Allowed", "text/plain",
                      "Only GET\n")
        return
    if path == "/favicon.ico":
        send_response(client, "204 No Content", "image/x-icon", b"")
        return
    if path != "/":
        send_response(client, "404 Not Found", "text/plain", "Not found\n")
        return

    print("GET / from", addr)
    found, error = scan_devices()
    send_response(
        client,
        "200 OK",
        "text/html; charset=utf-8",
        build_html(found, error),
    )


def serve_forever():
    while True:
        server = None
        try:
            addr = socket.getaddrinfo("0.0.0.0", HTTP_PORT)[0][-1]
            server = socket.socket()
            try:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            server.bind(addr)
            server.listen(3)
            ip = active_interface().ifconfig()[0]
            print("Server ready -> http://{}:{}/".format(ip, HTTP_PORT))

            while True:
                client = None
                try:
                    client, remote = server.accept()
                    handle_client(client, remote)
                except KeyboardInterrupt:
                    raise
                except OSError as e:
                    if not (e.args and e.args[0] in
                            (110, 116, 104, 11, 128)):
                        print_exception("Request error:", e)
                except Exception as e:
                    print_exception("Request error:", e)
                finally:
                    if client:
                        try:
                            client.close()
                        except Exception:
                            pass
                    gc.collect()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print_exception("Server error:", e)
            time.sleep_ms(1000)
        finally:
            if server:
                try:
                    server.close()
                except Exception:
                    pass


def main():
    orange_off()
    led_off()
    ble.active(True)
    ble.irq(ble_irq)
    configure_wifi()
    serve_forever()


try:
    main()
except KeyboardInterrupt:
    print("\nStopped.")
except Exception as e:
    print_exception("Fatal:", e)
finally:
    try:
        ble.gap_scan(None)
        ble.active(False)
    except Exception:
        pass
    led_off()
    orange_off()
