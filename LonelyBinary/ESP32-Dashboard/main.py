"""Auto-starting PinPulse web dashboard for an ESP32-S3.

Copy these files to the board's root:

    main.py
    index.html
    toolbox.py

MicroPython runs ``main.py`` automatically after every boot. Press Ctrl+C to
stop the server at the serial REPL.

The HTML interface is stored separately and streamed from flash so it does
not occupy one large block of the MicroPython heap.
"""

import gc as _gc
import machine as _machine
import network as _network
import os as _os
import socket as _socket
import time as _time

try:
    import ujson as _json
except ImportError:
    import json as _json

import toolbox as _toolbox


# ============================================================
# Configuration
# ============================================================

PORT = 80
AUTO_START = True

HTML_FILE = "/index.html"
HTML_CHUNK_SIZE = 1024

MAX_REQUEST_BYTES = 4096
MAX_WIFI_RESULTS = 30
MAX_BLE_RESULTS = 40

CLIENT_TIMEOUT_SECONDS = 8
GC_REQUEST_INTERVAL = 80

# Verify these pins against the exact PinPulse board pinout.
#
# GPIO48 is intentionally excluded because it controls the RGB NeoPixel.
# Pins used by flash, PSRAM, USB, boot circuitry, or other onboard hardware
# should not be added without verifying the board schematic.
ALLOWED_GPIO_PINS = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 16, 17, 18,
    21, 35, 36, 37, 38, 39, 40, 41, 42, 47,
)

# These pins remain locked even in expert mode because they are commonly tied
# to native USB, module flash/PSRAM, or the onboard NeoPixel on ESP32-S3 boards.
HARD_BLOCKED_GPIO_PINS = (
    19, 20,
    22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34,
    45, 46, 48,
)

UNLOCKABLE_GPIO_PINS = (0, 43, 44)


# ============================================================
# Internal state
# ============================================================

_state = {
    # The NeoPixel's physical state cannot be read back after a reboot.
    "rgb": None,
    "brightness": 100,
    "led": False,
    "gpio": {},
    "requests": 0,
    "unsafe_gpio_unlocked": False,
}

_started_at = _time.ticks_ms()
_station = None
_ble_radio = None
_gpio_outputs = {}


# ============================================================
# General helpers
# ============================================================

def _clamp(value, minimum, maximum):
    """Convert a value to int and keep it inside the allowed range."""
    value = int(value)

    if value < minimum:
        return minimum

    if value > maximum:
        return maximum

    return value


def _format_mac(address):
    """Convert six MAC-address bytes into readable hexadecimal text."""
    return ":".join("{:02X}".format(value) for value in address)


def _output_pin(pin_number):
    """Return a cached output Pin object."""
    pin = _gpio_outputs.get(pin_number)

    if pin is None:
        pin = _machine.Pin(
            pin_number,
            _machine.Pin.OUT,
            value=0,
        )
        _gpio_outputs[pin_number] = pin

    return pin


# ============================================================
# Board information and controls
# ============================================================

def _wlan():
    """Return one cached Wi-Fi station interface."""
    global _station

    if _station is None:
        _gc.collect()

        interface = getattr(_network, "STA_IF", None)

        if interface is None:
            interface = getattr(_network, "IF_STA")

        _station = _network.WLAN(interface)

    return _station


def _uptime():
    """Return dashboard uptime as a compact string."""
    elapsed = _time.ticks_diff(
        _time.ticks_ms(),
        _started_at,
    )

    return _toolbox.format_uptime(elapsed)


def _system_status():
    """Build a compact JSON-safe system snapshot."""
    wlan = _wlan()
    connected = wlan.isconnected()

    ip_address = None
    gateway = None
    subnet = None
    dns = None
    rssi = None
    ssid = None
    mac = None
    channel = None

    if connected:
        config = wlan.ifconfig()

        ip_address = config[0]
        subnet = config[1]
        gateway = config[2]
        dns = config[3]

        try:
            ssid = wlan.config("ssid")
        except Exception:
            pass

        try:
            mac = _format_mac(wlan.config("mac"))
        except Exception:
            pass

        try:
            channel = wlan.config("channel")
        except Exception:
            pass

        try:
            rssi = wlan.status("rssi")
        except Exception:
            pass

    free_heap = _gc.mem_free()
    used_heap = _gc.mem_alloc()

    disk = _os.statvfs("/")

    block_size = disk[0]
    total_flash = block_size * disk[2]
    free_flash = block_size * disk[3]

    gpio_states = _gpio_status()

    return {
        "ok": True,
        "cpu_mhz": _machine.freq() // 1_000_000,
        "heap_free": free_heap,
        "heap_total": free_heap + used_heap,
        "flash_free": free_flash,
        "flash_total": total_flash,
        "connected": connected,
        "ip": ip_address,
        "subnet": subnet,
        "gateway": gateway,
        "dns": dns,
        "ssid": ssid,
        "mac": mac,
        "channel": channel,
        "rssi": rssi,
        "quality": _toolbox.signal_quality(rssi),
        "uptime": _uptime(),
        "rgb": _state["rgb"],
        "brightness": _state["brightness"],
        "led": _state["led"],
        "gpio": gpio_states,
        "allowed_gpio_pins": _controllable_gpio_pins(),
        "hard_blocked_gpio_pins": HARD_BLOCKED_GPIO_PINS,
        "unsafe_gpio_unlocked": _state["unsafe_gpio_unlocked"],
        "requests": _state["requests"],
        "toolbox_version": getattr(
            _toolbox,
            "__version__",
            "unknown",
        ),
    }


def _gpio_status():
    """Read allow-listed pins without changing their current modes."""
    gpio_states = {}

    for pin_number in _controllable_gpio_pins():
        try:
            gpio_states[pin_number] = _machine.Pin(pin_number).value()
        except Exception:
            pass

    _state["gpio"] = gpio_states
    return gpio_states


def _controllable_gpio_pins():
    """Return the safe pins plus temporary expert-mode pins."""
    if _state["unsafe_gpio_unlocked"]:
        return ALLOWED_GPIO_PINS + UNLOCKABLE_GPIO_PINS
    return ALLOWED_GPIO_PINS


def _scan_networks():
    """Return nearby Wi-Fi networks ordered by signal strength."""
    wlan = _wlan()
    wlan.active(True)

    _gc.collect()

    found = wlan.scan()
    networks = []

    for row in found[:MAX_WIFI_RESULTS]:
        raw_ssid, bssid, channel, rssi, auth_mode, hidden = row

        try:
            ssid = raw_ssid.decode("utf-8")
        except Exception:
            ssid = repr(raw_ssid)

        networks.append({
            "ssid": ssid or "<hidden>",
            "bssid": _format_mac(bssid),
            "channel": channel,
            "rssi": rssi,
            "quality": _toolbox.signal_quality(rssi),
            "security": _toolbox.security_type(auth_mode),
            "hidden": bool(hidden),
        })

    del found
    _gc.collect()

    return networks


def _set_gpio(pin_number, value):
    """Set one allow-listed GPIO HIGH or LOW."""
    pin_number = int(pin_number)
    value = 1 if int(value) else 0

    if pin_number not in _controllable_gpio_pins():
        raise ValueError(
            "GPIO{} is locked for this board".format(pin_number)
        )

    pin = _output_pin(pin_number)
    pin.value(value)

    # Integer keys become strings automatically when converted to JSON.
    _state["gpio"][pin_number] = value


def _set_all_safe_lights(on):
    """Drive every allow-listed GPIO HIGH or LOW.

    GPIO48 is excluded because it controls the onboard RGB NeoPixel.
    """
    value = 1 if on else 0

    for pin_number in ALLOWED_GPIO_PINS:
        pin = _output_pin(pin_number)
        pin.value(value)

        _state["gpio"][pin_number] = value

    _state["led"] = bool(on)


# ============================================================
# Bluetooth scanning
# ============================================================

def _ble_name(payload):
    """Extract a complete or shortened BLE device name."""
    offset = 0
    short_name = None
    payload_length = len(payload)

    while offset + 1 < payload_length:
        field_length = payload[offset]

        if field_length == 0:
            break

        field_end = offset + field_length + 1

        if field_end > payload_length:
            break

        field_type = payload[offset + 1]

        # 0x09 = complete local name
        # 0x08 = shortened local name
        if field_type == 0x09 or field_type == 0x08:
            raw_name = payload[offset + 2:field_end]

            try:
                name = bytes(raw_name).decode("utf-8")
            except Exception:
                name = ""

            if field_type == 0x09:
                return name

            short_name = name

        offset = field_end

    return short_name


def _scan_bluetooth(duration_ms=4000):
    """Perform one bounded BLE scan and return compact results."""
    _gc.collect()

    try:
        import bluetooth
    except ImportError:
        raise RuntimeError(
            "This firmware does not include Bluetooth support"
        )

    # MicroPython BLE IRQ event numbers.
    IRQ_SCAN_RESULT = 5
    IRQ_SCAN_DONE = 6

    global _ble_radio

    if _ble_radio is None:
        _ble_radio = bluetooth.BLE()

    ble = _ble_radio

    # Raw address bytes are used as dictionary keys.
    results = {}

    # A list is used because nested functions cannot assign directly to a
    # normal outer local variable on all MicroPython versions.
    scan_done = [False]

    def on_ble_event(event, data):
        if event == IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data

            address = bytes(addr)
            key = (int(addr_type), address)
            previous = results.get(key)

            # Prevent an unbounded number of BLE result allocations.
            if previous is None and len(results) >= MAX_BLE_RESULTS:
                return

            name = _ble_name(adv_data)

            # Compact tuple layout:
            #
            #   0 = RSSI
            #   1 = name
            #   2 = connectable
            #   3 = address type
            if (
                previous is None
                or rssi > previous[0]
                or (name and not previous[1])
            ):
                previous_name = ""

                if previous is not None:
                    previous_name = previous[1]

                results[key] = (
                    rssi,
                    name or previous_name,
                    adv_type in (0, 1),
                    addr_type,
                )

        elif event == IRQ_SCAN_DONE:
            scan_done[0] = True

    try:
        ble.active(True)
        ble.irq(on_ble_event)

        # Cancel a stale scan left by an interrupted dashboard request.
        try:
            ble.gap_scan(None)
        except Exception:
            pass

        # Stopping an old scan can itself emit IRQ_SCAN_DONE.
        scan_done[0] = False

        ble.gap_scan(
            int(duration_ms),
            30_000,
            30_000,
            True,
        )

        started = _time.ticks_ms()
        timeout_ms = duration_ms + 1000

        while not scan_done[0]:
            elapsed = _time.ticks_diff(
                _time.ticks_ms(),
                started,
            )

            if elapsed > timeout_ms:
                break

            _time.sleep_ms(50)

    finally:
        try:
            ble.gap_scan(None)
        except Exception:
            pass

        try:
            ble.irq(None)
        except Exception:
            pass

        # Keep the controller active. Repeatedly deinitializing the shared
        # ESP32 radio can make later scans unreliable while Wi-Fi is serving.

    devices = []

    for key, record in results.items():
        addr_type, address = key
        rssi, name, connectable, addr_type = record

        devices.append({
            "address": _format_mac(address),
            "name": name or "<unnamed>",
            "rssi": rssi,
            "connectable": connectable,
            "address_type": addr_type,
        })

    del results
    _gc.collect()

    return devices


# ============================================================
# HTTP request helpers
# ============================================================

def _read_request(client):
    """Read one bounded HTTP request and decode its JSON body."""
    data = bytearray()

    header_end = -1
    content_length = 0

    while len(data) < MAX_REQUEST_BYTES:
        remaining = MAX_REQUEST_BYTES - len(data)
        chunk_size = min(512, remaining)

        chunk = client.recv(chunk_size)

        if not chunk:
            break

        data.extend(chunk)

        # Parse the headers only once.
        if header_end < 0:
            header_end = data.find(b"\r\n\r\n")

            if header_end >= 0:
                header_bytes = bytes(data[:header_end])

                try:
                    header_text = header_bytes.decode("utf-8")
                except Exception:
                    raise ValueError("HTTP headers are not valid UTF-8")

                for line in header_text.split("\r\n")[1:]:
                    if line.lower().startswith("content-length:"):
                        try:
                            content_length = int(
                                line.split(":", 1)[1].strip()
                            )
                        except Exception:
                            raise ValueError("Invalid Content-Length")

                        if content_length < 0:
                            raise ValueError("Invalid Content-Length")

                        full_length = (
                            header_end
                            + 4
                            + content_length
                        )

                        if full_length > MAX_REQUEST_BYTES:
                            raise ValueError("Request is too large")

        if header_end >= 0:
            expected_length = (
                header_end
                + 4
                + content_length
            )

            if len(data) >= expected_length:
                break

    if header_end < 0:
        raise ValueError("Incomplete HTTP headers")

    expected_length = header_end + 4 + content_length

    if len(data) < expected_length:
        raise ValueError("Incomplete HTTP body")

    try:
        header = bytes(data[:header_end]).decode("utf-8")
    except Exception:
        raise ValueError("HTTP headers are not valid UTF-8")

    request_line = header.split("\r\n", 1)[0].split()

    if len(request_line) != 3:
        raise ValueError("Invalid HTTP request line")

    method = request_line[0]
    path = request_line[1].split("?", 1)[0]

    if content_length:
        raw_body = bytes(
            data[
                header_end + 4:
                expected_length
            ]
        )

        try:
            body = _json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise ValueError("Invalid JSON request body")
    else:
        body = {}

    return method, path, body


_STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    413: "Payload Too Large",
    500: "Internal Server Error",
}


def _headers(client, status, content_type, length):
    """Send HTTP headers without buffering the response body."""
    reason = _STATUS_TEXT.get(status, "Error")

    header = (
        "HTTP/1.1 {} {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(
        status,
        reason,
        content_type,
        length,
    )

    client.sendall(header.encode("utf-8"))


def _send_json(client, payload, status=200):
    """Serialize and send one compact JSON response."""
    body = _json.dumps(payload).encode("utf-8")

    _headers(
        client,
        status,
        "application/json; charset=utf-8",
        len(body),
    )

    client.sendall(body)


def _send_dashboard(client):
    """Stream dashboard.html directly from flash."""
    size = _os.stat(HTML_FILE)[6]

    _headers(
        client,
        200,
        "text/html; charset=utf-8",
        size,
    )

    with open(HTML_FILE, "rb") as page:
        while True:
            chunk = page.read(HTML_CHUNK_SIZE)

            if not chunk:
                break

            client.sendall(chunk)


# ============================================================
# Dashboard routes
# ============================================================

def _route(method, path, body):
    """Execute one dashboard route."""
    if method == "GET":
        if path == "/api/status":
            return _system_status()

        if path == "/api/wifi/scan":
            return {
                "ok": True,
                "networks": _scan_networks(),
            }

        if path == "/api/bluetooth/scan":
            return {
                "ok": True,
                "devices": _scan_bluetooth(),
            }

        if path == "/api/gpio/status":
            return {
                "ok": True,
                "gpio": _gpio_status(),
                "allowed_gpio_pins": _controllable_gpio_pins(),
                "hard_blocked_gpio_pins": HARD_BLOCKED_GPIO_PINS,
                "unsafe_gpio_unlocked": _state["unsafe_gpio_unlocked"],
            }

    elif method == "POST":
        if path == "/api/rgb":
            red = _clamp(body.get("r", 0), 0, 255)
            green = _clamp(body.get("g", 0), 0, 255)
            blue = _clamp(body.get("b", 0), 0, 255)

            brightness = _clamp(
                body.get("brightness", 100),
                0,
                100,
            )

            values = [red, green, blue]

            applied = _toolbox.rgb(
                red,
                green,
                blue,
                brightness=brightness,
            )

            _state["rgb"] = values
            _state["brightness"] = brightness

            return {
                "ok": True,
                "rgb": values,
                "brightness": brightness,
                "applied": applied,
            }

        if path == "/api/led":
            on = bool(body.get("on"))

            _set_all_safe_lights(on)

            return {
                "ok": True,
                "on": on,
            }

        if path == "/api/gpio":
            _set_gpio(
                body.get("pin"),
                body.get("value", 0),
            )

            return {
                "ok": True,
            }

        if path == "/api/gpio/unlock":
            _state["unsafe_gpio_unlocked"] = bool(body.get("unlocked"))
            return {
                "ok": True,
                "unlocked": _state["unsafe_gpio_unlocked"],
                "allowed_gpio_pins": _controllable_gpio_pins(),
                "hard_blocked_gpio_pins": HARD_BLOCKED_GPIO_PINS,
            }

        if path == "/api/cpu":
            mhz = int(body.get("mhz", 160))

            if mhz == 160:
                _toolbox.cpu160()

            elif mhz == 240:
                _toolbox.cpu240()

            else:
                raise ValueError(
                    "CPU speed must be 160 or 240 MHz"
                )

            return {
                "ok": True,
                "mhz": mhz,
            }

        if path == "/api/gc":
            before = _gc.mem_free()

            _gc.collect()

            after = _gc.mem_free()

            return {
                "ok": True,
                "reclaimed": max(0, after - before),
            }

        if path == "/api/reset":
            return {
                "ok": True,
                "resetting": True,
            }

    raise KeyError("Route not found")


def _handle_client(client):
    """Serve the dashboard page or one API request."""
    try:
        method, path, body = _read_request(client)

        _state["requests"] += 1

        if method == "GET" and path == "/":
            _send_dashboard(client)
            return

        try:
            response = _route(method, path, body)
            _send_json(client, response)

            if response.get("resetting"):
                _time.sleep_ms(150)
                _machine.reset()

        except KeyError:
            _send_json(
                client,
                {
                    "ok": False,
                    "error": "Route not found",
                },
                404,
            )

        except Exception as error:
            _send_json(
                client,
                {
                    "ok": False,
                    "error": str(error),
                },
                400,
            )

    except Exception as error:
        try:
            _send_json(
                client,
                {
                    "ok": False,
                    "error": str(error),
                },
                400,
            )
        except Exception:
            pass


# ============================================================
# Public server entry point
# ============================================================

def start(port=PORT):
    """Connect Wi-Fi and serve until Ctrl+C is pressed."""
    _gc.collect()

    try:
        _os.stat(HTML_FILE)

    except OSError:
        print(
            "Missing {}. Upload index.html beside main.py.".format(
                HTML_FILE
            )
        )
        return

    try:
        wlan = _wlan()

    except OSError as error:
        print(
            "Dashboard could not initialize Wi-Fi: {}".format(
                error
            )
        )

        print(
            "Free heap: {}".format(
                _toolbox.human_size(_gc.mem_free())
            )
        )
        return

    if not wlan.isconnected():
        _toolbox.connect()

    if not wlan.isconnected():
        print(
            "Dashboard stopped because Wi-Fi is not connected."
        )
        return

    address = wlan.ifconfig()[0]

    server = _socket.socket(
        _socket.AF_INET,
        _socket.SOCK_STREAM,
    )

    try:
        server.setsockopt(
            _socket.SOL_SOCKET,
            _socket.SO_REUSEADDR,
            1,
        )
    except Exception:
        pass

    server.bind(("0.0.0.0", int(port)))
    server.listen(2)

    print("====================================================")
    print(" PinPulse dashboard is online")
    print(" http://{}:{}".format(address, port))
    print(" Press Ctrl+C to stop")
    print("====================================================")

    try:
        while True:
            client = None

            try:
                client, _remote = server.accept()
                client.settimeout(CLIENT_TIMEOUT_SECONDS)

                _handle_client(client)

            except OSError:
                # Common causes include a browser disconnecting or a timeout.
                pass

            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

                # Run collection periodically instead of after every request.
                if (
                    _state["requests"] > 0
                    and _state["requests"] % GC_REQUEST_INTERVAL == 0
                ):
                    _gc.collect()

    except KeyboardInterrupt:
        print("Dashboard stopped.")

    finally:
        try:
            server.close()
        except Exception:
            pass

        _gc.collect()


__version__ = "3.1.0"


if AUTO_START:
    start()
