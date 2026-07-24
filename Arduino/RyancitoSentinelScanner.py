# main.py - RyancitoSentinal Wireless Survey Tool
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
    AP_SSID = "RyancitoSentinal"
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
MAX_NETWORKS = 64

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
previous_ble_rssi = {}
previous_wifi_rssi = {}

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


def get_network_constant(name):
    for owner in (sta, ap, network.WLAN, network):
        try:
            return getattr(owner, name)
        except (AttributeError, TypeError):
            pass
    return None


def build_security_map():
    result = {
        0: "Open",
        1: "WEP",
        2: "WPA",
        3: "WPA2",
        4: "WPA/WPA2",
    }
    known = (
        ("SEC_OPEN", "Open"),
        ("SEC_WEP", "WEP"),
        ("SEC_WPA", "WPA"),
        ("SEC_WPA2", "WPA2"),
        ("SEC_WPA_WPA2", "WPA/WPA2"),
        ("SEC_WPA3", "WPA3"),
        ("SEC_WPA2_WPA3", "WPA2/WPA3"),
    )
    for constant, label in known:
        value = get_network_constant(constant)
        if value is not None:
            result[value] = label
    return result


SECURITY_MAP = build_security_map()


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


def security_name(authmode):
    return SECURITY_MAP.get(
        authmode, "Unknown ({})".format(authmode))


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


def signal_trend(previous_rssi, current_rssi):
    if previous_rssi is None:
        return "NEW", "trend-new"
    change = current_rssi - previous_rssi
    if change >= 4:
        return "↑ CLOSER (+{} dB)".format(change), "trend-up"
    if change <= -4:
        return "↓ FARTHER ({} dB)".format(change), "trend-down"
    return "→ STEADY ({:+d} dB)".format(change), "trend-steady"


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
    global devices, scan_done, strongest_rssi, previous_ble_rssi
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
        current_rssi = {}
        for item in result:
            label, style = signal_trend(
                previous_ble_rssi.get(item["mac"]), item["best_rssi"])
            item["trend"] = label
            item["trend_style"] = style
            current_rssi[item["mac"]] = item["best_rssi"]
        previous_ble_rssi = current_rssi
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


def scan_wifi_networks():
    global previous_wifi_rssi
    print("Scanning for Wi-Fi networks...")
    gc.collect()
    try:
        sta.active(True)
        raw_results = sta.scan()
    except Exception as e:
        print_exception("Wi-Fi scan failed:", e)
        return [], str(e)

    found = []
    for result in raw_results:
        try:
            raw_ssid = result[0]
            bssid = result[1]
            channel = int(result[2])
            rssi = int(result[3])
            authmode = result[4] if len(result) > 4 else -1
            hidden = bool(result[5]) if len(result) > 5 else not raw_ssid
            try:
                ssid = raw_ssid.decode("utf-8", "ignore")
            except Exception:
                ssid = str(raw_ssid)
            if not ssid:
                ssid = "Hidden"
                hidden = True

            found.append({
                "ssid": ssid,
                "bssid": format_mac(bssid),
                "channel": channel,
                "rssi": rssi,
                "security": security_name(authmode),
                "hidden": hidden,
            })
        except Exception as e:
            print_exception("Bad Wi-Fi scan result:", e)

    found.sort(key=lambda item: item["rssi"], reverse=True)
    current_rssi = {}
    for item in found:
        label, style = signal_trend(
            previous_wifi_rssi.get(item["bssid"]), item["rssi"])
        item["trend"] = label
        item["trend_style"] = style
        current_rssi[item["bssid"]] = item["rssi"]
    previous_wifi_rssi = current_rssi
    print("Found {} Wi-Fi networks.".format(len(found)))
    return found[:MAX_NETWORKS], None


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
        "mode": ("Fallback AP + Wi-Fi/BLE survey" if in_ap_mode
                 else "Home network + Wi-Fi/BLE survey"),
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
            "<tr class='survey-row' data-radio='ble' data-rssi='{}' "
            "data-device-id='ble:{}'>"
            "<td>{}</td><td>{}</td><td class='bar'>{}</td>"
            "<td class='{}'>{}</td>"
            "<td><span class='dot {}'></span>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td class='ignore-cell'><label><input class='ignore-box' "
            "type='checkbox'> Ignore</label></td>"
            "</tr>".format(
                item["best_rssi"],
                html_escape(item["mac"]),
                html_escape(name),
                item["best_rssi"],
                html_escape(signal_bar(item["best_rssi"])),
                item["trend_style"],
                html_escape(item["trend"]),
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
            "<tr><td colspan='10' class='center'>No BLE devices found</td></tr>")
    return "".join(rows)


def build_wifi_rows(networks):
    rows = []
    for item in networks:
        hidden = " <span class='muted'>(hidden)</span>" if item["hidden"] else ""
        rows.append(
            "<tr class='survey-row' data-radio='wifi' data-rssi='{}' "
            "data-device-id='wifi:{}'>"
            "<td>{}{}</td><td>{}</td><td class='bar'>{}</td>"
            "<td class='{}'>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td>"
            "<td class='ignore-cell'><label><input class='ignore-box' "
            "type='checkbox'> Ignore</label></td></tr>".format(
                item["rssi"],
                html_escape(item["bssid"]),
                html_escape(item["ssid"]),
                hidden,
                item["rssi"],
                html_escape(signal_bar(item["rssi"])),
                item["trend_style"],
                html_escape(item["trend"]),
                item["channel"],
                html_escape(item["security"]),
                html_escape(item["bssid"]),
            )
        )
    if not rows:
        rows.append(
            "<tr><td colspan='8' class='center'>No Wi-Fi networks found</td></tr>")
    return "".join(rows)


def build_html(found, wifi_networks, scan_error=None, wifi_error=None):
    status = get_device_status()
    error_html = ""
    if scan_error:
        error_html = (
            "<div class='error'><strong>BLE scan error:</strong> {}</div>"
            .format(html_escape(scan_error)))
    if wifi_error:
        error_html += (
            "<div class='error'><strong>Wi-Fi scan error:</strong> {}</div>"
            .format(html_escape(wifi_error)))

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RyancitoSentinal</title>
<style>
body{{background:#05070c;color:#00fff7;font-family:monospace;margin:0}}
.header{{text-align:center;padding:16px;border-bottom:1px solid rgba(0,255,247,.2);font-size:1.35em;font-weight:bold;text-shadow:0 0 10px #00fff7}}
.settings-open{{position:absolute;right:12px;top:10px;color:#00fff7;background:#0a0e16;border:1px solid #00fff7;border-radius:9px;padding:7px 11px;font:inherit;cursor:pointer}}
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
.muted{{opacity:.55;font-size:.8em}}
.error{{border:1px solid #ff6b6b;color:#ffaaaa;padding:10px;border-radius:8px;margin-bottom:16px}}
.note{{opacity:.65;font-size:.84em;line-height:1.5}}
.legend{{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0 14px;font-size:.84em}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;box-shadow:0 0 8px currentColor}}
.dot.red{{background:#ff334d;color:#ff334d}}
.dot.yellow{{background:#ffd23f;color:#ffd23f}}
.dot.green{{background:#2cff88;color:#2cff88}}
.dot.blue{{background:#3f8cff;color:#3f8cff}}
.dot.off{{background:#555;color:#555}}
.trend-new{{color:#b967ff;font-weight:bold;white-space:nowrap}}
.trend-up{{color:#2cff88;font-weight:bold;white-space:nowrap}}
.trend-down{{color:#ff5c70;font-weight:bold;white-space:nowrap}}
.trend-steady{{color:#00fff7;white-space:nowrap}}
.ignore-tools{{text-align:right;margin:-4px 0 10px;font-size:.84em}}
.ignored-row{{display:none}}
.show-ignored .ignored-row{{display:table-row;opacity:.35}}
.show-ignored .ignored-row td{{text-decoration:line-through}}
.section-hidden{{display:none!important}}
.compact .card{{padding:9px;margin-bottom:9px}}
.compact th,.compact td{{padding:4px 3px}}
.settings-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.62);opacity:0;pointer-events:none;transition:opacity .2s;z-index:20}}
.settings-drawer{{position:fixed;right:0;top:0;height:100%;width:min(360px,88vw);box-sizing:border-box;background:#090d15;border-left:1px solid rgba(0,255,247,.4);padding:18px;transform:translateX(105%);transition:transform .25s;z-index:21;overflow-y:auto;box-shadow:-10px 0 30px rgba(0,0,0,.5)}}
.settings-visible .settings-overlay{{opacity:1;pointer-events:auto}}
.settings-visible .settings-drawer{{transform:translateX(0)}}
.settings-title{{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}}
.settings-title h2{{margin:0;font-size:1.2em}}
.settings-close{{color:#00fff7;background:transparent;border:0;font-size:1.7em;cursor:pointer}}
.setting{{display:flex;justify-content:space-between;align-items:center;gap:15px;padding:12px 0;border-bottom:1px solid rgba(0,255,247,.12)}}
.setting span{{color:#e8ffff}}
.setting small{{display:block;color:#7da5aa;margin-top:3px}}
.setting select{{background:#111827;color:#00fff7;border:1px solid #31545a;border-radius:6px;padding:7px}}
.toggle{{width:42px;height:23px;accent-color:#b967ff}}
.scan-status{{position:fixed;right:12px;bottom:12px;background:#0a0e16;border:1px solid rgba(0,255,247,.45);border-radius:9px;padding:8px 11px;font-size:.78em;z-index:10;display:none}}
.auto-active .scan-status{{display:block}}
.btn-row{{text-align:center;margin-top:10px}}
.btn{{display:inline-block;text-decoration:none;color:#00fff7;border:2px solid #00fff7;padding:10px 22px;border-radius:8px;margin:5px;background:transparent;font-family:inherit;font-size:1em;cursor:pointer}}
.footer{{text-align:center;padding:14px;font-size:.8em;opacity:.45}}
@media(max-width:650px){{.status-grid{{grid-template-columns:1fr}}}}
@page{{size:landscape;margin:.35in}}
@media print{{
*{{text-shadow:none!important;box-shadow:none!important}}
html,body{{width:100%!important;margin:0!important;padding:0!important}}
body{{background:white!important;color:black!important;font-size:8pt!important;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}}
.header{{color:black!important;text-shadow:none!important;border-color:black!important;padding:6px!important;font-size:13pt!important}}
.container{{max-width:none!important;width:100%!important;margin:0!important;padding:6px 0 0!important}}
.card{{background:white!important;border:1px solid black!important;color:black!important;border-radius:0!important;padding:7px!important;margin-bottom:7px!important}}
h2,.status-col strong{{color:#333!important}}
h2{{font-size:10pt!important;margin-bottom:6px!important}}
.status-grid{{gap:8px!important}}
.status-col div{{margin-bottom:3px!important;font-size:8pt!important}}
th{{background:#eee!important;color:black!important}}
table{{border:1px solid black!important;width:100%!important;table-layout:auto!important;font-size:7pt!important}}
thead{{display:table-header-group}}
tr{{break-inside:avoid!important;page-break-inside:avoid!important}}
th,td{{color:black!important;border-bottom:1px solid black!important;padding:3px 2px!important;overflow-wrap:anywhere!important;word-break:break-word!important}}
.bar{{color:black!important}}
.note{{margin:5px 0 0!important;font-size:7pt!important}}
.legend{{margin:4px 0 6px!important;gap:8px!important;font-size:7pt!important}}
.note,.muted,.footer{{color:black!important;opacity:1!important}}
.footer{{padding:5px!important;font-size:7pt!important}}
.dot{{border:1px solid black!important;box-shadow:none!important;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}}
.dot.red{{background:#ff0000!important;color:#ff0000!important}}
.dot.yellow{{background:#ffff00!important;color:#ffff00!important}}
.dot.green{{background:#00b83f!important;color:#00b83f!important}}
.dot.blue{{background:#0066ff!important;color:#0066ff!important}}
.dot.off{{background:#777!important;color:#777!important}}
.trend-new,.trend-up,.trend-down,.trend-steady{{color:black!important}}
.ignore-cell,.ignore-tools{{display:none!important}}
.ignored-row{{display:none!important}}
.btn,.settings-open,.settings-drawer,.settings-overlay,.scan-status{{display:none!important}}
}}
</style>
</head>
<body>
<div class="header">RyancitoSentinal — Wi-Fi + BLE Survey
<button class="settings-open" id="settings-open" type="button" aria-label="Open settings">⚙ Settings</button>
</div>
<div class="container">
{error_html}
<div class="card status-card">
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

<div class="card wifi-card">
<h2>Nearby Wi-Fi Networks ({wifi_count} found)</h2>
<div class="ignore-tools"><label><input class="show-ignored-box" type="checkbox"> Show ignored</label></div>
<div style="overflow-x:auto">
<table>
<thead><tr><th>SSID</th><th>RSSI</th><th>Signal</th><th>Trend</th><th>Channel</th><th>Security</th><th>BSSID</th><th>Filter</th></tr></thead>
<tbody>{wifi_rows}</tbody>
</table>
</div>
<p class="note">Security is the authentication mode advertised by the access point. It does not prove that a network or its connected devices are trustworthy.</p>
</div>

<div class="card ble-card">
<h2>Nearby BLE Devices ({count} found)</h2>
<div class="ignore-tools"><label><input class="show-ignored-box" type="checkbox"> Show ignored</label></div>
<div class="legend">
<span><i class="dot red"></i>~15 ft</span>
<span><i class="dot yellow"></i>~10 ft</span>
<span><i class="dot green"></i>~5 ft</span>
<span><i class="dot blue"></i>right next to it</span>
<span><i class="dot off"></i>beyond ~15 ft</span>
</div>
<div style="overflow-x:auto">
<table>
<thead><tr><th>Name</th><th>RSSI</th><th>Signal</th><th>Trend</th><th>Proximity</th><th>Seen</th><th>Address Type</th><th>Address</th><th>Advertisement Details</th><th>Filter</th></tr></thead>
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
<div class="footer">RyancitoSentinal Passive Wireless Survey Tool</div>
<div class="scan-status" id="scan-status">Next scan in <strong id="countdown">--</strong>s</div>
<div class="settings-overlay" id="settings-overlay"></div>
<aside class="settings-drawer" id="settings-drawer" aria-label="Scanner settings">
  <div class="settings-title">
    <h2>Sentinal Settings</h2>
    <button class="settings-close" id="settings-close" type="button" aria-label="Close settings">×</button>
  </div>
  <label class="setting">
    <span>Auto-rescan<small>Refresh observations automatically</small></span>
    <input class="toggle" id="setting-auto" type="checkbox">
  </label>
  <label class="setting">
    <span>Scan interval<small>Time between dashboard refreshes</small></span>
    <select id="setting-interval">
      <option value="15">15 seconds</option>
      <option value="30">30 seconds</option>
      <option value="60">1 minute</option>
      <option value="120">2 minutes</option>
      <option value="300">5 minutes</option>
    </select>
  </label>
  <label class="setting">
    <span>Minimum signal<small>Hide weaker observations</small></span>
    <select id="setting-rssi">
      <option value="-100">Show all</option>
      <option value="-90">-90 dBm or stronger</option>
      <option value="-80">-80 dBm or stronger</option>
      <option value="-70">-70 dBm or stronger</option>
      <option value="-60">-60 dBm or stronger</option>
    </select>
  </label>
  <label class="setting">
    <span>Show Wi-Fi<small>Display nearby access points</small></span>
    <input class="toggle" id="setting-wifi" type="checkbox">
  </label>
  <label class="setting">
    <span>Show Bluetooth<small>Display BLE advertisements</small></span>
    <input class="toggle" id="setting-ble" type="checkbox">
  </label>
  <label class="setting">
    <span>Show ignored<small>Reveal filtered observations</small></span>
    <input class="toggle" id="setting-ignored" type="checkbox">
  </label>
  <label class="setting">
    <span>Compact layout<small>Fit more observations onscreen</small></span>
    <input class="toggle" id="setting-compact" type="checkbox">
  </label>
</aside>
<script>
(function(){{
  var storageKey = "ryancito-sentinal-ignored-devices";
  var settingsKey = "ryancito-sentinal-settings";
  var ignored = {{}};
  var settings = {{
    auto: false,
    interval: 30,
    rssi: -100,
    wifi: true,
    ble: true,
    ignored: false,
    compact: false
  }};
  var timer = null;
  try {{
    ignored = JSON.parse(localStorage.getItem(storageKey) || "{{}}");
  }} catch (error) {{
    ignored = {{}};
  }}
  try {{
    var storedSettings = JSON.parse(localStorage.getItem(settingsKey) || "{{}}");
    Object.keys(storedSettings).forEach(function(key){{
      if (Object.prototype.hasOwnProperty.call(settings, key))
        settings[key] = storedSettings[key];
    }});
  }} catch (error) {{}}

  function save(){{
    try {{ localStorage.setItem(storageKey, JSON.stringify(ignored)); }}
    catch (error) {{}}
  }}

  function saveSettings(){{
    try {{ localStorage.setItem(settingsKey, JSON.stringify(settings)); }}
    catch (error) {{}}
  }}

  function updateRows(){{
    document.querySelectorAll(".survey-row").forEach(function(row){{
      var id = row.getAttribute("data-device-id");
      var box = row.querySelector(".ignore-box");
      var isIgnored = !!ignored[id];
      var tooWeak = Number(row.getAttribute("data-rssi")) < Number(settings.rssi);
      box.checked = isIgnored;
      row.classList.toggle("ignored-row", isIgnored);
      row.classList.toggle("section-hidden", tooWeak);
    }});
  }}

  function startTimer(){{
    if (timer) clearInterval(timer);
    document.body.classList.toggle("auto-active", !!settings.auto);
    if (!settings.auto) return;
    var remaining = Number(settings.interval);
    document.getElementById("countdown").textContent = remaining;
    timer = setInterval(function(){{
      remaining -= 1;
      document.getElementById("countdown").textContent = remaining;
      if (remaining <= 0) window.location.reload();
    }}, 1000);
  }}

  function applySettings(){{
    document.querySelector(".wifi-card").classList.toggle("section-hidden", !settings.wifi);
    document.querySelector(".ble-card").classList.toggle("section-hidden", !settings.ble);
    document.body.classList.toggle("show-ignored", !!settings.ignored);
    document.body.classList.toggle("compact", !!settings.compact);
    document.getElementById("setting-auto").checked = !!settings.auto;
    document.getElementById("setting-interval").value = String(settings.interval);
    document.getElementById("setting-rssi").value = String(settings.rssi);
    document.getElementById("setting-wifi").checked = !!settings.wifi;
    document.getElementById("setting-ble").checked = !!settings.ble;
    document.getElementById("setting-ignored").checked = !!settings.ignored;
    document.getElementById("setting-compact").checked = !!settings.compact;
    document.querySelectorAll(".show-ignored-box").forEach(function(box){{
      box.checked = !!settings.ignored;
    }});
    updateRows();
    startTimer();
  }}

  function bindSetting(id, key, numeric){{
    document.getElementById(id).addEventListener("change", function(event){{
      settings[key] = numeric ? Number(event.target.value) : event.target.checked;
      saveSettings();
      applySettings();
    }});
  }}

  document.querySelectorAll(".ignore-box").forEach(function(box){{
    box.addEventListener("change", function(){{
      var row = box.closest(".survey-row");
      var id = row.getAttribute("data-device-id");
      if (box.checked) ignored[id] = true;
      else delete ignored[id];
      save();
      updateRows();
    }});
  }});

  document.querySelectorAll(".show-ignored-box").forEach(function(box){{
    box.addEventListener("change", function(){{
      settings.ignored = box.checked;
      saveSettings();
      applySettings();
    }});
  }});

  document.getElementById("settings-open").addEventListener("click", function(){{
    document.body.classList.add("settings-visible");
  }});
  function closeSettings(){{
    document.body.classList.remove("settings-visible");
  }}
  document.getElementById("settings-close").addEventListener("click", closeSettings);
  document.getElementById("settings-overlay").addEventListener("click", closeSettings);
  document.addEventListener("keydown", function(event){{
    if (event.key === "Escape") closeSettings();
  }});

  bindSetting("setting-auto", "auto", false);
  bindSetting("setting-interval", "interval", true);
  bindSetting("setting-rssi", "rssi", true);
  bindSetting("setting-wifi", "wifi", false);
  bindSetting("setting-ble", "ble", false);
  bindSetting("setting-ignored", "ignored", false);
  bindSetting("setting-compact", "compact", false);
  window.addEventListener("beforeprint", function(){{
    if (timer) clearInterval(timer);
  }});
  window.addEventListener("afterprint", startTimer);
  applySettings();
}})();
</script>
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
        wifi_count=len(wifi_networks),
        wifi_rows=build_wifi_rows(wifi_networks),
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
    wifi_networks, wifi_error = scan_wifi_networks()
    found, error = scan_devices()
    send_response(
        client,
        "200 OK",
        "text/html; charset=utf-8",
        build_html(found, wifi_networks, error, wifi_error),
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
