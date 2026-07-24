# RyancitoSentinal Collector
# Arduino Nano ESP32 (ESP32-S3), MicroPython
#
# The ESP32 collects bounded BLE evidence and serves a small sequence API.
# Aggregation, storage, filtering, visualization, and exporting live in-browser.

import bluetooth
import gc
import machine
import network
import os
import socket
import sys
import time
import ubinascii
import ujson

try:
    import uselect as select
except ImportError:
    import select

try:
    import secret
    # DEFAULT_* replaces HOME_*. The fallback keeps older secret.py files
    # working while users migrate.
    DEFAULT_SSID = getattr(
        secret, "DEFAULT_SSID", getattr(secret, "HOME_SSID", ""))
    DEFAULT_PASSWORD = getattr(
        secret, "DEFAULT_PASSWORD", getattr(secret, "HOME_PASSWORD", ""))
    AP_SSID = getattr(secret, "AP_SSID", "RyancitoSentinal")
    AP_PASSWORD = getattr(secret, "AP_PASSWORD", "ryancito1337")
except ImportError:
    DEFAULT_SSID = ""
    DEFAULT_PASSWORD = ""
    AP_SSID = "RyancitoSentinal"
    AP_PASSWORD = "ryancito1337"

# ----------------------------- configuration -----------------------------
HTTP_PORT = 80
CONNECT_TIMEOUT_MS = 12_000

RAW_RING_SIZE = 96
EVIDENCE_RING_SIZE = 512
MAX_TRACKED_DEVICES = 160
DEFAULT_API_LIMIT = 50
MAX_API_LIMIT = 100

MIN_RSSI = -100
RSSI_DELTA_DB = 5
HEARTBEAT_MS = 1_000
WIFI_SCAN_MIN_INTERVAL_MS = 30_000
PROXIMITY_STALE_MS = 5_000
RSSI_RIGHT_NEXT_TO = -50
RSSI_WITHIN_10_FT = -70
RSSI_10_TO_20_FT = -78
RSSI_20_TO_30_FT = -85

SCAN_INTERVAL_US = 30_000
SCAN_WINDOW_US = 30_000
ACTIVE_SCAN = True

LOG_LEVEL = 1  # 0=quiet, 1=status, 2=debug
FIRMWARE_NAME = "RyancitoSentinal Collector"
FIRMWARE_VERSION = "2.4.0"

ORANGE_PIN = 48
RGB_RED_PIN = 46
RGB_GREEN_PIN = 0
RGB_BLUE_PIN = 45
# -----------------------------------------------------------------------

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)

BOOT_MS = time.ticks_ms()

orange = machine.Pin(ORANGE_PIN, machine.Pin.OUT)
led_r = machine.PWM(machine.Pin(RGB_RED_PIN), freq=1000, duty=1023)
led_g = machine.PWM(machine.Pin(RGB_GREEN_PIN), freq=1000, duty=1023)
led_b = machine.PWM(machine.Pin(RGB_BLUE_PIN), freq=1000, duty=1023)

sta = network.WLAN(network.STA_IF)
ap = network.WLAN(network.AP_IF)
active_interface = None
connected_ssid = ""

ble = bluetooth.BLE()

# IRQ ingress ring. Entries are copied because IRQ buffers are transient.
raw_ring = [None] * RAW_RING_SIZE
raw_read = 0
raw_write = 0
raw_count = 0
raw_dropped = 0

# Evidence ring. Index is sequence modulo capacity.
evidence_ring = [None] * EVIDENCE_RING_SIZE
next_sequence = 1
evidence_overwritten = 0

# Bounded deduplication state keyed by "address-type:MAC".
device_state = {}
wifi_cache = []
wifi_scan_number = 0
wifi_last_scan_ms = time.ticks_add(BOOT_MS, -WIFI_SCAN_MIN_INTERVAL_MS)
wifi_scan_duration_ms = 0


def log(level, *parts):
    if LOG_LEVEL >= level:
        print(*parts)


def print_exception(label, exception):
    print(label)
    sys.print_exception(exception)


def set_rgb(red, green, blue):
    led_r.duty(1023 - (max(0, min(255, red)) * 1023 // 255))
    led_g.duty(1023 - (max(0, min(255, green)) * 1023 // 255))
    led_b.duty(1023 - (max(0, min(255, blue)) * 1023 // 255))


def led_off():
    set_rgb(0, 0, 0)


def format_mac(addr):
    value = ubinascii.hexlify(addr).decode().upper()
    return ":".join(value[i:i + 2] for i in range(0, 12, 2))


def payload_fingerprint(payload):
    # Small FNV-1a implementation; performed outside the BLE IRQ.
    value = 2166136261
    for byte in payload:
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def ble_irq(event, data):
    global raw_write, raw_count, raw_dropped
    if event != _IRQ_SCAN_RESULT:
        return

    if raw_count >= RAW_RING_SIZE:
        raw_dropped += 1
        return

    addr_type, addr, adv_type, rssi, adv_data = data
    # Keep the callback limited to copies, primitive conversion, and enqueue.
    raw_ring[raw_write] = (
        int(addr_type),
        bytes(addr),
        int(adv_type),
        int(rssi),
        bytes(adv_data),
        time.ticks_ms(),
    )
    raw_write = (raw_write + 1) % RAW_RING_SIZE
    raw_count += 1


def pop_raw():
    global raw_read, raw_count
    if raw_count == 0:
        return None
    item = raw_ring[raw_read]
    raw_ring[raw_read] = None
    raw_read = (raw_read + 1) % RAW_RING_SIZE
    raw_count -= 1
    return item


def evict_oldest_device():
    if not device_state:
        return
    oldest_key = None
    oldest_ms = None
    for key, state in device_state.items():
        seen_ms = state[3]
        if oldest_ms is None or time.ticks_diff(seen_ms, oldest_ms) < 0:
            oldest_key = key
            oldest_ms = seen_ms
    if oldest_key is not None:
        del device_state[oldest_key]


def append_evidence(item):
    global next_sequence, evidence_overwritten
    sequence = next_sequence
    next_sequence += 1
    index = (sequence - 1) % EVIDENCE_RING_SIZE
    if evidence_ring[index] is not None:
        evidence_overwritten += 1
    evidence_ring[index] = (sequence,) + item


def process_raw(max_items=32):
    processed = 0
    while processed < max_items:
        raw = pop_raw()
        if raw is None:
            break
        processed += 1

        addr_type, addr, adv_type, rssi, payload, observed_ms = raw
        if rssi < MIN_RSSI:
            continue

        mac = format_mac(addr)
        key = "{}:{}".format(addr_type, mac)
        fingerprint = payload_fingerprint(payload)
        previous = device_state.get(key)

        emit = False
        flags = 0
        if previous is None:
            if len(device_state) >= MAX_TRACKED_DEVICES:
                evict_oldest_device()
            emit = True
            flags |= 1  # first seen
        else:
            previous_fingerprint, previous_rssi, previous_emit_ms, _ = previous
            if fingerprint != previous_fingerprint:
                emit = True
                flags |= 2  # advertisement changed
            if abs(rssi - previous_rssi) >= RSSI_DELTA_DB:
                emit = True
                flags |= 4  # significant RSSI change
            if time.ticks_diff(observed_ms, previous_emit_ms) >= HEARTBEAT_MS:
                emit = True
                flags |= 8  # periodic heartbeat

        if emit:
            elapsed_ms = time.ticks_diff(observed_ms, BOOT_MS)
            # Compact evidence tuple:
            # seq is prepended by append_evidence.
            # [elapsed_ms, addr_type, mac, rssi, adv_type, flags, adv_hex]
            append_evidence((
                elapsed_ms,
                addr_type,
                mac,
                rssi,
                adv_type,
                flags,
                ubinascii.hexlify(payload).decode(),
            ))
            last_emit_ms = observed_ms
        else:
            last_emit_ms = previous[2]

        device_state[key] = (
            fingerprint,
            rssi,
            last_emit_ms,
            observed_ms,
        )
    return processed


def update_proximity_led():
    now = time.ticks_ms()
    strongest_rssi = None
    for state in device_state.values():
        rssi = state[1]
        last_seen_ms = state[3]
        if time.ticks_diff(now, last_seen_ms) <= PROXIMITY_STALE_MS:
            if strongest_rssi is None or rssi > strongest_rssi:
                strongest_rssi = rssi

    if strongest_rssi is None or strongest_rssi < RSSI_20_TO_30_FT:
        set_rgb(28, 28, 28)       # gray: stale or beyond ~30 ft
    elif strongest_rssi < RSSI_10_TO_20_FT:
        set_rgb(255, 0, 0)        # red: approximately 20–30 ft
    elif strongest_rssi < RSSI_WITHIN_10_FT:
        set_rgb(255, 150, 0)      # yellow: approximately 10–20 ft
    elif strongest_rssi < RSSI_RIGHT_NEXT_TO:
        set_rgb(0, 255, 0)        # green: approximately 10 ft or closer
    else:
        set_rgb(0, 0, 255)        # blue: immediately nearby


def oldest_sequence():
    return max(1, next_sequence - EVIDENCE_RING_SIZE)


def get_updates(after, limit):
    newest = next_sequence - 1
    oldest = oldest_sequence()
    reset = after > newest and after > 0
    if reset:
        after = 0
    dropped = 0
    requested_start = after + 1
    if requested_start < oldest:
        dropped = oldest - requested_start
        requested_start = oldest

    end = min(newest, requested_start + limit - 1)
    items = []
    sequence = requested_start
    while sequence <= end:
        item = evidence_ring[(sequence - 1) % EVIDENCE_RING_SIZE]
        if item is not None and item[0] == sequence:
            items.append(item)
        sequence += 1

    return {
        "from": items[0][0] if items else after + 1,
        "to": items[-1][0] if items else after,
        "dropped": dropped,
        "reset": reset,
        "items": items,
    }


def wifi_security(authmode):
    return {
        0: "Open",
        1: "WEP",
        2: "WPA",
        3: "WPA2",
        4: "WPA/WPA2",
        5: "WPA2 Enterprise",
        6: "WPA3",
        7: "WPA2/WPA3",
    }.get(authmode, "Unknown ({})".format(authmode))


def scan_wifi_if_due(force=False):
    global wifi_cache, wifi_scan_number, wifi_last_scan_ms
    global wifi_scan_duration_ms
    now = time.ticks_ms()
    if (not force and wifi_cache and
            time.ticks_diff(now, wifi_last_scan_ms) <
            WIFI_SCAN_MIN_INTERVAL_MS):
        return

    started = time.ticks_ms()
    # ESP32-S3 shares its 2.4 GHz radio. Pause BLE intentionally instead of
    # letting the IRQ ingress ring overflow during the blocking WLAN scan.
    try:
        ble.gap_scan(None)
    except Exception:
        pass
    process_raw(RAW_RING_SIZE)

    results = []
    try:
        if not sta.active():
            sta.active(True)
        for item in sta.scan():
            raw_ssid, bssid, channel, rssi, authmode = item[:5]
            hidden = bool(item[5]) if len(item) > 5 else not raw_ssid
            try:
                ssid = raw_ssid.decode("utf-8", "ignore")
            except Exception:
                ssid = str(raw_ssid)
            if not ssid:
                ssid = "Hidden"
                hidden = True
            results.append([
                ssid,
                format_mac(bssid),
                int(channel),
                int(rssi),
                wifi_security(authmode),
                hidden,
            ])
        results.sort(key=lambda row: row[3], reverse=True)
        wifi_cache = results
        wifi_scan_number += 1
        wifi_last_scan_ms = time.ticks_ms()
    finally:
        ble.gap_scan(0, SCAN_INTERVAL_US, SCAN_WINDOW_US, ACTIVE_SCAN)
        wifi_scan_duration_ms = time.ticks_diff(time.ticks_ms(), started)


def connect_default():
    global active_interface, connected_ssid
    if not DEFAULT_SSID:
        return False
    log(1, "Connecting to default Wi-Fi:", DEFAULT_SSID)
    sta.active(True)
    try:
        sta.connect(DEFAULT_SSID, DEFAULT_PASSWORD)
    except Exception as e:
        print_exception("Wi-Fi connect failed:", e)
        return False

    deadline = time.ticks_add(time.ticks_ms(), CONNECT_TIMEOUT_MS)
    while not sta.isconnected() and time.ticks_diff(
            deadline, time.ticks_ms()) > 0:
        orange.value(1 - orange.value())
        time.sleep_ms(150)

    orange.value(0)
    if not sta.isconnected():
        try:
            sta.disconnect()
        except Exception:
            pass
        return False

    active_interface = sta
    connected_ssid = DEFAULT_SSID
    return True


def start_fallback_ap():
    global active_interface, connected_ssid
    ap.active(True)
    if len(AP_PASSWORD) >= 8:
        try:
            ap.config(
                essid=AP_SSID,
                password=AP_PASSWORD,
                authmode=network.AUTH_WPA2_PSK,
            )
        except Exception:
            ap.config(ssid=AP_SSID, password=AP_PASSWORD)
    else:
        log(1, "AP password is too short; starting an open AP.")
        try:
            ap.config(essid=AP_SSID, authmode=network.AUTH_OPEN)
        except Exception:
            ap.config(ssid=AP_SSID)
    active_interface = ap
    connected_ssid = AP_SSID


def configure_network():
    try:
        network.hostname("RyancitoSentinal")
    except Exception:
        pass
    ap.active(False)
    sta.active(False)
    time.sleep_ms(200)
    if not connect_default():
        start_fallback_ap()
    log(1, "Network:", connected_ssid, active_interface.ifconfig()[0])


def query_value(target, name, default):
    if "?" not in target:
        return default
    query = target.split("?", 1)[1]
    for pair in query.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            if key == name:
                return value
    return default


def request_path(target):
    return target.split("?", 1)[0]


def send_headers(client, status, content_type, length, cache=False):
    cache_header = (
        "Cache-Control: public, max-age=86400\r\n"
        if cache else
        "Cache-Control: no-store\r\n"
    )
    headers = (
        "HTTP/1.1 {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "{}"
        "Connection: close\r\n\r\n"
    ).format(status, content_type, length, cache_header)
    client.sendall(headers.encode())


def send_bytes(client, status, content_type, body, cache=False):
    if isinstance(body, str):
        body = body.encode()
    send_headers(client, status, content_type, len(body), cache)
    client.sendall(body)


def send_file(client, filename, content_type, cache=True):
    try:
        length = os.stat(filename)[6]
        send_headers(client, "200 OK", content_type, length, cache)
        with open(filename, "rb") as asset:
            while True:
                chunk = asset.read(1024)
                if not chunk:
                    break
                client.sendall(chunk)
    except OSError:
        send_bytes(client, "404 Not Found", "text/plain", "Missing asset\n")


def diagnostics():
    return {
        "firmware": FIRMWARE_NAME,
        "version": FIRMWARE_VERSION,
        "uptime_ms": time.ticks_diff(time.ticks_ms(), BOOT_MS),
        "ssid": connected_ssid,
        "ip": active_interface.ifconfig()[0],
        "next_seq": next_sequence,
        "oldest_seq": oldest_sequence(),
        "raw_buffer_used": raw_count,
        "raw_buffer_capacity": RAW_RING_SIZE,
        "raw_dropped": raw_dropped,
        "evidence_capacity": EVIDENCE_RING_SIZE,
        "evidence_overwritten": evidence_overwritten,
        "tracked_devices": len(device_state),
        "wifi_scan_number": wifi_scan_number,
        "wifi_networks": len(wifi_cache),
        "wifi_scan_duration_ms": wifi_scan_duration_ms,
        "free_heap": gc.mem_free(),
        "config": {
            "min_rssi": MIN_RSSI,
            "rssi_delta_db": RSSI_DELTA_DB,
            "heartbeat_ms": HEARTBEAT_MS,
            "proximity_stale_ms": PROXIMITY_STALE_MS,
            "rssi_right_next_to": RSSI_RIGHT_NEXT_TO,
            "rssi_within_10_ft": RSSI_WITHIN_10_FT,
            "rssi_10_to_20_ft": RSSI_10_TO_20_FT,
            "rssi_20_to_30_ft": RSSI_20_TO_30_FT,
            "active_scan": ACTIVE_SCAN,
            "scan_interval_us": SCAN_INTERVAL_US,
            "scan_window_us": SCAN_WINDOW_US,
        },
    }


def handle_http(client):
    try:
        client.settimeout(2)
        request = client.recv(1024)
        if not request:
            return
        first_line = request.split(b"\r\n", 1)[0].split()
        if len(first_line) < 2:
            send_bytes(client, "400 Bad Request", "text/plain", "Bad request\n")
            return
        method = first_line[0].decode()
        target = first_line[1].decode()
        path = request_path(target)
        if method != "GET":
            send_bytes(
                client, "405 Method Not Allowed", "text/plain", "GET only\n")
            return

        if path == "/api/updates":
            try:
                after = max(0, int(query_value(target, "after", "0")))
                limit = int(query_value(
                    target, "limit", str(DEFAULT_API_LIMIT)))
                limit = max(1, min(MAX_API_LIMIT, limit))
            except ValueError:
                send_bytes(
                    client, "400 Bad Request", "application/json",
                    '{"error":"invalid query"}')
                return
            send_bytes(
                client, "200 OK", "application/json",
                ujson.dumps(get_updates(after, limit)))
            return

        if path == "/api/status":
            send_bytes(
                client, "200 OK", "application/json",
                ujson.dumps(diagnostics()))
            return

        if path == "/api/wifi":
            force = query_value(target, "force", "0") == "1"
            scan_wifi_if_due(force=force)
            send_bytes(
                client, "200 OK", "application/json",
                ujson.dumps({
                    "scan": wifi_scan_number,
                    "captured_ms": time.ticks_diff(wifi_last_scan_ms, BOOT_MS),
                    "duration_ms": wifi_scan_duration_ms,
                    "items": wifi_cache,
                }))
            return

        assets = {
            "/": ("index.html", "text/html; charset=utf-8", False),
            "/index.html": ("index.html", "text/html; charset=utf-8", False),
            "/app.js": ("app.js", "application/javascript", True),
            "/worker.js": ("worker.js", "application/javascript", True),
            "/style.css": ("style.css", "text/css", True),
        }
        asset = assets.get(path)
        if asset:
            send_file(client, asset[0], asset[1], asset[2])
            return
        if path == "/favicon.ico":
            send_bytes(client, "204 No Content", "image/x-icon", b"")
            return
        send_bytes(client, "404 Not Found", "text/plain", "Not found\n")
    except Exception as e:
        if LOG_LEVEL >= 2:
            print_exception("HTTP error:", e)


def serve_forever():
    address = socket.getaddrinfo("0.0.0.0", HTTP_PORT)[0][-1]
    server = socket.socket()
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    server.bind(address)
    server.listen(2)
    server.setblocking(False)

    ip = active_interface.ifconfig()[0]
    print("RyancitoSentinal Collector -> http://{}/".format(ip))

    ble.active(True)
    ble.irq(ble_irq)
    ble.gap_scan(0, SCAN_INTERVAL_US, SCAN_WINDOW_US, ACTIVE_SCAN)
    orange.value(1)
    set_rgb(0, 20, 45)

    last_gc_ms = time.ticks_ms()
    last_led_ms = time.ticks_ms()
    while True:
        process_raw(48)
        try:
            client, _ = server.accept()
        except OSError:
            client = None
        if client is not None:
            try:
                handle_http(client)
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        now = time.ticks_ms()
        if time.ticks_diff(now, last_led_ms) >= 100:
            update_proximity_led()
            last_led_ms = now
        if time.ticks_diff(now, last_gc_ms) >= 5_000:
            gc.collect()
            last_gc_ms = now
        time.sleep_ms(5)


def main():
    orange.value(0)
    led_off()
    configure_network()
    serve_forever()


try:
    main()
except KeyboardInterrupt:
    print("Stopped.")
except Exception as e:
    print_exception("Fatal:", e)
finally:
    try:
        ble.gap_scan(None)
        ble.active(False)
    except Exception:
        pass
    orange.value(0)
    led_off()
