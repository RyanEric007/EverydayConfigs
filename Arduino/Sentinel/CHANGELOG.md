# RyancitoSentinal v4

## v4.6 BLE forensic analysis

- Added the official IEEE MA-L OUI CSV link and import instructions to the
  built-in Help guide.
- Added decoded-field and raw-byte diffs for the latest distinct BLE
  advertisements.
- Added distinct-payload history with occurrence counts and time windows.
- Added minimum, maximum, average, median, and signal-volatility statistics.
- Added an observation-gap presence timeline with an explicit evidentiary
  limitation.
- Added persistent bookmarks for specific advertisement changes; bookmark
  details remain analyst-derived annotations and are exported with evidence.

## v4.5 manufacturer identification

- Added browser-side decoding for common Bluetooth SIG company identifiers.
- Added persistent import and clearing of IEEE MA-L or simple OUI/vendor CSV
  databases for WiFi BSSID lookup.
- Added manufacturer source and confidence language to BLE and WiFi detail
  cards.
- Added derived manufacturer information to JSON and CSV evidence exports.
- Locally administered WiFi addresses are explicitly identified as unsuitable
  for OUI vendor lookup.

## v4.4 status and filter ordering

- Status now presents Client before Connection (`Mac · Live · latency`).
- BLE signal filters are ordered nearest to farthest.

## v4.3 dashboard flow

- Positioned Explainable Insights directly below Status and above both radio
  sections to make clear that it summarizes BLE and WiFi.
- Made every insight open its related BLE or WiFi detail card.
- Replaced the separate Show All and Show Ignored controls with Clear Filters.
- Combined connection state and browser client into one aligned Status field.
- Standardized visible dashboard wording to WiFi and removed redundant
  “Nearby” labels.

## v4.2 evidence clear and signal filters

- Clear Browser Evidence now reloads the dashboard after IndexedDB deletion
  and creates exactly one clean replacement session.
- The BLE color legend is now a set of persistent display-filter buttons.
- Signal-band filters never remove raw observations from storage or exports.
- Print reports include only enabled signal-band labels and retain their solid
  colors.

## v4.1 session reset correction

- New Session and Clear Browser Evidence now reset both BLE and Wi-Fi DOM
  tables, counters, trends, annotations, insights, open detail state, and
  session-library state.
- Added explicit progress/success/failure feedback.
- IndexedDB deletion now reports when another open dashboard tab blocks it.

## Evidence workflow

- Added Session Library with review, rename, comparison, historical export,
  selective deletion, and explicit session closing.
- Added JSON import and SHA-256 verification.
- Added evidence schema version and documented hash procedure.
- Added ESP32 monotonic time, browser receipt time, estimated wall-clock time,
  timestamp source, and timing uncertainty to BLE observations.
- Added per-device analyst annotations, classifications, tags, and watchlists.
- Added browser storage usage and optional session retention.

## Analysis

- Added explainable insights for new and strong BLE identifiers, changed BLE
  advertisements, watchlist observations, open Wi-Fi, duplicate SSIDs, and
  Wi-Fi channel/security changes.
- Added timeline previews and two-session identifier comparisons.
- Expanded BLE decoding for 32-bit and 128-bit service UUIDs, service data,
  TX power, and Appearance.
- Replaced distance and movement claims with signal bands and signal trends.
- Renamed sightings to recorded observations.

## Reliability and security

- Rate-limited forced Wi-Fi scans to one every five seconds.
- Added raw-ring high-water mark and HTTP request count diagnostics.
- Fallback AP mode no longer becomes open when a configured password is too
  short; it uses the documented secure fallback password instead.
- Preserved fixed-size ESP32 rings, browser-side aggregation, and bounded
  device tracking.
