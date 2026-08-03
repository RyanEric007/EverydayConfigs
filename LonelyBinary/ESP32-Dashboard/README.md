# 🎛️ ESP32-S3 PinPulse Dashboard

A lightweight, self-hosted control dashboard for an ESP32-S3 running MicroPython. The ESP32 serves the webpage directly over your local Wi-Fi network—no cloud account, external server, or internet connection is required after setup.

The dashboard includes:

- 📊 CPU, memory, storage, uptime, and Wi-Fi telemetry
- 🌈 Onboard RGB/NeoPixel color and brightness controls
- 🔌 Live GPIO state monitoring and output controls
- 📡 Nearby 2.4 GHz Wi-Fi network scanning
- 🟦 Passive Bluetooth Low Energy advertisement scanning
- 🏭 MAC vendor identification using the IEEE OUI database
- ⚙️ A configuration and help drawer
- 🖨️ Black-and-white PDF reports with RGB controls preserved in color
- 🔄 Browser-side OUI persistence and reset controls

## 📁 Repository contents

```text
ESP32-Dashboard/
├── .gitignore
├── boot.py
├── index.html
├── main.py
├── README.md
├── secrets.py
└── toolbox.py
```

| File | Copy to ESP32? | Purpose |
|---|:---:|---|
| `boot.py` | ✅ | Runs first and performs small boot-time setup. |
| `main.py` | ✅ | Starts Wi-Fi and the dashboard web server automatically. |
| `index.html` | ✅ | Complete dashboard interface, styling, and browser-side JavaScript. |
| `toolbox.py` | ✅ | Shared ESP32-S3 helpers for Wi-Fi, GPIO, RGB, memory, and CPU controls. |
| `secrets.py` | ✅ | Your private 2.4 GHz Wi-Fi name and password. |
| `README.md` | ❌ | Setup and usage documentation for people. |
| `.gitignore` | ❌ | Prevents private or generated files from being committed to Git. |
| `oui.csv` | ❌ | Imported through the dashboard in your browser; never loaded by the ESP32. |

## 🚀 Quick start

### 1. Install MicroPython

Install a compatible ESP32-S3 MicroPython firmware on the board. Confirm that you can reach the MicroPython REPL before copying the project files.

The firmware must include these standard modules:

```text
machine
network
socket
bluetooth
neopixel
```

### 2. Configure Wi-Fi

Open `secrets.py` and replace the placeholders with the credentials for a **2.4 GHz Wi-Fi network**:

```python
SSID = "YOUR_WIFI_NAME"
PASSWORD = "YOUR_WIFI_PASSWORD"
```

The ESP32-S3 cannot connect to a 5 GHz-only network.

> 🔐 **Do not publish real credentials.** `secrets.py` is excluded by `.gitignore`, but Git will continue tracking it if it was already committed. Remove it from Git tracking before adding real credentials, or keep the repository private.

### 3. Copy the runtime files to the board

Copy these five files to the **root** of the ESP32 MicroPython filesystem:

```text
/
├── boot.py
├── main.py
├── index.html
├── secrets.py
└── toolbox.py
```

Do not place them inside another directory on the ESP32. MicroPython automatically looks for `/boot.py` and `/main.py` at startup, and `main.py` expects `/index.html`, `toolbox.py`, and `secrets.py` beside it.

You can transfer the files using Thonny, mpremote, WebREPL, or another MicroPython file manager.

### 4. Reset the board

After the files are copied, reset or power-cycle the ESP32.

MicroPython starts the project in this order:

```text
boot.py → main.py → connect to Wi-Fi → start dashboard server
```

The serial console should print an address similar to:

```text
PinPulse dashboard is online
http://192.168.1.123:80
```

Open that address from a device connected to the same local network.

## 🏭 Adding the IEEE OUI vendor database

An OUI is the first portion of a globally assigned MAC address. IEEE publishes a public MA-L/OUI listing that maps those prefixes to registered organizations.

### Download and import it

1. Download the current official [IEEE `oui.csv`](https://standards-oui.ieee.org/oui/oui.csv).
2. Save it as `oui.csv` on your computer, phone, or tablet.
3. Open the ESP32 dashboard.
4. Select the ⚙️ configuration icon.
5. Find **MAC identification**.
6. Select **Import OUI.csv**.
7. Choose the downloaded `oui.csv` file.
8. Wait for the dashboard to report how many OUI records were saved.

The browser stores the imported records in IndexedDB and reloads them automatically on later visits.

### Why the database stays in the browser

The full IEEE database is much larger than the ESP32 application and changes over time. Processing and storing it in the browser provides several benefits:

- 🧠 Preserves the ESP32’s limited heap
- 💾 Avoids consuming board flash unnecessarily
- ⚡ Moves CSV parsing and vendor matching to the faster browser
- 🔄 Lets you replace the database without reflashing or rewriting board files
- 📶 Keeps Wi-Fi and BLE scan responses compact
- 📴 Continues working locally after the initial import

Because browser storage belongs to a specific webpage origin, you may need to import the database again if the ESP32 receives a different IP address or you open it from a different browser/profile.

> ℹ️ OUI results normally identify the registered network-interface vendor—not the device model, owner, location, safety, or trustworthiness. Randomized and locally administered addresses usually cannot be identified reliably.

### Clear saved data

The configuration drawer provides two controls:

- **Clear OUI** removes only the saved vendor database.
- **Reset browser data** removes the OUI database and dashboard browser settings.

Neither control erases files or settings stored on the ESP32.

## 🔌 GPIO matrix and safety modes

The dashboard displays GPIO0 through GPIO48, but not every number is a usable physical pin on the ESP32-S3.

### Safe mode

Safe mode is enabled after every boot. Only GPIOs in the configured board allowlist can be controlled. Other tiles remain visibly locked, and `main.py` rejects attempts to change them even if someone manually calls the API.

### Expert mode

The configuration drawer includes **Expert GPIO unlock**. It requires typing `UNLOCK` and temporarily enables GPIO0, GPIO43, and GPIO44:

- GPIO0 is a boot-strapping pin. Holding it LOW during reset can start download mode.
- GPIO43 is normally UART0 TX.
- GPIO44 is normally UART0 RX.

Using GPIO43 or GPIO44 can interrupt serial logs, the REPL, or UART firmware uploads. Expert mode ends when you relock it or restart the board.

Critical USB, flash/PSRAM, strapping, nonexistent, and onboard RGB pins remain locked in both modes. Unlocking a tile is permission—not electrical verification. Always check the exact board and module schematic before attaching hardware.

## 🌈 RGB control

The RGB panel selects an unscaled color and a brightness percentage. For example:

```text
Selected color: (0, 255, 255)
Brightness: 10%
Applied output: (0, 25, 25)
```

The console reports the selected percentage while `toolbox.py` applies the corresponding scaled LED values.

## 📡 Wireless scans

### Wi-Fi spectrum

The Wi-Fi scan reports nearby access points with SSID, BSSID, RSSI, quality, security, channel, and OUI vendor when available.

### Bluetooth spectrum

The BLE scan listens passively for advertisements for approximately four seconds. It reports names when advertised, signal strength, address, address type, vendor lookup, and whether the advertisement appears connectable.

Wi-Fi and Bluetooth share the ESP32-S3’s 2.4 GHz radio. A scan can briefly delay other dashboard requests. The browser displays scan progress and a useful error if the operation fails.

## 🖨️ Printing and PDF reports

Open Configuration, choose portrait or landscape, and select **Print / Save PDF**. Use your browser’s print dialog to select a printer or **Save as PDF**.

Reports are printed in black and white to remain readable and economical. The RGB spectrum panel preserves its selected color.

## 🛠️ Troubleshooting

### The dashboard does not start

- Confirm all five runtime files are in the ESP32 filesystem root.
- Confirm the HTML file is named exactly `index.html`.
- Check the serial console for a Python exception.
- Confirm `secrets.py` contains valid credentials.

### Wi-Fi will not connect

- Use a 2.4 GHz network.
- Check capitalization and punctuation in `SSID` and `PASSWORD`.
- Move the ESP32 closer to the access point.
- Reset the board after editing `secrets.py`.

### The webpage does not open

- Use the exact IP address printed in the serial console.
- Make sure the browser device is on the same network.
- Disable client isolation on the Wi-Fi network if local devices cannot communicate.
- The board’s IP address may change after a router restart.

### BLE finds no devices

- Wait for the full four-second scan to finish.
- Move BLE devices closer and make sure they are advertising.
- Confirm the MicroPython firmware includes the `bluetooth` module.
- Retry after a Wi-Fi scan finishes because both use the same radio.

### OUI data disappeared

- Confirm you are using the same browser, profile, and ESP32 IP address.
- Private browsing may discard IndexedDB data.
- Browser storage cleanup removes the saved database.
- Import the latest IEEE file again when needed.

## 🔒 Privacy and responsible use

Wireless scan results are observations, not proof of ownership, identity, intent, or continued presence. Modern devices frequently rotate BLE and Wi-Fi addresses. Use the dashboard only on networks, equipment, and locations where you have permission to scan and test.

## 🧩 Customization

Board-specific settings are near the top of `main.py` and `toolbox.py`, including:

- HTTP port
- HTML filename
- Wi-Fi and BLE result limits
- GPIO allowlist
- Hard-blocked GPIO list
- RGB and regular LED pins
- Client and polling timing

Verify hardware changes against the exact schematic before editing GPIO safety lists.
