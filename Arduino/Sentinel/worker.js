const DB_NAME = "RyancitoSentinalEvidence";
const DB_VERSION = 5;
let db;
let sessionId;
let after = 0;
let polling = true;
let pollMs = 500;
let dropped = 0;
let retryMs = 1000;
let wifiMs = 60000;
let showWifi = true;
let maxSessions = 0;
let caseMetadata = {};
let lastWifiScan = 0;
let wifiTimer = null;
let wifiBusy = false;
let wifiNetworks = [];
let sessionStartTime = 0;
let collectorBootWall = 0;
let sessionObservationCount = 0;
let sessionWifiCount = 0;
let sessionName = "";
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
        const annotations = database.createObjectStore("annotations", { keyPath: ["sessionId", "deviceId"] });
        annotations.createIndex("sessionId", "sessionId");
      } else {
        const annotations = request.transaction.objectStore("annotations");
        if (!annotations.indexNames.contains("sessionId"))
          annotations.createIndex("sessionId", "sessionId");
      }
      if (!database.objectStoreNames.contains("wifiObservations")) {
        const wifi = database.createObjectStore("wifiObservations", { keyPath: ["sessionId", "scan", "bssid"] });
        wifi.createIndex("sessionId", "sessionId");
      }
      if (database.objectStoreNames.contains("contextRecords"))
        database.deleteObjectStore("contextRecords");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transaction(store, mode = "readonly") {
  return db.transaction(store, mode).objectStore(store);
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function saveSession(endTime = null) {
  if (!db || !sessionId) return;
  transaction("sessions", "readwrite").put({
    id: sessionId, startTime: sessionStartTime, endTime,
    observationCount: sessionObservationCount, wifiObservationCount: sessionWifiCount,
    dropped, active: endTime === null, schemaVersion: 2, case: caseMetadata,
    name: sessionName, lastUpdatedAt: Date.now()
  });
}

async function anchorCollectorClock() {
  try {
    const status = await fetch("/api/status", { cache: "no-store" }).then(response => response.json());
    collectorBootWall = Date.now() - (status.uptime_ms || 0);
  } catch (error) { collectorBootWall = 0; }
}

async function recordsForSession(storeName, id) {
  const records = [];
  await new Promise((resolve, reject) => {
    const request = transaction(storeName).index("sessionId").openCursor(IDBKeyRange.only(id));
    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor) { records.push(cursor.value); cursor.continue(); } else resolve();
    };
    request.onerror = () => reject(request.error);
  });
  return records;
}

function parseFields(hex) {
  const bytes = new Uint8Array(hex.match(/../g)?.map(x => parseInt(x, 16)) || []);
  let name = "", manufacturer = "", services = [], txPower = null, appearance = null, serviceData = [];
  for (let i = 0; i + 1 < bytes.length;) {
    const length = bytes[i]; if (!length || i + length >= bytes.length + 1) break;
    const type = bytes[i + 1], data = bytes.slice(i + 2, i + length + 1);
    if (type === 0x09 || (!name && type === 0x08)) name = new TextDecoder().decode(data);
    if (type === 0xff && data.length >= 2) manufacturer = `0x${(data[1] << 8 | data[0]).toString(16).padStart(4, "0").toUpperCase()}`;
    if ((type === 0x02 || type === 0x03) && data.length >= 2) {
      for (let p = 0; p + 1 < data.length; p += 2)services.push(`0x${(data[p + 1] << 8 | data[p]).toString(16).padStart(4, "0").toUpperCase()}`);
    }
    if ((type === 0x04 || type === 0x05) && data.length >= 4) {
      for (let p = 0; p + 3 < data.length; p += 4)
        services.push(`0x${[data[p + 3], data[p + 2], data[p + 1], data[p]].map(value => value.toString(16).padStart(2, "0")).join("").toUpperCase()}`);
    }
    if ((type === 0x06 || type === 0x07) && data.length >= 16) {
      for (let p = 0; p + 15 < data.length; p += 16)
        services.push([...data.slice(p, p + 16)].reverse().map(value => value.toString(16).padStart(2, "0")).join("").toUpperCase());
    }
    if (type === 0x0a && data.length) txPower = (data[0] << 24 >> 24);
    if (type === 0x19 && data.length >= 2) appearance = data[1] << 8 | data[0];
    if (type === 0x16 && data.length >= 2) serviceData.push(
      `0x${(data[1] << 8 | data[0]).toString(16).padStart(4, "0").toUpperCase()}`);
    i += length + 1;
  }
  return { name, manufacturer, services, txPower, appearance, serviceData };
}

function aggregate(observation) {
  const id = `${observation.addrType}:${observation.mac}`;
  const existing = devices.get(id);
  const fields = parseFields(observation.advHex);
  const observationTime = observation.estimatedObservedAt || observation.receivedAt;
  if (!existing) {
    const created = {
      id, mac: observation.mac, addrType: observation.addrType,
      name: fields.name || "Unnamed", manufacturer: fields.manufacturer,
      services: fields.services, firstSeen: observationTime,
      lastSeen: observationTime, strongestRssi: observation.rssi,
      latestRssi: observation.rssi, previousRssi: observation.rssi,
      latestAdvHex: observation.advHex, sightings: 1, flags: observation.flags
    };
    created.txPower = fields.txPower; created.appearance = fields.appearance;
    created.serviceData = fields.serviceData;
    devices.set(id, created);
    return created;
  }
  existing.previousRssi = existing.latestRssi;
  existing.latestRssi = observation.rssi;
  existing.strongestRssi = Math.max(existing.strongestRssi, observation.rssi);
  existing.lastSeen = observationTime;
  existing.sightings++;
  existing.flags |= observation.flags;
  existing.latestAdvHex = observation.advHex;
  if (fields.name) existing.name = fields.name;
  if (fields.manufacturer) existing.manufacturer = fields.manufacturer;
  if (fields.services.length) existing.services = fields.services;
  if (fields.txPower !== null) existing.txPower = fields.txPower;
  if (fields.appearance !== null) existing.appearance = fields.appearance;
  if (fields.serviceData.length) existing.serviceData = fields.serviceData;
  return existing;
}

function storeBatch(items) {
  if (!items.length) return;
  const store = transaction("observations", "readwrite");
  for (const item of items) store.put(item);
}

async function poll() {
  if (!polling) return;
  const pollStarted = performance.now();
  try {
    const response = await fetch(`/api/updates?after=${after}&limit=100`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const packet = await response.json();
    if (packet.reset) {
      await anchorCollectorClock();
      await startSession("collector-reset");
      setTimeout(poll, 0);
      return;
    }
    dropped += packet.dropped || 0;
    const receivedAt = Date.now();
    const observations = packet.items.map(row => ({
      sessionId, seq: row[0], deviceMs: row[1], addrType: row[2], mac: row[3],
      rssi: row[4], advType: row[5], flags: row[6], advHex: row[7], receivedAt,
      estimatedObservedAt: collectorBootWall ? collectorBootWall + row[1] : null,
      timestampSource: collectorBootWall ? "esp32-monotonic-anchored-to-browser" : "browser-receipt",
      timingUncertaintyMs: collectorBootWall ?
        Math.max(0, receivedAt - (collectorBootWall + row[1])) : null
    }));
    const changed = new Map();
    for (const observation of observations) {
      const device = aggregate(observation);
      changed.set(device.id, device);
    }
    storeBatch(observations);
    sessionObservationCount += observations.length;
    if (observations.length || packet.dropped) saveSession();
    if (packet.to > after) after = packet.to;
    if (observations.length) postMessage({
      type: "dirty", updates: [...changed.values()], after, dropped
    });
    postMessage({
      type: "connection", state: "Live", lastPollAt: Date.now(),
      latencyMs: Math.round(performance.now() - pollStarted)
    });
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

async function pollWifi(manual = false) {
  if (!manual && (!showWifi || wifiMs <= 0)) return;
  if (wifiBusy) {
    if (manual) postMessage({ type: "wifiError", error: "A Wi-Fi scan is already running", manual: true });
    return;
  }
  wifiBusy = true;
  try {
    const packet = await fetch(manual ? "/api/wifi?force=1" : "/api/wifi", { cache: "no-store" }).then(response => {
      if (!response.ok) throw new Error(`Wi-Fi HTTP ${response.status}`);
      return response.json();
    });
    if (manual && packet.performed === false)
      throw new Error(`Please wait ${Math.ceil((packet.forced_cooldown_ms || 5000) / 1000)} seconds between manual scans`);
    wifiNetworks = packet.items.map(row => ({
      ssid: row[0], bssid: row[1], channel: row[2], rssi: row[3],
      security: row[4], hidden: row[5], scan: packet.scan,
      receivedAt: Date.now()
    }));
    if (packet.scan !== lastWifiScan) {
      lastWifiScan = packet.scan;
      const store = transaction("wifiObservations", "readwrite");
      for (const network of wifiNetworks) store.put({ ...network, sessionId });
      sessionWifiCount += wifiNetworks.length;
      saveSession();
    }
    postMessage({ type: "wifi", networks: wifiNetworks, scan: packet.scan, durationMs: packet.duration_ms, manual });
    scheduleWifi(wifiMs);
  } catch (error) {
    postMessage({ type: "wifiError", error: String(error), manual });
    scheduleWifi(Math.min(30000, Math.max(5000, wifiMs)));
  } finally {
    wifiBusy = false;
  }
}

async function startSession(reason = "new") {
  if (sessionId) saveSession(Date.now());
  sessionId = uuid(); after = 0; dropped = 0; lastWifiScan = 0; devices.clear();
  sessionObservationCount = 0; sessionWifiCount = 0;
  sessionName = "";
  sessionStartTime = Date.now();
  saveSession();
  postMessage({ type: "session", sessionId, reason });
  if (maxSessions > 0) await enforceRetention();
}

async function clearEvidence() {
  if (sessionId) saveSession(Date.now());
  polling = false;
  if (wifiTimer) { clearTimeout(wifiTimer); wifiTimer = null; }
  db.close();
  await new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DB_NAME);
    request.onsuccess = resolve;
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Database deletion was blocked by another open RyancitoSentinal tab"));
  });
  db = null;
  sessionId = null;
  devices.clear();
  postMessage({ type: "evidenceCleared" });
}

async function exportEvidence(format, targetSession = sessionId) {
  const observations = await recordsForSession("observations", targetSession);
  const wifiObservations = await recordsForSession("wifiObservations", targetSession);
  const annotations = await recordsForSession("annotations", targetSession);
  const session = await requestResult(transaction("sessions").get(targetSession));
  postMessage({
    type: "export", format, sessionId: targetSession,
    sessionStartTime: session?.startTime || sessionStartTime,
    sessionEndTime: session?.endTime || Date.now(), observations, wifiObservations,
    annotations, dropped: session?.dropped ?? dropped, session
  });
}

async function listSessions() {
  const sessions = await requestResult(transaction("sessions").getAll());
  sessions.sort((a, b) => b.startTime - a.startTime);
  postMessage({ type: "sessions", sessions, currentSessionId: sessionId });
}

async function closeOrphanedSessions() {
  const sessions = await requestResult(transaction("sessions").getAll());
  const store = transaction("sessions", "readwrite");
  for (const session of sessions) if (session.active) {
    session.active = false;
    session.endTime = session.lastUpdatedAt || session.startTime;
    store.put(session);
  }
}

async function deleteSession(id) {
  if (id === sessionId) throw new Error("The active session cannot be deleted");
  for (const storeName of ["observations", "wifiObservations", "annotations"]) {
    const store = transaction(storeName, "readwrite");
    const request = store.index("sessionId").openCursor(IDBKeyRange.only(id));
    await new Promise((resolve, reject) => {
      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor) { cursor.delete(); cursor.continue(); } else resolve();
      };
      request.onerror = () => reject(request.error);
    });
  }
  await requestResult(transaction("sessions", "readwrite").delete(id));
  await listSessions();
}

async function enforceRetention() {
  const sessions = await requestResult(transaction("sessions").getAll());
  sessions.sort((a, b) => b.startTime - a.startTime);
  for (const session of sessions.slice(maxSessions)) {
    if (session.id !== sessionId) await deleteSession(session.id);
  }
}

async function renameSession(id, name) {
  const session = await requestResult(transaction("sessions").get(id));
  if (!session) throw new Error("Session not found");
  session.name = String(name || "").slice(0, 80);
  if (id === sessionId) sessionName = session.name;
  await requestResult(transaction("sessions", "readwrite").put(session));
  await listSessions();
}

async function saveAnnotation(annotation) {
  const saved = {
    ...annotation, sessionId, updatedAt: Date.now()
  };
  await requestResult(transaction("annotations", "readwrite").put(saved));
  postMessage({ type: "annotation", annotation: saved });
}

async function getAnnotation(deviceId) {
  const annotation = await requestResult(
    transaction("annotations").get([sessionId, deviceId]));
  postMessage({ type: "annotation", annotation: annotation || { sessionId, deviceId } });
}

async function sessionAnalysis(ids) {
  const results = [];
  for (const id of ids) {
    const ble = await recordsForSession("observations", id);
    const wifi = await recordsForSession("wifiObservations", id);
    const identifiers = new Set([
      ...ble.map(record => `BLE ${record.mac}`),
      ...wifi.map(record => `Wi-Fi ${record.bssid}`)
    ]);
    const timeline = [
      ...ble.map(record => ({
        at: record.estimatedObservedAt || record.receivedAt,
        label: `BLE ${record.mac} ${record.rssi} dBm`
      })),
      ...wifi.map(record => ({
        at: record.receivedAt,
        label: `Wi-Fi ${record.bssid} ${record.rssi} dBm`
      }))
    ].sort((a, b) => a.at - b.at).slice(0, 100);
    results.push({
      id, bleCount: ble.length, wifiCount: wifi.length,
      identifiers: [...identifiers], timeline
    });
  }
  postMessage({ type: "sessionAnalysis", results });
}

async function getHistory(radio, identifier) {
  const storeName = radio === "BLE" ? "observations" : "wifiObservations";
  const records = [];
  await new Promise((resolve, reject) => {
    const index = transaction(storeName).index("sessionId");
    const request = index.openCursor(IDBKeyRange.only(sessionId));
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) { resolve(); return; }
      const value = cursor.value;
      const matches = radio === "BLE" ?
        value.mac === identifier : value.bssid === identifier;
      if (matches) {
        records.push(value);
        if (records.length > 100) records.shift();
      }
      cursor.continue();
    };
    request.onerror = () => reject(request.error);
  });
  postMessage({ type: "detailHistory", radio, identifier, records });
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
    maxSessions = Math.max(0, Number(message.maxSessions) || 0);
    caseMetadata = message.caseMetadata || caseMetadata;
    saveSession();
    if (wifiChanged) scheduleWifi(0);
  } else if (message.type === "newSession") {
    await startSession("new");
  } else if (message.type === "forceWifi") {
    await pollWifi(true);
  } else if (message.type === "export") {
    try { await exportEvidence(message.format, message.sessionId || sessionId); }
    catch (error) { postMessage({ type: "exportError", error: String(error) }); }
  } else if (message.type === "clear") {
    try { await clearEvidence(); }
    catch (error) { postMessage({ type: "clearError", error: String(error) }); }
  } else if (message.type === "history") {
    try { await getHistory(message.radio, message.identifier); }
    catch (error) {
      postMessage({
        type: "detailHistory", radio: message.radio,
        identifier: message.identifier, records: [], error: String(error)
      });
    }
  } else if (message.type === "listSessions") {
    await listSessions();
  } else if (message.type === "deleteSession") {
    try { await deleteSession(message.sessionId); }
    catch (error) { postMessage({ type: "sessionError", error: String(error) }); }
  } else if (message.type === "renameSession") {
    try { await renameSession(message.sessionId, message.name); }
    catch (error) { postMessage({ type: "sessionError", error: String(error) }); }
  } else if (message.type === "annotationGet") {
    await getAnnotation(message.deviceId);
  } else if (message.type === "annotationSave") {
    await saveAnnotation(message.annotation);
  } else if (message.type === "sessionAnalysis") {
    await sessionAnalysis(message.sessionIds || []);
  }
};

(async () => {
  db = await openDb();
  await closeOrphanedSessions();
  await anchorCollectorClock();
  await startSession("startup");
  poll();
  scheduleWifi(0);
})();
