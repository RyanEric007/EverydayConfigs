"""ESP32-S3 utilities for MicroPython.

Copy this file to the board's root, then run::

    import toolbox
    toolbox.help()

Public helpers print useful output by default and return script-friendly values.
Pass ``quiet=True`` to action helpers when calling them from a dashboard.
"""

import gc as _gc
import machine as _machine
import network as _network
import os as _os
import sys as _sys
import time as _time

try:
    import neopixel as _neopixel
except ImportError:
    _neopixel = None

__version__ = "2.0.0"

try:
    from secrets import SSID
    from secrets import PASSWORD
except ImportError:
    SSID = None
    PASSWORD = None
WIFI_TIMEOUT_SECONDS = 15

LED_PIN = 2
RGB_PIN = 48
LED_ACTIVE_HIGH = True
RGB_BRIGHTNESS = 100
DIVIDER_WIDTH = 52

# Verify this list against the exact board schematic before adding pins.
# GPIO48 is reserved for the onboard RGB LED.
ALLOWED_GPIO_PINS = (
    1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
    21, 38, 39, 40, 41, 42, 47,
)

_managed_pins = {}
_rgb_pixel = None
_station = None
_started_at_ms = _time.ticks_ms()


def _say(message, quiet=False):
    if not quiet:
        print(message)


def human_size(byte_count):
    size = float(byte_count)
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while abs(size) >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return "{} B".format(int(size))
    return "{:.2f} {}".format(size, units[index])


def divider(title=None, character="=", quiet=False):
    character = character[0] if character else "="
    if title:
        label = " {} ".format(str(title).upper())
        remaining = max(0, DIVIDER_WIDTH - len(label))
        left = remaining // 2
        line = character * left + label + character * (remaining - left)
    else:
        line = character * DIVIDER_WIDTH
    _say(line, quiet)
    return line


def format_uptime(milliseconds=None):
    if milliseconds is None:
        milliseconds = _time.ticks_diff(_time.ticks_ms(), _started_at_ms)
    seconds = max(0, int(milliseconds) // 1000)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return "{}d {:02d}h {:02d}m {:02d}s".format(days, hours, minutes, seconds)


def signal_quality(rssi):
    if rssi is None:
        return "Unknown"
    if rssi >= -50:
        return "Excellent"
    if rssi >= -60:
        return "Good"
    if rssi >= -70:
        return "Fair"
    if rssi >= -80:
        return "Weak"
    return "Very weak"


def uptime(quiet=False):
    value = format_uptime()
    _say("Uptime: {}".format(value), quiet)
    return value


def info(quiet=False):
    uname = _os.uname()
    result = {
        "system": uname.sysname, "node": uname.nodename,
        "release": uname.release, "version": uname.version,
        "machine": uname.machine, "python": _sys.version,
        "cpu_hz": _machine.freq(), "uptime": format_uptime(),
        "toolbox_version": __version__,
    }
    if not quiet:
        divider("SYSTEM INFORMATION")
        print("System     : {}".format(result["system"]))
        print("Board      : {}".format(result["machine"]))
        print("Release    : {}".format(result["release"]))
        print("MicroPython: {}".format(result["python"]))
        print("CPU        : {} MHz".format(result["cpu_hz"] // 1000000))
        print("Uptime     : {}".format(result["uptime"]))
        print("Toolbox    : {}".format(__version__))
        divider(character="-")
    return result


def mem(quiet=False):
    free = _gc.mem_free()
    used = _gc.mem_alloc()
    total = free + used
    result = {"free": free, "used": used, "total": total,
              "used_percent": (used * 100 / total) if total else 0}
    if not quiet:
        divider("MEMORY")
        print("Free : {}".format(human_size(free)))
        print("Used : {} ({:.1f}%)".format(human_size(used), result["used_percent"]))
        print("Total: {}".format(human_size(total)))
        divider(character="-")
    return result


def gc(quiet=False):
    before = _gc.mem_free()
    _gc.collect()
    reclaimed = max(0, _gc.mem_free() - before)
    _say("Garbage collection reclaimed {}.".format(human_size(reclaimed)), quiet)
    return reclaimed


def disk(path="/", quiet=False):
    stats = _os.statvfs(path)
    total = stats[0] * stats[2]
    free = stats[0] * stats[3]
    used = total - free
    result = {"path": path, "free": free, "used": used, "total": total,
              "used_percent": (used * 100 / total) if total else 0}
    if not quiet:
        divider("STORAGE")
        print("Path : {}".format(path))
        print("Free : {}".format(human_size(free)))
        print("Used : {} ({:.1f}%)".format(human_size(used), result["used_percent"]))
        print("Total: {}".format(human_size(total)))
        divider(character="-")
    return result


def cpu(quiet=False):
    mhz = _machine.freq() // 1000000
    _say("CPU frequency: {} MHz".format(mhz), quiet)
    return mhz


def _set_cpu(mhz, quiet=False):
    _machine.freq(int(mhz) * 1000000)
    actual = _machine.freq() // 1000000
    _say("CPU frequency set to {} MHz.".format(actual), quiet)
    return actual


def cpu160(quiet=False):
    return _set_cpu(160, quiet)


def cpu240(quiet=False):
    return _set_cpu(240, quiet)


def reset():
    print("Hardware reset...")
    _time.sleep_ms(100)
    _machine.reset()


def reboot():
    reset()


def soft_reset():
    print("Soft reset...")
    _time.sleep_ms(100)
    _machine.soft_reset()


def _wlan():
    global _station
    if _station is None:
        interface = getattr(_network, "STA_IF", None)
        if interface is None:
            interface = getattr(_network, "IF_STA", None)
        if interface is None:
            raise RuntimeError("This firmware has no Wi-Fi station interface")
        _station = _network.WLAN(interface)
    return _station


def _wifi_error(status):
    errors = {-3: "wrong Wi-Fi password", -2: "network not found",
              -1: "connection failed"}
    for name, message in (("STAT_WRONG_PASSWORD", "wrong Wi-Fi password"),
                          ("STAT_NO_AP_FOUND", "network not found"),
                          ("STAT_CONNECT_FAIL", "connection failed")):
        value = getattr(_network, name, None)
        if value is not None:
            errors[value] = message
    return errors.get(status)


def connect(ssid=SSID, password=PASSWORD, timeout=WIFI_TIMEOUT_SECONDS, quiet=False):
    if not ssid:
        _say("Wi-Fi is not configured. Edit secrets.py first.", quiet)
        return False
    wlan = _wlan()
    try:
        wlan.active(True)
        if wlan.isconnected():
            address = wlan.ifconfig()[0]
            _say("Already connected; IP: {}".format(address), quiet)
            return address
        _say("Connecting to {!r}...".format(ssid), quiet)
        wlan.disconnect()
        _time.sleep_ms(100)
        wlan.connect(ssid, password)
    except Exception as error:
        _say("Could not start Wi-Fi connection: {}".format(error), quiet)
        return False
    started = _time.ticks_ms()
    timeout_ms = max(0, int(float(timeout) * 1000))
    while not wlan.isconnected():
        try:
            status = wlan.status()
        except Exception:
            status = None
        failure = _wifi_error(status)
        if failure:
            _say("Wi-Fi error: {} (status {}).".format(failure, status), quiet)
            return False
        if _time.ticks_diff(_time.ticks_ms(), started) >= timeout_ms:
            _say("Connection timed out after {} seconds.".format(timeout), quiet)
            return False
        _time.sleep_ms(250)
    address = wlan.ifconfig()[0]
    _say("Connected; IP: {}".format(address), quiet)
    return address


def disconnect(deactivate=False, quiet=False):
    wlan = _wlan()
    wlan.disconnect()
    if deactivate:
        wlan.active(False)
    _say("Wi-Fi disconnected{}.".format(" and disabled" if deactivate else ""), quiet)
    return True


def net(quiet=False):
    wlan = _wlan()
    connected = wlan.isconnected()
    result = {"active": wlan.active(), "connected": connected}
    if connected:
        address, mask, gateway, dns = wlan.ifconfig()
        try:
            rssi = wlan.status("rssi")
        except Exception:
            rssi = None
        result.update({"ip": address, "mask": mask, "gateway": gateway,
                       "dns": dns, "rssi": rssi})
    if not quiet:
        divider("WI-FI STATUS")
        print("Radio    : {}".format("On" if result["active"] else "Off"))
        print("Connected: {}".format("Yes" if connected else "No"))
        if connected:
            print("IP        : {}".format(result["ip"]))
            print("Subnet    : {}".format(result["mask"]))
            print("Gateway   : {}".format(result["gateway"]))
            print("DNS       : {}".format(result["dns"]))
            if result["rssi"] is not None:
                print("Signal    : {} dBm ({})".format(
                    result["rssi"], signal_quality(result["rssi"])))
        divider(character="-")
    return result


def ip(quiet=False):
    wlan = _wlan()
    address = wlan.ifconfig()[0] if wlan.isconnected() else None
    _say("IP address: {}".format(address) if address else "Not connected to Wi-Fi.", quiet)
    return address


def security_type(auth_mode):
    names = {0: "Open", 1: "WEP", 2: "WPA", 3: "WPA2", 4: "WPA/WPA2",
             5: "WPA2-Ent", 6: "WPA3", 7: "WPA2/WPA3", 8: "WAPI", 9: "OWE"}
    return names.get(auth_mode, "Unknown({})".format(auth_mode))


def scan(limit=None, quiet=False):
    wlan = _wlan()
    wlan.active(True)
    _gc.collect()
    networks = wlan.scan()
    networks.sort(key=lambda item: item[3], reverse=True)
    if limit is not None:
        del networks[max(0, int(limit)):]
    count = len(networks)
    if not quiet:
        divider("WI-FI NETWORKS")
        print("{:<24} {:>5}  {:<10} {:<10} {}".format(
            "SSID", "RSSI", "QUALITY", "SECURITY", "CH"))
        for entry in networks:
            raw_ssid, _bssid, channel, rssi, security, _hidden = entry
            try:
                name = raw_ssid.decode("utf-8")
            except Exception:
                name = repr(raw_ssid)
            name = name or "<hidden>"
            print("{:<24} {:>5}  {:<10} {:<10} {}".format(
                name[:24], rssi, signal_quality(rssi), security_type(security), channel))
        print("Found {} network(s).".format(count))
        divider(character="-")
    del networks
    _gc.collect()
    return count


def pwd(quiet=False):
    path = _os.getcwd()
    _say(path, quiet)
    return path


def cd(path="/", quiet=False):
    _os.chdir(path)
    return pwd(quiet)


def ls(path=".", quiet=False):
    names = sorted(_os.listdir(path))
    if not quiet:
        divider("FILES: {}".format(path))
        for name in names:
            full = (path.rstrip("/") + "/" + name) if path != "/" else "/" + name
            try:
                stats = _os.stat(full)
                marker = "<DIR>" if stats[0] & 0x4000 else human_size(stats[6])
            except OSError:
                marker = "?"
            print("{:<10} {}".format(marker, name))
        print("{} item(s).".format(len(names)))
        divider(character="-")
    return names


def cat(path, quiet=False):
    with open(path, "r") as handle:
        contents = handle.read()
    if not quiet:
        print(contents, end="" if contents.endswith("\n") else "\n")
    return contents


def rm(path, quiet=False):
    _os.remove(path)
    _say("Removed: {}".format(path), quiet)
    return path


def mv(source, destination, quiet=False):
    _os.rename(source, destination)
    _say("Moved: {} -> {}".format(source, destination), quiet)
    return destination


def mkdir(path, quiet=False):
    _os.mkdir(path)
    _say("Created directory: {}".format(path), quiet)
    return path


def _validate_gpio(pin_number):
    pin_number = int(pin_number)
    if pin_number not in ALLOWED_GPIO_PINS:
        raise ValueError("GPIO{} is not in ALLOWED_GPIO_PINS".format(pin_number))
    return pin_number


def _output_pin(pin_number):
    pin_number = _validate_gpio(pin_number)
    pin = _managed_pins.get(pin_number)
    if pin is None:
        try:
            pin = _machine.Pin(pin_number, _machine.Pin.OUT, value=0)
        except TypeError:
            pin = _machine.Pin(pin_number, _machine.Pin.OUT)
            pin.value(0)
        _managed_pins[pin_number] = pin
    return pin


def high(pin_number, quiet=False):
    pin_number = _validate_gpio(pin_number)
    _output_pin(pin_number).value(1)
    _say("GPIO{}: HIGH".format(pin_number), quiet)
    return 1


def low(pin_number, quiet=False):
    pin_number = _validate_gpio(pin_number)
    _output_pin(pin_number).value(0)
    _say("GPIO{}: LOW".format(pin_number), quiet)
    return 0


def toggle(pin_number, quiet=False):
    pin_number = _validate_gpio(pin_number)
    pin = _output_pin(pin_number)
    value = 0 if pin.value() else 1
    pin.value(value)
    _say("GPIO{}: {}".format(pin_number, "HIGH" if value else "LOW"), quiet)
    return value


def read(pin_number, pull=None, quiet=False):
    pin_number = _validate_gpio(pin_number)
    normalized = pull.lower() if isinstance(pull, str) else pull
    pulls = {None: None, "up": _machine.Pin.PULL_UP, "down": _machine.Pin.PULL_DOWN}
    if normalized not in pulls:
        raise ValueError("pull must be None, 'up', or 'down'")
    pin = _machine.Pin(pin_number, _machine.Pin.IN, pulls[normalized])
    value = pin.value()
    _say("GPIO{}: {}".format(pin_number, "HIGH" if value else "LOW"), quiet)
    return value


def led_on(quiet=False):
    pin = _output_pin(LED_PIN)
    pin.value(1 if LED_ACTIVE_HIGH else 0)
    _say("LED: ON", quiet)
    return True


def led_off(quiet=False):
    pin = _output_pin(LED_PIN)
    pin.value(0 if LED_ACTIVE_HIGH else 1)
    _say("LED: OFF", quiet)
    return False


def led_toggle(quiet=False):
    pin = _output_pin(LED_PIN)
    pin.value(0 if pin.value() else 1)
    is_on = pin.value() == (1 if LED_ACTIVE_HIGH else 0)
    _say("LED: {}".format("ON" if is_on else "OFF"), quiet)
    return is_on


def blink(count=3, interval=0.25, quiet=False):
    count = max(0, int(count))
    delay_ms = max(0, int(float(interval) * 1000))
    for _ in range(count):
        led_on(True)
        _time.sleep_ms(delay_ms)
        led_off(True)
        _time.sleep_ms(delay_ms)
    _say("Blinked {} time(s).".format(count), quiet)
    return count


def _rgb():
    global _rgb_pixel
    if _neopixel is None:
        raise RuntimeError("This firmware does not include the neopixel module")
    if _rgb_pixel is None:
        _rgb_pixel = _neopixel.NeoPixel(_machine.Pin(RGB_PIN), 1)
    return _rgb_pixel


def set_rgb_brightness(percent, quiet=False):
    global RGB_BRIGHTNESS
    percent = max(0, min(100, int(percent)))
    RGB_BRIGHTNESS = percent
    _say("RGB brightness: {}%".format(percent), quiet)
    return percent


def rgb(red, green, blue, brightness=None, quiet=False):
    red, green, blue = int(red), int(green), int(blue)
    if (red < 0 or red > 255 or green < 0 or green > 255 or
            blue < 0 or blue > 255):
        raise ValueError("RGB values must each be between 0 and 255")
    if brightness is None:
        brightness = RGB_BRIGHTNESS
    brightness = max(0, min(100, int(brightness)))
    applied = (red * brightness // 100, green * brightness // 100,
               blue * brightness // 100)
    pixel = _rgb()
    pixel[0] = applied
    pixel.write()
    _say("RGB LED: ({}, {}, {}) at {}%".format(red, green, blue, brightness), quiet)
    return applied


def red(brightness=None, quiet=False):
    return rgb(255, 0, 0, brightness, quiet)


def green(brightness=None, quiet=False):
    return rgb(0, 255, 0, brightness, quiet)


def blue(brightness=None, quiet=False):
    return rgb(0, 0, 255, brightness, quiet)


def rgb_off(quiet=False):
    return rgb(0, 0, 0, 100, quiet)


def cleanup(disconnect_wifi=False, rgb_off=True, quiet=False):
    global _rgb_pixel
    pin_numbers = tuple(_managed_pins)
    for pin_number in pin_numbers:
        try:
            _managed_pins[pin_number].init(mode=_machine.Pin.IN, pull=None)
        except Exception:
            _machine.Pin(pin_number, _machine.Pin.IN)
    _managed_pins.clear()
    if rgb_off and _rgb_pixel is not None:
        try:
            _rgb_pixel[0] = (0, 0, 0)
            _rgb_pixel.write()
        except Exception:
            pass
        _rgb_pixel = None
        try:
            _machine.Pin(RGB_PIN, _machine.Pin.IN)
        except Exception:
            pass
    if disconnect_wifi:
        disconnect(deactivate=True, quiet=True)
    _gc.collect()
    _say("Cleanup complete; released {} managed pin(s).".format(len(pin_numbers)), quiet)
    return len(pin_numbers)


def help():
    """Print a compact command reference."""
    print("toolbox.py v{}".format(__version__))
    print("System : info, uptime, mem, gc, disk, cpu, cpu160, cpu240")
    print("Reset  : reset, reboot, soft_reset")
    print("Wi-Fi : connect, disconnect, net, ip, scan")
    print("Files  : pwd, cd, ls, cat, rm, mv, mkdir")
    print("GPIO   : high, low, toggle, read, cleanup")
    print("LED    : led_on, led_off, led_toggle, blink")
    print("RGB    : rgb, red, green, blue, rgb_off, set_rgb_brightness")
    print("Most action helpers accept quiet=True for dashboard use.")
    return __version__
