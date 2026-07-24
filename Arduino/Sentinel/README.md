# RyancitoSentinal v4

## Files to upload to the Nano ESP32

- `main.py`
- `index.html`
- `style.css`
- `app.js`
- `worker.js`
- your private `secret.py`

All files must be placed in the root of the MicroPython filesystem.

## Connection behavior

The collector tries `DEFAULT_SSID` from `secret.py`. If that fails, it starts
`AP_SSID`. `DEFAULT_PASSWORD` is the matching password. Older `HOME_SSID` and
`HOME_PASSWORD` names are accepted temporarily for migration. The dashboard
URL is printed in the REPL. Fallback AP mode normally uses
`http://192.168.4.1/`.

`AP_PASSWORD` must contain at least eight characters. A shorter configured
password never creates an open access point; firmware uses `ryancito1337` as
the secure recovery password and prints a warning in the REPL.

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
- **Scan Wi-Fi now** forces an immediate survey and then resumes the normal
  schedule.
- Wi-Fi trends compare the same BSSID across consecutive completed surveys.
  Changes of at least 4 dB are labeled stronger or weaker; smaller changes are
  labeled stable. Sorting and screen refreshes do not alter the comparison.
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
- BLE color chips are persistent display filters. Turning a band off hides its
  rows without deleting or excluding its raw evidence from exports.
- Pausing freezes the display only; background polling and evidence recording
  continue.
- Settings includes a collapsible plain-language help guide covering controls,
  sessions, exports, RSSI limitations, privacy, and evidence handling.
- JSON export separates observed data, derived device summaries, and
  annotations.
- JSON and CSV exports include SHA-256 evidence hashes.
- Session Library reviews, renames, compares, exports, and selectively deletes
  browser sessions.
- New Session resets both live radios while preserving closed sessions. Clear
  Browser Evidence deletes all sessions, observations, and annotations, then
  reloads the dashboard into one empty fresh session.
- JSON imports can be verified against their embedded SHA-256 hash.
- BLE records separate ESP32 monotonic time, browser receipt time, estimated
  wall-clock time, timestamp source, and timing uncertainty.
- Analyst annotations, classifications, tags, and watchlists remain separate
  from observed data.
- Explainable insights report measurable changes without claiming malicious
  intent.
- Browser storage usage and optional session retention are visible in
  Settings.

## Client identification

The Status card identifies the browser client as iPhone, iPad, Android, Mac,
Windows PC, Linux computer, or a generic browser client. This is a lightweight
display hint based on browser information; it is not stored as sensor evidence
and it does not fingerprint or uniquely identify the device.

Double-click a device row to hide it. Use Settings to reveal hidden devices.

## Memory and continuity

The ESP32 rings and Wi-Fi cache are intentionally volatile and reset on power loss. Long-term
evidence lives in the browser's IndexedDB. Sequence-reset detection
automatically starts a new browser session after an ESP32 restart.

Keep the browser open until its latest polling request succeeds before
disconnecting power if the newest observations are important.
