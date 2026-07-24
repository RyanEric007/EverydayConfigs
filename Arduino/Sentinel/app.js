const $ = selector => document.querySelector(selector);
const settings = Object.assign({
  theme: "dark", minRssi: -100, pollMs: 500, wifiMs: 60000,
  showHidden: false, showWifi: true, showBle: true, compact: false,
  hidden: [], collapsed: [], bleSort: "latestRssi", bleSortDir: -1,
  wifiSort: "rssi", wifiSortDir: -1, printOrientation: "landscape"
}, JSON.parse(localStorage.getItem("sentinal-ui") || "{}"));
const hidden = new Set(settings.hidden || []);
const worker = new Worker("/worker.js?v=2.5");
const rows = new Map();
const deviceStore = new Map();
let devices = [];
let observationCount = 0;
let dropped = 0;
let dirty = false;
let sessionId = "";
let wifiNetworks = [];
let wifiDirty = false;
let paused = false;
const MAX_RENDER_ROWS = 300;
const wifiRows = new Map();
const wifiPrevious = new Map();

function saveSettings() {
  settings.hidden = [...hidden];
  localStorage.setItem("sentinal-ui", JSON.stringify(settings));
  worker.postMessage({
    type: "settings", pollMs: Number(settings.pollMs),
    wifiMs: Number(settings.wifiMs), showWifi: settings.showWifi
  });
  dirty = true;
}

function trend(device) {
  const delta = device.latestRssi - device.previousRssi;
  if (device.sightings === 1) return ["NEW", "new"];
  if (delta >= 4) return [`↑ +${delta} dB`, "up"];
  if (delta <= -4) return [`↓ ${delta} dB`, "down"];
  return [`→ ${delta >= 0 ? "+" : ""}${delta} dB`, "steady"];
}
function proximity(rssi) {
  if (rssi >= -50) return ["Right next to it", "blue"];
  if (rssi >= -62) return ["Around 5 ft", "green"];
  if (rssi >= -70) return ["Around 10 ft", "yellow"];
  if (rssi >= -75) return ["Around 15 ft", "red"];
  return ["Beyond ~15 ft", "off"];
}
function signalWidth(rssi) {
  return Math.max(0, Math.min(100, Math.round((rssi + 100) * 1.8)));
}
function addressType(value) {
  return ({ 0: "Public", 1: "Random", 2: "Public ID", 3: "Random ID" })[value] || `Type ${value}`;
}
function visibleDevices() {
  const query = $("#search").value.trim().toLowerCase();
  const result = devices.filter(device => {
    if (device.latestRssi < Number(settings.minRssi)) return false;
    if (hidden.has(device.id) && !settings.showHidden) return false;
    if (!query) return true;
    return `${device.name} ${device.mac} ${device.manufacturer} ${device.services.join(" ")}`.toLowerCase().includes(query);
  });
  const key = settings.bleSort;
  result.sort((a, b) => {
    const left = a[key] ?? "", right = b[key] ?? "";
    const comparison = typeof left === "string" ?
      left.localeCompare(right) : left - right;
    return comparison * settings.bleSortDir;
  });
  return result;
}

function updateRow(device) {
  let row = rows.get(device.id);
  if (!row) {
    row = document.createElement("tr");
    row.innerHTML = "<td></td><td class='rssi'></td><td><span class='signal-track'><i></i></span></td><td></td><td></td><td></td><td></td><td></td><td></td><td class='filter-cell'><label><input type='checkbox'> Ignore</label></td>";
    row.querySelector("input").addEventListener("change", event => {
      if (event.target.checked) hidden.add(device.id); else hidden.delete(device.id);
      saveSettings();
    });
    rows.set(device.id, row);
  }
  const cells = row.children;
  const movement = trend(device);
  const distance = proximity(device.latestRssi);
  const details = [device.manufacturer, ...device.services].filter(Boolean).join(" | ") || "No decoded data";
  const values = [
    device.name, `${device.latestRssi}`, null, movement[0], distance[0],
    device.sightings, addressType(device.addrType), device.mac, details, null
  ];
  for (let i = 0; i < values.length; i++) {
    if (values[i] === null) continue;
    const value = String(values[i]);
    if (cells[i].textContent !== value) cells[i].textContent = value;
  }
  cells[3].className = movement[1];
  const proximityHtml = `<span class="dot ${distance[1]}"></span>${distance[0]}`;
  if (cells[4].innerHTML !== proximityHtml) cells[4].innerHTML = proximityHtml;
  cells[2].querySelector("i").style.width = `${signalWidth(device.latestRssi)}%`;
  cells[9].querySelector("input").checked = hidden.has(device.id);
  return row;
}

function renderWifi() {
  if (!wifiDirty) return;
  wifiDirty = false;
  const body = $("#wifiRows");
  const fragment = document.createDocumentFragment();
  const keep = new Set();
  const visibleWifi = wifiNetworks.filter(
    network => network.rssi >= Number(settings.minRssi));
  visibleWifi.sort((a, b) => {
    const left = a[settings.wifiSort] ?? "", right = b[settings.wifiSort] ?? "";
    const comparison = typeof left === "string" ?
      left.localeCompare(right) : left - right;
    return comparison * settings.wifiSortDir;
  });
  for (const network of visibleWifi) {
    let row = wifiRows.get(network.bssid);
    if (!row) {
      row = document.createElement("tr");
      row.innerHTML = "<td></td><td class='rssi'></td><td><span class='signal-track'><i></i></span></td><td></td><td></td><td></td><td></td>";
      wifiRows.set(network.bssid, row);
    }
    const previous = wifiPrevious.get(network.bssid);
    const delta = previous === undefined ? null : network.rssi - previous;
    const movement = delta === null ? ["NEW", "new"] : delta >= 4 ? [`↑ +${delta} dB`, "up"] : delta <= -4 ? [`↓ ${delta} dB`, "down"] : [`→ ${delta >= 0 ? "+" : ""}${delta} dB`, "steady"];
    const cells = row.children;
    const values = [network.hidden ? "Hidden" : network.ssid, network.rssi, null, movement[0], network.channel, network.security, network.bssid];
    for (let i = 0; i < values.length; i++) {
      if (values[i] === null) continue;
      if (cells[i].textContent !== String(values[i])) cells[i].textContent = values[i];
    }
    cells[2].querySelector("i").style.width = `${signalWidth(network.rssi)}%`;
    cells[3].className = movement[1];
    wifiPrevious.set(network.bssid, network.rssi);
    keep.add(network.bssid); fragment.appendChild(row);
  }
  for (const [id, row] of wifiRows) if (!keep.has(id)) {
    if (row.parentNode) row.remove();
    wifiRows.delete(id);
    wifiPrevious.delete(id);
  }
  body.appendChild(fragment);
  $("#wifiCount").textContent = visibleWifi.length;
  $("#wifiEmpty").hidden = visibleWifi.length > 0;
}

function render() {
  if (paused) return;
  if (!dirty) return;
  dirty = false;
  const visible = visibleDevices();
  const rendered = visible.slice(0, MAX_RENDER_ROWS);
  const fragment = document.createDocumentFragment();
  const keep = new Set();
  for (const device of rendered) {
    const row = updateRow(device); keep.add(device.id); fragment.appendChild(row);
  }
  for (const [id, row] of rows) if (!keep.has(id)) {
    if (row.parentNode) row.remove();
    rows.delete(id);
  }
  $("#deviceRows").appendChild(fragment);
  $("#emptyState").hidden = visible.length > 0;
  $("#visibleCount").textContent = visible.length > MAX_RENDER_ROWS ?
    `${MAX_RENDER_ROWS} of ${visible.length}` : visible.length;
  $("#deviceCount").textContent = devices.length;
  $("#observationCount").textContent = observationCount;
  $("#droppedCount").textContent = dropped;
  renderWifi();
}
setInterval(render, 300);

worker.onmessage = event => {
  const message = event.data;
  if (message.type === "dirty") {
    for (const device of message.updates) deviceStore.set(device.id, device);
    devices = [...deviceStore.values()];
    observationCount = message.after;
    dropped = message.dropped;
    dirty = true;
  } else if (message.type === "connection") {
    if (!paused) $("#connectionState").textContent = message.state;
  } else if (message.type === "session") {
    sessionId = message.sessionId; deviceStore.clear(); devices = []; rows.clear(); dirty = true;
  } else if (message.type === "wifi") {
    wifiNetworks = message.networks; wifiDirty = true; dirty = true;
  } else if (message.type === "export") {
    prepareExport(message);
  } else if (message.type === "exportError") {
    $("#exportStatus").textContent = `Export failed: ${message.error}`;
  }
};

async function prepareExport(message) {
  let collector = {};
  try { collector = await fetch("/api/status", { cache: "no-store" }).then(r => r.json()); }
  catch (error) { collector = { error: String(error) }; }
  const metadata = {
    sessionId: message.sessionId,
    sessionStartTime: new Date(message.sessionStartTime).toISOString(),
    sessionEndTime: new Date(message.sessionEndTime).toISOString(),
    firmware: { name: collector.firmware || "unknown", version: collector.version || "unknown" },
    scanConfiguration: collector.config || {},
    exportedAt: new Date().toISOString(),
    observationCount: message.observations.length + message.wifiObservations.length,
    droppedRecordCount: message.dropped,
    observed: {
      bleObservations: message.observations,
      wifiObservations: message.wifiObservations
    },
    derived: { devices },
    annotations: []
  };
  if (message.format === "json") {
    const canonical = JSON.stringify(metadata);
    metadata.sha256 = await sha256(canonical);
    download(`RyancitoSentinal-${message.sessionId}.json`, "application/json", JSON.stringify(metadata, null, 2));
  } else {
    const lines = ["radio,sessionId,sequence,receivedAt,identifier,rssi,channel,security,advType,flags,raw"];
    for (const o of message.observations) lines.push([
      "BLE", o.sessionId, o.seq, new Date(o.receivedAt).toISOString(), o.mac,
      o.rssi, "", "", o.advType, o.flags, o.advHex
    ].map(value => `"${String(value).replaceAll('"', '""')}"`).join(","));
    for (const o of message.wifiObservations) lines.push([
      "Wi-Fi", o.sessionId, o.scan, new Date(o.receivedAt).toISOString(), o.bssid,
      o.rssi, o.channel, o.security, "", "", "SSID: " + o.ssid
    ].map(value => `"${String(value).replaceAll('"', '""')}"`).join(","));
    const body = lines.join("\r\n");
    const hash = await sha256(body);
    download(`RyancitoSentinal-${message.sessionId}.csv`, "text/csv",
      body + `\r\n# SHA-256,"${hash}"\r\n`);
  }
  $("#exportStatus").textContent = `Export ready — ${message.observations.length} BLE and ${(message.wifiObservations || []).length} Wi-Fi records`;
}

async function sha256(text) {
  if (globalThis.crypto && crypto.subtle) {
    try {
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
      return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("");
    } catch (error) { }
  }
  return sha256Fallback(new TextEncoder().encode(text));
}

function sha256Fallback(bytes) {
  const K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
  const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const bitLength = bytes.length * 8;
  const paddedLength = ((bytes.length + 9 + 63) >> 6) << 6;
  const data = new Uint8Array(paddedLength); data.set(bytes); data[bytes.length] = 0x80;
  const view = new DataView(data.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);
  const w = new Uint32Array(64);
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i++)w[i] = view.getUint32(offset + i * 4, false);
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
  }
  return H.map(value => value.toString(16).padStart(8, "0")).join("");
}
function download(name, type, content) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], { type }));
  link.download = name; document.body.appendChild(link); link.click(); link.remove();
  $("#exportStatus").textContent = `Preparing ${name}…`;
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

async function refreshDiagnostics() {
  try {
    const status = await fetch("/api/status", { cache: "no-store" }).then(r => r.json());
    $("#diagnostics").textContent = JSON.stringify(status, null, 2);
    $("#collectorSsid").textContent = status.ssid || "—";
    $("#collectorIp").textContent = status.ip || "—";
    $("#collectorVersion").textContent = `${status.firmware} ${status.version}`;
    $("#collectorHeap").textContent = `${(status.free_heap / 1048576).toFixed(2)} MB`;
    $("#collectorBuffer").textContent = `${status.raw_buffer_used}/${status.raw_buffer_capacity} raw`;
  } catch (error) { $("#diagnostics").textContent = String(error); }
}
setInterval(refreshDiagnostics, 5000); refreshDiagnostics();

function applySettings() {
  document.body.classList.toggle("light", settings.theme === "light");
  $("#theme").value = settings.theme;
  $("#minRssi").value = String(settings.minRssi);
  $("#pollMs").value = String(settings.pollMs);
  $("#showHiddenTop").checked = settings.showHidden;
  $("#showWifi").checked = settings.showWifi;
  $("#showBle").checked = settings.showBle;
  $("#compact").checked = settings.compact;
  $("#wifiMs").value = String(settings.wifiMs);
  $("#printOrientation").value = settings.printOrientation;
  $(".wifi-card").hidden = !settings.showWifi;
  $(".devices-card").hidden = !settings.showBle;
  document.body.classList.toggle("compact", settings.compact);
  updatePrintOrientation();
  wifiDirty = true;
  saveSettings();
}
$("#settingsButton").onclick = () => document.body.classList.add("drawer-open");
$("#closeSettings").onclick = $("#backdrop").onclick = () => document.body.classList.remove("drawer-open");
$("#theme").onchange = event => { settings.theme = event.target.value; applySettings(); };
$("#minRssi").onchange = event => { settings.minRssi = Number(event.target.value); applySettings(); };
$("#pollMs").onchange = event => { settings.pollMs = Number(event.target.value); applySettings(); };
$("#showHiddenTop").onchange = event => { settings.showHidden = event.target.checked; applySettings(); };
$("#showWifi").onchange = event => { settings.showWifi = event.target.checked; applySettings(); };
$("#showBle").onchange = event => { settings.showBle = event.target.checked; applySettings(); };
$("#compact").onchange = event => { settings.compact = event.target.checked; applySettings(); };
$("#wifiMs").onchange = event => { settings.wifiMs = Number(event.target.value); applySettings(); };
$("#printOrientation").onchange = event => {
  settings.printOrientation = event.target.value;
  applySettings();
};
$("#search").oninput = () => dirty = true;
$("#newSession").onclick = () => worker.postMessage({ type: "newSession" });
$("#clearBrowserData").onclick = () => {
  if (confirm("Delete all browser evidence?")) worker.postMessage({ type: "clear" });
};
$("#exportJson").onclick = () => worker.postMessage({ type: "export", format: "json" });
$("#exportCsv").onclick = () => worker.postMessage({ type: "export", format: "csv" });

function printReport() {
  document.body.classList.remove("drawer-open");
  document.body.classList.add("printing");
  updatePrintOrientation();
  window.print();
}
$("#printReportTop").onclick = printReport;
window.addEventListener("afterprint", () => document.body.classList.remove("printing"));

function updatePrintOrientation() {
  let style = document.getElementById("dynamicPrintPage");
  if (!style) {
    style = document.createElement("style");
    style.id = "dynamicPrintPage";
    document.head.appendChild(style);
  }
  const orientation = settings.printOrientation === "portrait" ? "portrait" : "landscape";
  document.body.classList.toggle("print-portrait", orientation === "portrait");
  style.textContent = `@page { size: ${orientation}; margin: .35in; }`;
}

document.querySelectorAll(".collapse-button").forEach(button => {
  const target = document.getElementById(button.dataset.target);
  const collapsed = settings.collapsed.includes(button.dataset.target);
  target.hidden = collapsed; button.textContent = collapsed ? "⌄" : "⌃";
  button.onclick = () => {
    target.hidden = !target.hidden;
    button.textContent = target.hidden ? "⌄" : "⌃";
    settings.collapsed = [...document.querySelectorAll(".collapsible[hidden]")].map(node => node.id);
    saveSettings();
  };
});

function updateSortIndicators() {
  document.querySelectorAll("th[data-ble-sort],th[data-wifi-sort]").forEach(th => {
    const isBle = th.dataset.bleSort && th.dataset.bleSort === settings.bleSort;
    const isWifi = th.dataset.wifiSort && th.dataset.wifiSort === settings.wifiSort;
    const active = isBle || isWifi;
    th.classList.toggle("sort-active", active);
    th.dataset.arrow = active ?
      ((isBle ? settings.bleSortDir : settings.wifiSortDir) > 0 ? "▲" : "▼") : "";
  });
}
document.querySelectorAll("th[data-ble-sort]").forEach(th => th.onclick = () => {
  const key = th.dataset.bleSort;
  settings.bleSortDir = settings.bleSort === key ? -settings.bleSortDir : (key === "name" || key === "mac" || key === "manufacturer" ? 1 : -1);
  settings.bleSort = key; saveSettings(); updateSortIndicators();
});
document.querySelectorAll("th[data-wifi-sort]").forEach(th => th.onclick = () => {
  const key = th.dataset.wifiSort;
  settings.wifiSortDir = settings.wifiSort === key ? -settings.wifiSortDir : (key === "ssid" || key === "security" || key === "bssid" ? 1 : -1);
  settings.wifiSort = key; wifiDirty = true; dirty = true; saveSettings(); updateSortIndicators();
});
$("#pauseDisplay").onclick = event => {
  paused = !paused;
  event.target.textContent = paused ? "Resume display" : "Pause display";
  $("#connectionState").textContent = paused ? "Paused (recording)" : "Live";
  if (!paused) { dirty = true; render(); }
};
updateSortIndicators();
updatePrintOrientation();
applySettings();
