const DB_NAME = "RyancitoSentinalEvidence";
const DB_VERSION = 2;
let db;
let sessionId;
let after = 0;
let polling = true;
let pollMs = 500;
let dropped = 0;
let retryMs = 1000;
let wifiMs = 60000;
let showWifi = true;
let lastWifiScan = 0;
let wifiTimer = null;
let wifiNetworks = [];
let sessionStartTime = 0;
const devices = new Map();

function uuid() {
  if (self.crypto && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains("observations")) {
        const observations = database.createObjectStore("observations", { keyPath: ["sessionId", "seq"] });
        observations.createIndex("sessionId", "sessionId");
      }
      if (!database.objectStoreNames.contains("sessions")) {
        database.createObjectStore("sessions", { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains("annotations")) {
        database.createObjectStore("annotations", { keyPath: ["sessionId", "deviceId"] });
      }
      if (!database.objectStoreNames.contains("wifiObservations")) {
        const wifi = database.createObjectStore("wifiObservations", { keyPath: ["sessionId", "scan", "bssid"] });
        wifi.createIndex("sessionId", "sessionId");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transaction(store, mode = "readonly") {
  return db.transaction(store, mode).objectStore(store);
}

function parseFields(hex) {
  const bytes = new Uint8Array(hex.match(/../g)?.map(x => parseInt(x, 16)) || []);
  let name = "", manufacturer = "", services = [];
  for (let i = 0; i + 1 < bytes.length;) {
    const length = bytes[i]; if (!length || i + length >= bytes.length + 1) break;
    const type = bytes[i + 1], data = bytes.slice(i + 2, i + length + 1);
    if (type === 0x09 || (!name && type === 0x08)) name = new TextDecoder().decode(data);
    if (type === 0xff && data.length >= 2) manufacturer = `0x${(data[1] << 8 | data[0]).toString(16).padStart(4, "0").toUpperCase()}`;
    if ((type === 0x02 || type === 0x03) && data.length >= 2) {
      for (let p = 0; p + 1 < data.length; p += 2)services.push(`0x${(data[p + 1] << 8 | data[p]).toString(16).padStart(4, "0").toUpperCase()}`);
    }
    i += length + 1;
  }
  return { name, manufacturer, services };
}

function aggregate(observation) {
  const id = `${observation.addrType}:${observation.mac}`;
  const existing = devices.get(id);
  const fields = parseFields(observation.advHex);
  if (!existing) {
    const created = {
      id, mac: observation.mac, addrType: observation.addrType,
      name: fields.name || "Unnamed", manufacturer: fields.manufacturer,
      services: fields.services, firstSeen: observation.receivedAt,
      lastSeen: observation.receivedAt, strongestRssi: observation.rssi,
      latestRssi: observation.rssi, previousRssi: observation.rssi,
      latestAdvHex: observation.advHex, sightings: 1, flags: observation.flags
    };
    devices.set(id, created);
    return created;
  }
  existing.previousRssi = existing.latestRssi;
  existing.latestRssi = observation.rssi;
  existing.strongestRssi = Math.max(existing.strongestRssi, observation.rssi);
  existing.lastSeen = observation.receivedAt;
  existing.sightings++;
  existing.flags |= observation.flags;
  existing.latestAdvHex = observation.advHex;
  if (fields.name) existing.name = fields.name;
  if (fields.manufacturer) existing.manufacturer = fields.manufacturer;
  if (fields.services.length) existing.services = fields.services;
  return existing;
}

function storeBatch(items) {
  if (!items.length) return;
  const store = transaction("observations", "readwrite");
  for (const item of items) store.put(item);
}

async function poll() {
  if (!polling) return;
  try {
    const response = await fetch(`/api/updates?after=${after}&limit=100`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const packet = await response.json();
    if (packet.reset) {
      await startSession();
      setTimeout(poll, 0);
      return;
    }
    dropped += packet.dropped || 0;
    const receivedAt = Date.now();
    const observations = packet.items.map(row => ({
      sessionId, seq: row[0], deviceMs: row[1], addrType: row[2], mac: row[3],
      rssi: row[4], advType: row[5], flags: row[6], advHex: row[7], receivedAt
    }));
    const changed = new Map();
    for (const observation of observations) {
      const device = aggregate(observation);
      changed.set(device.id, device);
    }
    storeBatch(observations);
    if (packet.to > after) after = packet.to;
    if (observations.length) postMessage({
      type: "dirty", updates: [...changed.values()], after, dropped
    });
    postMessage({ type: "connection", state: "Live" });
    retryMs = 1000;
    setTimeout(poll, pollMs);
  } catch (error) {
    postMessage({ type: "connection", state: "Retrying", error: String(error) });
    setTimeout(poll, retryMs);
    retryMs = Math.min(30000, retryMs * 2);
  }
}

function scheduleWifi(delay) {
  if (wifiTimer) clearTimeout(wifiTimer);
  if (showWifi && wifiMs > 0) wifiTimer = setTimeout(pollWifi, delay);
}

async function pollWifi() {
  if (!showWifi || wifiMs <= 0) return;
  try {
    const packet = await fetch("/api/wifi", { cache: "no-store" }).then(response => {
      if (!response.ok) throw new Error(`Wi-Fi HTTP ${response.status}`);
      return response.json();
    });
    wifiNetworks = packet.items.map(row => ({
      ssid: row[0], bssid: row[1], channel: row[2], rssi: row[3],
      security: row[4], hidden: row[5], scan: packet.scan,
      receivedAt: Date.now()
    }));
    if (packet.scan !== lastWifiScan) {
      lastWifiScan = packet.scan;
      const store = transaction("wifiObservations", "readwrite");
      for (const network of wifiNetworks) store.put({ ...network, sessionId });
    }
    postMessage({ type: "wifi", networks: wifiNetworks, scan: packet.scan, durationMs: packet.duration_ms });
    scheduleWifi(wifiMs);
  } catch (error) {
    postMessage({ type: "wifiError", error: String(error) });
    scheduleWifi(Math.min(30000, Math.max(5000, wifiMs)));
  }
}

async function startSession() {
  sessionId = uuid(); after = 0; dropped = 0; lastWifiScan = 0; devices.clear();
  sessionStartTime = Date.now();
  transaction("sessions", "readwrite").put({ id: sessionId, startTime: sessionStartTime, endTime: null });
  postMessage({ type: "session", sessionId });
}

async function exportEvidence(format) {
  const observations = [];
  const wifiObservations = [];
  await new Promise((resolve, reject) => {
    const index = transaction("observations").index("sessionId");
    const request = index.openCursor(IDBKeyRange.only(sessionId));
    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor) { observations.push(cursor.value); cursor.continue(); } else resolve();
    };
    request.onerror = () => reject(request.error);
  });
  await new Promise((resolve, reject) => {
    const index = transaction("wifiObservations").index("sessionId");
    const request = index.openCursor(IDBKeyRange.only(sessionId));
    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor) { wifiObservations.push(cursor.value); cursor.continue(); } else resolve();
    };
    request.onerror = () => reject(request.error);
  });
  postMessage({
    type: "export", format, sessionId, sessionStartTime,
    sessionEndTime: Date.now(), observations, wifiObservations, dropped
  });
}

onmessage = async event => {
  const message = event.data;
  if (message.type === "settings") {
    const nextWifiMs = message.wifiMs === 0 ? 0 : (message.wifiMs || 60000);
    const nextShowWifi = message.showWifi !== false;
    const wifiChanged = nextWifiMs !== wifiMs || nextShowWifi !== showWifi;
    pollMs = message.pollMs || 500;
    wifiMs = nextWifiMs;
    showWifi = nextShowWifi;
    if (wifiChanged) scheduleWifi(0);
  } else if (message.type === "newSession") {
    await startSession();
  } else if (message.type === "export") {
    try { await exportEvidence(message.format); }
    catch (error) { postMessage({ type: "exportError", error: String(error) }); }
  } else if (message.type === "clear") {
    db.close();
    await new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(DB_NAME);
      request.onsuccess = resolve; request.onerror = () => reject(request.error);
    });
    db = await openDb(); await startSession();
  }
};

(async () => {
  db = await openDb();
  await startSession();
  poll();
  scheduleWifi(0);
})();
