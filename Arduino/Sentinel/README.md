# RyancitoSentinal Optimized

## Files to upload to the Nano ESP32

- `main.py`
- `index.html`
- `style.css`
- `app.js`
- `worker.js`
- your private `secret.py`

All files must be placed in the root of the MicroPython filesystem.

## Connection behavior

The collector tries `HOME_SSID` from `secret.py`. If that fails, it starts
`AP_SSID`. The dashboard URL is printed in the REPL. Fallback AP mode normally
uses `http://192.168.4.1/`.

## Collector behavior

- BLE scanning runs continuously.
- The BLE IRQ only copies and enqueues transient scan data.
- A 96-record ingress ring bounds IRQ-side memory.
- A 512-record evidence ring bounds API history.
- A 160-device state table bounds deduplication state.
- Evidence is emitted on first sighting, advertisement changes, RSSI changes
  of at least 5 dB, or a 1-second heartbeat.
- No evidence is written to ESP32 flash.
- Wi-Fi surveys are cached and rate-limited to protect BLE collection time.
- BLE scanning pauses briefly during the ESP32's blocking WLAN scan, then
  resumes automatically.
- `/api/updates?after=N&limit=50` returns compact sequence batches.
- `/api/status` reports buffer use, dropped records, heap, firmware, and scan
  configuration.
- `/api/wifi` returns the latest cached Wi-Fi survey.

Compact item schema:

```text
[seq, elapsed_ms, addr_type, mac, rssi, adv_type, flags, adv_hex]
```

Flag bits:

- `1`: first seen
- `2`: advertisement changed
- `4`: significant RSSI change
- `8`: heartbeat interval elapsed

## Browser behavior

- A Web Worker polls and aggregates observations.
- Raw observations and sessions are stored in IndexedDB.
- Wi-Fi snapshots use a separate IndexedDB object store.
- UI preferences and hidden-device IDs are stored in localStorage.
- Rendering is coalesced to approximately 300 ms.
- Existing DOM rows are updated instead of rebuilding the complete table.
- Worker messages contain only changed device summaries, not the full device
  collection.
- The table renders at most 300 rows while all raw evidence remains in
  IndexedDB.
- Click sortable table headings to change field and direction.
- Pausing freezes the display only; background polling and evidence recording
  continue.
- JSON export separates observed data, derived device summaries, and
  annotations.
- JSON and CSV exports include SHA-256 evidence hashes.

Double-click a device row to hide it. Use Settings to reveal hidden devices.

## Memory and continuity

The ESP32 rings and Wi-Fi cache are intentionally volatile and reset on power loss. Long-term
evidence lives in the browser's IndexedDB. Sequence-reset detection
automatically starts a new browser session after an ESP32 restart.

Keep the browser open until its latest polling request succeeds before
disconnecting power if the newest observations are important.
