const $=selector=>document.querySelector(selector);
const settings=Object.assign({
  theme:"dark",minRssi:-100,pollMs:500,wifiMs:60000,
  maxSessions:0,
  showHidden:false,showWifi:true,showBle:true,compact:false,
  hidden:[],hiddenBands:[],collapsed:[],bleSort:"latestRssi",bleSortDir:-1,
  wifiSort:"rssi",wifiSortDir:-1,printOrientation:"landscape",
  caseId:"",investigator:"",locationLabel:"",caseNote:""
},JSON.parse(localStorage.getItem("sentinal-ui")||"{}"));
const hidden=new Set(settings.hidden||[]);
const hiddenBands=new Set(settings.hiddenBands||[]);
const worker=new Worker("/worker.js?v=4.4");
const rows=new Map();
const deviceStore=new Map();
let devices=[];
let observationCount=0;
let dropped=0;
let dirty=false;
let sessionId="";
let wifiNetworks=[];
let wifiScanNumber=0;
let wifiDirty=false;
let paused=false;
let connectionStatus="Starting";
const MAX_RENDER_ROWS=300;
let detailSelection=null;
const wifiRows=new Map();
const annotations=new Map();
let savedSessions=[];

function saveSettings(){
  settings.hidden=[...hidden];
  settings.hiddenBands=[...hiddenBands];
  localStorage.setItem("sentinal-ui",JSON.stringify(settings));
  worker.postMessage({
    type:"settings",pollMs:Number(settings.pollMs),
    wifiMs:Number(settings.wifiMs),showWifi:settings.showWifi,
    maxSessions:Number(settings.maxSessions),
    caseMetadata:caseContext()
  });
  dirty=true;
}

function trend(device){
  const delta=device.latestRssi-device.previousRssi;
  if(device.sightings===1)return["NEW","new"];
  if(delta>=4)return[`↑ +${delta} dB`,"up"];
  if(delta<=-4)return[`↓ ${delta} dB`,"down"];
  return[`→ ${delta>=0?"+":""}${delta} dB`,"steady"];
}
function wifiTrend(network){
  if(network.previousRssi===undefined)return["NEW","new",null];
  const delta=network.rssi-network.previousRssi;
  if(delta>=4)return[`↑ +${delta} dB stronger`,"up",delta];
  if(delta<=-4)return[`↓ ${delta} dB weaker`,"down",delta];
  return[`→ ${delta>=0?"+":""}${delta} dB stable`,"steady",delta];
}
function proximity(device){
  if(Date.now()-device.lastSeen>5000)return["Stale","off"];
  const rssi=device.latestRssi;
  if(rssi>=-50)return["Immediate","blue"];
  if(rssi>=-70)return["Strong","green"];
  if(rssi>=-78)return["Medium","yellow"];
  if(rssi>=-85)return["Weak","red"];
  return["Very weak","off"];
}
function signalWidth(rssi){
  return Math.max(0,Math.min(100,Math.round((rssi+100)*1.8)));
}
function addressType(value){
  return({0:"Public",1:"Random",2:"Public ID",3:"Random ID"})[value]||`Type ${value}`;
}
function escapeHtml(value){
  return String(value??"").replace(/[&<>"']/g,char=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  })[char]);
}
function formatDate(value){
  return value?new Date(value).toLocaleString():"Unavailable";
}
function classifyClient(){
  const ua=navigator.userAgent||"";
  if(/iPhone/i.test(ua))return"iPhone";
  if(/iPad/i.test(ua)||(/Macintosh/i.test(ua)&&navigator.maxTouchPoints>1))return"iPad";
  if(/Android/i.test(ua))return"Android";
  if(/Mac/i.test(ua))return"Mac";
  if(/Windows/i.test(ua))return"Windows PC";
  if(/Linux/i.test(ua))return"Linux computer";
  return"Browser client";
}
function updateConnectionClient(){
  $("#connectionClient").textContent=`${classifyClient()} · ${connectionStatus}`;
}
function caseContext(){
  return{
    caseId:settings.caseId||null,investigator:settings.investigator||null,
    locationLabel:settings.locationLabel||null,note:settings.caseNote||null
  };
}
function spacedHex(hex){
  return (hex||"").match(/.{1,2}/g)?.join(" ").toUpperCase()||"Unavailable";
}
function decodeAdvertisement(hex){
  const bytes=new Uint8Array((hex||"").match(/../g)?.map(x=>parseInt(x,16))||[]);
  const types={
    0x01:"Flags",0x02:"More 16-bit Service UUIDs",0x03:"Complete 16-bit Service UUIDs",
    0x06:"More 128-bit Service UUIDs",0x07:"Complete 128-bit Service UUIDs",
    0x08:"Shortened Local Name",0x09:"Complete Local Name",0x0a:"TX Power",
    0x16:"Service Data",0x19:"Appearance",0xff:"Manufacturer Data"
  };
  const fields=[];
  for(let index=0;index+1<bytes.length;){
    const length=bytes[index];
    if(!length||index+length>=bytes.length+1)break;
    const type=bytes[index+1];
    const data=bytes.slice(index+2,index+length+1);
    fields.push({
      type:`0x${type.toString(16).padStart(2,"0").toUpperCase()}`,
      name:types[type]||"Unknown AD type",
      length:data.length,
      data:[...data].map(x=>x.toString(16).padStart(2,"0")).join(" ").toUpperCase()
    });
    index+=length+1;
  }
  return fields;
}
function visibleDevices(){
  const query=$("#search").value.trim().toLowerCase();
  const result=devices.filter(device=>{
    if(device.latestRssi<Number(settings.minRssi))return false;
    if(hidden.has(device.id)&&!settings.showHidden)return false;
    if(hiddenBands.has(proximity(device)[1]))return false;
    if(!query)return true;
    return `${device.name} ${device.mac} ${device.manufacturer} ${device.services.join(" ")}`.toLowerCase().includes(query);
  });
  const key=settings.bleSort;
  result.sort((a,b)=>{
    const left=a[key]??"",right=b[key]??"";
    const comparison=typeof left==="string"?
      left.localeCompare(right):left-right;
    return comparison*settings.bleSortDir;
  });
  return result;
}

function updateRow(device){
  let row=rows.get(device.id);
  if(!row){
    row=document.createElement("tr");
    row.innerHTML="<td></td><td class='rssi'></td><td><span class='signal-track'><i></i></span></td><td></td><td></td><td></td><td></td><td></td><td></td><td class='filter-cell'><label><input type='checkbox'> Ignore</label></td>";
    row.querySelector("input").addEventListener("change",event=>{
      if(event.target.checked)hidden.add(device.id);else hidden.delete(device.id);
      saveSettings();
    });
    row.addEventListener("click",event=>{
      if(event.target.closest(".filter-cell"))return;
      const current=deviceStore.get(device.id);
      if(current)openBleDetail(current);
    });
    rows.set(device.id,row);
  }
  const cells=row.children;
  const movement=trend(device);
  const distance=proximity(device);
  const annotation=annotations.get(`BLE:${device.mac}`);
  const marker=annotation?.watchlist?"★ ":
    annotation?.classification==="trusted"?"✓ ":
    annotation?.classification==="investigate"?"! ":"";
  const details=[device.manufacturer,...device.services].filter(Boolean).join(" | ")||"No decoded data";
  const values=[
    `${marker}${annotation?.friendlyName||device.name}`,`${device.latestRssi}`,null,movement[0],distance[0],
    device.sightings,addressType(device.addrType),device.mac,details,null
  ];
  for(let i=0;i<values.length;i++){
    if(values[i]===null)continue;
    const value=String(values[i]);
    if(cells[i].textContent!==value)cells[i].textContent=value;
  }
  cells[3].className=movement[1];
  const proximityHtml=`<span class="dot ${distance[1]}"></span>${distance[0]}`;
  if(cells[4].innerHTML!==proximityHtml)cells[4].innerHTML=proximityHtml;
  cells[2].querySelector("i").style.width=`${signalWidth(device.latestRssi)}%`;
  cells[9].querySelector("input").checked=hidden.has(device.id);
  return row;
}

function renderWifi(){
  if(!wifiDirty)return;
  wifiDirty=false;
  const body=$("#wifiRows");
  const fragment=document.createDocumentFragment();
  const keep=new Set();
  const visibleWifi=wifiNetworks.filter(
    network=>network.rssi>=Number(settings.minRssi));
  visibleWifi.sort((a,b)=>{
    const left=a[settings.wifiSort]??"",right=b[settings.wifiSort]??"";
    const comparison=typeof left==="string"?
      left.localeCompare(right):left-right;
    return comparison*settings.wifiSortDir;
  });
  for(const network of visibleWifi){
    let row=wifiRows.get(network.bssid);
    if(!row){
      row=document.createElement("tr");
      row.innerHTML="<td></td><td class='rssi'></td><td><span class='signal-track'><i></i></span></td><td></td><td></td><td></td><td></td>";
      row.addEventListener("click",()=>{
        const current=wifiNetworks.find(item=>item.bssid===network.bssid);
        if(current)openWifiDetail(current);
      });
      wifiRows.set(network.bssid,row);
    }
    const movement=wifiTrend(network);
    const annotation=annotations.get(`Wi-Fi:${network.bssid}`);
    const marker=annotation?.watchlist?"★ ":
      annotation?.classification==="trusted"?"✓ ":
      annotation?.classification==="investigate"?"! ":"";
    const cells=row.children;
    const values=[`${marker}${annotation?.friendlyName||(network.hidden?"Hidden":network.ssid)}`,network.rssi,null,movement[0],network.channel,network.security,network.bssid];
    for(let i=0;i<values.length;i++){
      if(values[i]===null)continue;
      if(cells[i].textContent!==String(values[i]))cells[i].textContent=values[i];
    }
    cells[2].querySelector("i").style.width=`${signalWidth(network.rssi)}%`;
    cells[3].className=movement[1];
    keep.add(network.bssid);fragment.appendChild(row);
  }
  for(const [id,row] of wifiRows)if(!keep.has(id)){
    if(row.parentNode)row.remove();
    wifiRows.delete(id);
  }
  body.appendChild(fragment);
  $("#wifiCount").textContent=visibleWifi.length;
  $("#wifiEmpty").hidden=visibleWifi.length>0;
}

function render(){
  if(paused)return;
  if(!dirty)return;
  dirty=false;
  const visible=visibleDevices();
  const rendered=visible.slice(0,MAX_RENDER_ROWS);
  const fragment=document.createDocumentFragment();
  const keep=new Set();
  for(const device of rendered){
    const row=updateRow(device);keep.add(device.id);fragment.appendChild(row);
  }
  for(const [id,row] of rows)if(!keep.has(id)){
    if(row.parentNode)row.remove();
    rows.delete(id);
  }
  $("#deviceRows").appendChild(fragment);
  $("#emptyState").hidden=visible.length>0;
  $("#visibleCount").textContent=visible.length>MAX_RENDER_ROWS?
    `${MAX_RENDER_ROWS} of ${visible.length}`:visible.length;
  $("#deviceCount").textContent=devices.length;
  $("#observationCount").textContent=observationCount;
  $("#droppedCount").textContent=dropped;
  renderWifi();
  renderInsights();
}

function renderInsights(){
  const insights=[];
  const add=(title,detail,radio,identifier)=>insights.push({title,detail,radio,identifier});
  const now=Date.now();
  for(const device of devices){
    const annotation=annotations.get(`BLE:${device.mac}`);
    if(annotation?.watchlist)add("Watchlist observation",`${annotation.friendlyName||device.name} · ${device.mac} · ${device.latestRssi} dBm`,"BLE",device.mac);
    if(annotation?.classification==="trusted"&&!annotation.watchlist)continue;
    if(now-device.firstSeen<30000)add("New BLE identifier",`${device.name} · ${device.mac} first appeared recently`,"BLE",device.mac);
    if(device.latestRssi>=-55)add("Strong BLE signal",`${device.name} · ${device.mac} at ${device.latestRssi} dBm`,"BLE",device.mac);
    if(device.flags&2)add("Advertisement changed",`${device.name} · ${device.mac} emitted changed advertisement data`,"BLE",device.mac);
  }
  const ssids=new Map();
  for(const network of wifiNetworks){
    const annotation=annotations.get(`Wi-Fi:${network.bssid}`);
    if(annotation?.watchlist)add("Watchlist observation",`${annotation.friendlyName||network.ssid} · ${network.bssid} · ${network.rssi} dBm`,"WiFi",network.bssid);
    if(annotation?.classification==="trusted"&&!annotation.watchlist)continue;
    if(network.security==="Open")add("Open WiFi advertised",`${network.ssid} · ${network.bssid}`,"WiFi",network.bssid);
    if(network.previousSecurity&&network.previousSecurity!==network.security)
      add("WiFi security changed",`${network.bssid}: ${network.previousSecurity} → ${network.security}`,"WiFi",network.bssid);
    if(network.previousChannel!==undefined&&network.previousChannel!==network.channel)
      add("WiFi channel changed",`${network.bssid}: channel ${network.previousChannel} → ${network.channel}`,"WiFi",network.bssid);
    if(!network.hidden){
      const list=ssids.get(network.ssid)||[];list.push(network);ssids.set(network.ssid,list);
    }
  }
  for(const [ssid,list] of ssids)if(list.length>1){
    const security=new Set(list.map(network=>network.security));
    add("Duplicate SSID",`${ssid} is advertised by ${list.length} BSSIDs${security.size>1?" with different security modes":""}`,"WiFi",list[0].bssid);
  }
  const unique=[];
  const seen=new Set();
  for(const insight of insights){
    const key=`${insight.title}|${insight.detail}`;
    if(!seen.has(key)){seen.add(key);unique.push(insight);}
  }
  const shown=unique.slice(0,12);
  $("#insightCount").textContent=unique.length;
  $("#insightList").innerHTML=shown.length?shown.map((insight,index)=>
    `<button class="insight" data-insight="${index}" title="Open related device details"><strong>${escapeHtml(insight.title)}</strong><span>${escapeHtml(insight.detail)}</span></button>`
  ).join(""):'<p class="evidence-note">No explainable changes currently meet the insight rules.</p>';
  $("#insightList").querySelectorAll("[data-insight]").forEach(button=>button.onclick=()=>{
    const insight=shown[Number(button.dataset.insight)];
    if(insight.radio==="BLE"){
      const device=devices.find(item=>item.mac===insight.identifier);
      if(device)openBleDetail(device);
    }else{
      const network=wifiNetworks.find(item=>item.bssid===insight.identifier);
      if(network)openWifiDetail(network);
    }
  });
}
setInterval(render,300);
setInterval(()=>{if(!paused)dirty=true;},1000);

function resetLiveView(message){
  sessionId=message.sessionId;
  deviceStore.clear();devices=[];rows.clear();annotations.clear();
  wifiNetworks=[];wifiScanNumber=0;wifiRows.clear();
  observationCount=0;dropped=0;wifiDirty=true;dirty=true;
  $("#deviceRows").textContent="";
  $("#wifiRows").textContent="";
  $("#deviceCount").textContent="0";
  $("#visibleCount").textContent="0";
  $("#observationCount").textContent="0";
  $("#droppedCount").textContent="0";
  $("#wifiCount").textContent="0";
  $("#insightCount").textContent="0";
  $("#emptyState").hidden=false;
  $("#wifiEmpty").hidden=false;
  $("#insightList").innerHTML='<p class="evidence-note">No explainable changes currently meet the insight rules.</p>';
  if(document.body.classList.contains("detail-open"))closeDetail();
  savedSessions=[];
  if(message.reason==="new")
    $("#exportStatus").textContent=`New session started · ${message.sessionId}`;
  else if(message.reason==="cleared"){
    $("#exportStatus").textContent="All browser evidence cleared; a fresh session is active.";
    $("#sessionList").innerHTML='<p class="evidence-note">Previous sessions were deleted.</p>';
    $("#sessionAnalysis").textContent="";
  }else if(message.reason==="collector-reset")
    $("#exportStatus").textContent="Collector restarted; a fresh browser session was created.";
  refreshStorage();
}

worker.onmessage=event=>{
  const message=event.data;
  if(message.type==="dirty"){
    for(const device of message.updates)deviceStore.set(device.id,device);
    devices=[...deviceStore.values()];
    observationCount=message.after;
    dropped=message.dropped;
    dirty=true;
  }else if(message.type==="connection"){
    document.body.dataset.connection=message.state;
    if(!paused){
      connectionStatus=message.latencyMs==null?message.state:
        `${message.state} · ${message.latencyMs} ms`;
      updateConnectionClient();
    }
  }else if(message.type==="session"){
    resetLiveView(message);
  }else if(message.type==="wifi"){
    if(message.scan!==wifiScanNumber){
      const previous=new Map(wifiNetworks.map(network=>[network.bssid,network.rssi]));
      const previousNetworks=new Map(wifiNetworks.map(network=>[network.bssid,network]));
      for(const network of message.networks){
        const prior=previous.get(network.bssid);
        if(prior!==undefined)network.previousRssi=prior;
        const priorNetwork=previousNetworks.get(network.bssid);
        if(priorNetwork){
          network.previousSecurity=priorNetwork.security;
          network.previousChannel=priorNetwork.channel;
        }
      }
      wifiNetworks=message.networks;
      wifiScanNumber=message.scan;
      wifiDirty=true;dirty=true;
    }
    if(message.manual){
      const button=$("#scanWifiNow");
      button.disabled=false;button.textContent=`Scanned ${message.networks.length} networks`;
      setTimeout(()=>button.textContent="Scan WiFi now",1800);
    }
  }else if(message.type==="wifiError"){
    if(message.manual){
      const button=$("#scanWifiNow");
      button.disabled=false;button.textContent="Scan failed";
      setTimeout(()=>button.textContent="Scan WiFi now",1800);
    }
  }else if(message.type==="export"){
    prepareExport(message);
  }else if(message.type==="exportError"){
    $("#exportStatus").textContent=`Export failed: ${message.error}`;
  }else if(message.type==="detailHistory"){
    if(detailSelection&&detailSelection.radio===message.radio&&
       detailSelection.identifier===message.identifier){
      renderDetailHistory(message.records,message.radio,message.error);
    }
  }else if(message.type==="annotation"){
    if(message.annotation?.deviceId){
      annotations.set(message.annotation.deviceId,message.annotation);
      if(detailSelection?.deviceId===message.annotation.deviceId)
        showAnnotation(message.annotation);
      wifiDirty=true;dirty=true;
    }
  }else if(message.type==="sessions"){
    savedSessions=message.sessions||[];
    renderSessionList(message.currentSessionId);
  }else if(message.type==="sessionAnalysis"){
    renderSessionComparison(message.results||[]);
  }else if(message.type==="sessionError"){
    $("#sessionAnalysis").textContent=message.error;
  }else if(message.type==="clearError"){
    $("#exportStatus").textContent=`Clear failed: ${message.error}`;
  }else if(message.type==="evidenceCleared"){
    $("#exportStatus").textContent="Browser evidence cleared. Reloading dashboard…";
    setTimeout(()=>location.reload(),250);
  }
};

function fieldRows(fields){
  return Object.entries(fields).map(([label,value])=>
    `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("");
}

function openBleDetail(device){
  detailSelection={radio:"BLE",identifier:device.mac,deviceId:`BLE:${device.mac}`};
  const movement=trend(device),distance=proximity(device);
  $("#detailType").textContent="BLE OBSERVATION";
  $("#detailTitle").textContent=device.name||"Unnamed";
  $("#detailSummary").innerHTML=`
    <article><strong>${device.latestRssi} dBm</strong><span>Latest RSSI</span></article>
    <article><strong>${device.strongestRssi} dBm</strong><span>Strongest RSSI</span></article>
    <article><strong>${device.sightings}</strong><span>Recorded observations</span></article>`;
  $("#detailFields").innerHTML=fieldRows({
    "Address":device.mac,
    "Address type":addressType(device.addrType),
    "Signal trend":movement[0],
    "Signal band":distance[0],
    "First seen":formatDate(device.firstSeen),
    "Last seen":formatDate(device.lastSeen),
    "Manufacturer ID":device.manufacturer||"Not advertised",
    "Service UUIDs":device.services.length?device.services.join(", "):"None advertised",
    "Service data UUIDs":device.serviceData?.length?device.serviceData.join(", "):"None advertised",
    "TX power":device.txPower==null?"Not advertised":`${device.txPower} dBm`,
    "Appearance":device.appearance==null?"Not advertised":`0x${device.appearance.toString(16).padStart(4,"0").toUpperCase()}`,
    "Evidence flags":device.flags
  });
  $("#detailRaw").textContent=spacedHex(device.latestAdvHex);
  const decoded=decodeAdvertisement(device.latestAdvHex);
  $("#decodedFields").innerHTML=decoded.length?decoded.map(field=>
    `<article><strong>${escapeHtml(field.name)}</strong> (${field.type}, ${field.length} bytes)<br><span>${escapeHtml(field.data||"No data")}</span></article>`
  ).join(""):"<article>No decodable advertisement fields.</article>";
  $("#detailHistory").textContent="Loading browser evidence…";
  $("#detailChart").textContent="";
  document.body.classList.add("detail-open");
  worker.postMessage({type:"history",radio:"BLE",identifier:device.mac});
  worker.postMessage({type:"annotationGet",deviceId:detailSelection.deviceId});
}

function openWifiDetail(network){
  detailSelection={radio:"Wi-Fi",identifier:network.bssid,deviceId:`Wi-Fi:${network.bssid}`};
  const movement=wifiTrend(network);
  $("#detailType").textContent="WIFI OBSERVATION";
  $("#detailTitle").textContent=network.hidden?"Hidden network":network.ssid;
  $("#detailSummary").innerHTML=`
    <article><strong>${network.rssi} dBm</strong><span>Signal</span></article>
    <article><strong>${network.channel}</strong><span>Channel</span></article>
    <article><strong>${escapeHtml(network.security)}</strong><span>Security</span></article>`;
  $("#detailFields").innerHTML=fieldRows({
    "SSID":network.hidden?"Hidden":network.ssid,
    "BSSID":network.bssid,
    "RSSI":`${network.rssi} dBm`,
    "Previous survey RSSI":network.previousRssi===undefined?
      "First observation":`${network.previousRssi} dBm`,
    "Survey trend":movement[0],
    "Channel":network.channel,
    "Security":network.security,
    "Hidden":network.hidden?"Yes":"No",
    "Survey number":network.scan,
    "Browser received":formatDate(network.receivedAt)
  });
  $("#detailRaw").textContent="WiFi scan results do not include frame payloads.";
  $("#decodedFields").innerHTML="<article>The standard MicroPython WLAN scan exposes SSID, BSSID, channel, RSSI, security, and hidden status—not raw 802.11 frames.</article>";
  $("#detailHistory").textContent="Loading browser evidence…";
  $("#detailChart").textContent="";
  document.body.classList.add("detail-open");
  worker.postMessage({type:"history",radio:"Wi-Fi",identifier:network.bssid});
  worker.postMessage({type:"annotationGet",deviceId:detailSelection.deviceId});
}

function showAnnotation(annotation={}){
  $("#annotationName").value=annotation.friendlyName||"";
  $("#annotationClass").value=annotation.classification||"unknown";
  $("#annotationWatch").checked=!!annotation.watchlist;
  $("#annotationTags").value=(annotation.tags||[]).join(", ");
  $("#annotationNote").value=annotation.note||"";
}

function renderDetailHistory(records,radio,error){
  if(error){
    $("#detailHistory").textContent=`History unavailable: ${error}`;
    return;
  }
  if(!records.length){
    $("#detailHistory").textContent="No stored history for this observation.";
    $("#detailChart").textContent="";
    return;
  }
  const chartRecords=records.slice(-50);
  const points=chartRecords.map((record,index)=>{
    const x=chartRecords.length===1?50:index*100/(chartRecords.length-1);
    const y=Math.max(0,Math.min(100,(-20-record.rssi)*1.25));
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  $("#detailChart").innerHTML=`
    <span class="chart-label chart-stronger">stronger</span>
    <span class="chart-label chart-weaker">weaker</span>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="RSSI history">
      <polyline points="${points}"></polyline>
    </svg>`;
  $("#detailHistory").innerHTML=records.slice(-20).reverse().map(record=>{
    const when=formatDate(record.estimatedObservedAt||record.receivedAt);
    const detail=radio==="BLE"?
      `${record.rssi} dBm · seq ${record.seq} · flags ${record.flags} · ${record.timestampSource||"browser receipt"}${record.timingUncertaintyMs==null?"":` · ≤${record.timingUncertaintyMs} ms uncertainty`}`:
      `${record.rssi} dBm · channel ${record.channel} · ${record.security}`;
    return `<article><strong>${escapeHtml(when)}</strong><br>${escapeHtml(detail)}</article>`;
  }).join("");
}

function closeDetail(){
  document.body.classList.remove("detail-open");
  detailSelection=null;
}
$("#closeDetail").onclick=$("#closeDetailBottom").onclick=$("#detailBackdrop").onclick=closeDetail;
$("#copyRaw").onclick=async()=>{
  const value=$("#detailRaw").textContent;
  let copied=false;
  try{
    await navigator.clipboard.writeText(value);
    copied=true;
  }catch(error){}
  if(!copied){
    const area=document.createElement("textarea");
    area.value=value;
    area.setAttribute("readonly","");
    area.style.cssText="position:fixed;left:-9999px;top:0";
    document.body.appendChild(area);
    area.select();
    try{copied=document.execCommand("copy");}catch(error){}
    area.remove();
  }
  $("#copyRaw").textContent=copied?"Copied ✓":"Copy unavailable";
  setTimeout(()=>$("#copyRaw").textContent="Copy raw data",1600);
};

function wrapCanvasText(context,text,x,y,maxWidth,lineHeight){
  const words=String(text).split(/\s+/);
  let line="",lines=0;
  for(const word of words){
    const test=line?`${line} ${word}`:word;
    if(context.measureText(test).width>maxWidth&&line){
      context.fillText(line,x,y+lines*lineHeight);line=word;lines++;
    }else line=test;
  }
  if(line){context.fillText(line,x,y+lines*lineHeight);lines++;}
  return lines;
}

function canvasRoundRect(context,x,y,width,height,radius,fill,stroke){
  const r=Math.min(radius,width/2,height/2);
  context.beginPath();
  context.moveTo(x+r,y);
  context.arcTo(x+width,y,x+width,y+height,r);
  context.arcTo(x+width,y+height,x,y+height,r);
  context.arcTo(x,y+height,x,y,r);
  context.arcTo(x,y,x+width,y,r);
  context.closePath();
  if(fill){context.fillStyle=fill;context.fill();}
  if(stroke){context.strokeStyle=stroke;context.stroke();}
}

async function saveDetailCardImage(){
  const canvas=document.createElement("canvas");
  canvas.width=1440;canvas.height=2040;
  const context=canvas.getContext("2d");
  const colors={
    outside:"#03070b",panel:"#081019",line:"#0d6972",
    rule:"#14323a",cyan:"#00fff7",purple:"#c067ff",muted:"#67b8bc"
  };
  context.fillStyle=colors.outside;context.fillRect(0,0,canvas.width,canvas.height);
  context.lineWidth=2;
  canvasRoundRect(context,36,36,canvas.width-72,canvas.height-72,28,colors.panel,colors.line);

  let y=105;
  context.font="22px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.fillStyle=colors.purple;
  context.fillText($("#detailType").textContent,80,y);y+=52;
  context.font="bold 43px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.fillStyle=colors.cyan;
  y+=wrapCanvasText(context,$("#detailTitle").textContent,80,y,1210,52)*52+18;

  const summaries=[...$("#detailSummary").querySelectorAll("article")];
  const summaryGap=18,summaryX=80,summaryWidth=(1280-summaryGap*2)/3;
  summaries.forEach((article,index)=>{
    const x=summaryX+index*(summaryWidth+summaryGap);
    canvasRoundRect(context,x,y,summaryWidth,112,16,colors.panel,colors.line);
    context.font="bold 30px ui-monospace, SFMono-Regular, Menlo, monospace";
    context.fillStyle=colors.cyan;
    context.fillText(article.querySelector("strong").textContent,x+20,y+45);
    context.font="18px ui-monospace, SFMono-Regular, Menlo, monospace";
    context.fillStyle=colors.muted;
    context.fillText(article.querySelector("span").textContent,x+20,y+82);
  });
  y+=150;

  const section=title=>{
    context.fillStyle=colors.purple;
    context.font="bold 22px ui-monospace, SFMono-Regular, Menlo, monospace";
    context.fillText(title.toUpperCase(),80,y);
    y+=34;
  };
  section("Observed data");
  const terms=$("#detailFields").querySelectorAll("dt");
  const descriptions=$("#detailFields").querySelectorAll("dd");
  for(let i=0;i<terms.length&&y<1120;i++){
    context.strokeStyle=colors.rule;context.lineWidth=2;
    context.beginPath();context.moveTo(80,y+40);context.lineTo(1360,y+40);context.stroke();
    context.font="18px ui-monospace, SFMono-Regular, Menlo, monospace";
    context.fillStyle=colors.muted;context.fillText(terms[i].textContent,92,y+25);
    context.fillStyle=colors.cyan;
    const count=wrapCanvasText(context,descriptions[i].textContent,420,y+25,910,25);
    y+=Math.max(1,count)*25+18;
  }

  y+=25;section("Raw advertisement data");
  const raw=$("#detailRaw").textContent;
  context.font="16px ui-monospace, SFMono-Regular, Menlo, monospace";
  const rawLines=Math.min(7,Math.max(1,Math.ceil(context.measureText(raw).width/1200)));
  canvasRoundRect(context,80,y,1280,rawLines*24+40,14,colors.outside,colors.line);
  context.fillStyle=colors.cyan;
  wrapCanvasText(context,raw,100,y+30,1240,24);
  y+=rawLines*24+72;

  const decoded=[...$("#decodedFields").querySelectorAll("article")].slice(0,4);
  if(decoded.length&&y<1600){
    section("Decoded advertisement");
    context.font="17px ui-monospace, SFMono-Regular, Menlo, monospace";
    for(const article of decoded){
      context.fillStyle=colors.cyan;
      const lines=wrapCanvasText(context,article.textContent.trim(),92,y+22,1220,23);
      y+=Math.max(1,lines)*23+18;
      context.strokeStyle=colors.rule;context.beginPath();
      context.moveTo(80,y);context.lineTo(1360,y);context.stroke();y+=8;
    }
  }

  if(y<1740){
    y+=20;section("Recent evidence");
    canvasRoundRect(context,80,y,1280,170,14,colors.panel,colors.line);
    context.fillStyle=colors.muted;
    context.font="15px ui-monospace, SFMono-Regular, Menlo, monospace";
    context.fillText("stronger",96,y+25);context.fillText("weaker",96,y+152);
    const polyline=$("#detailChart polyline");
    if(polyline){
      const points=polyline.getAttribute("points").trim().split(/\s+/).map(pair=>
        pair.split(",").map(Number));
      if(points.length){
        context.strokeStyle=colors.cyan;context.lineWidth=4;context.beginPath();
        points.forEach(([px,py],index)=>{
          const x=120+px*12.2,chartY=y+20+py*1.3;
          if(index===0)context.moveTo(x,chartY);else context.lineTo(x,chartY);
        });
        context.stroke();
      }
    }
    y+=200;
  }

  const finalHeight=Math.min(canvas.height,Math.max(900,Math.ceil(y+145)));
  const footerY=finalHeight-55;
  context.fillStyle=colors.muted;
  context.font="17px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.fillText(`Captured by RyancitoSentinal · ${new Date().toLocaleString()}`,80,footerY);
  context.textAlign="right";
  context.fillText(sessionId?`Session ${sessionId}`:"Browser evidence card",1360,footerY);
  context.textAlign="left";

  // Crop the fixed working canvas to the content, then clip it back into the
  // same rounded panel shape used by the on-screen detail card.
  const outputCanvas=document.createElement("canvas");
  outputCanvas.width=canvas.width;outputCanvas.height=finalHeight;
  const output=outputCanvas.getContext("2d");
  output.fillStyle=colors.outside;output.fillRect(0,0,outputCanvas.width,finalHeight);
  output.save();
  canvasRoundRect(output,36,36,outputCanvas.width-72,finalHeight-72,28,colors.panel,null);
  output.clip();
  output.drawImage(canvas,0,0,canvas.width,finalHeight,0,0,canvas.width,finalHeight);
  output.restore();
  output.lineWidth=2;
  canvasRoundRect(output,36,36,outputCanvas.width-72,finalHeight-72,28,null,colors.line);

  const blob=await new Promise(resolve=>outputCanvas.toBlob(resolve,"image/png"));
  if(!blob)throw new Error("PNG rendering unavailable");
  const safeName=$("#detailTitle").textContent.replace(/[^a-z0-9_-]+/gi,"-").slice(0,50)||"observation";
  const filename=`RyancitoSentinal-${safeName}.png`;
  const file=typeof File!=="undefined"?
    new File([blob],filename,{type:"image/png"}):null;
  if(file&&navigator.canShare&&navigator.canShare({files:[file]})){
    try{
      await navigator.share({files:[file],title:"RyancitoSentinal observation"});
      return;
    }catch(error){
      if(error.name==="AbortError")return;
    }
  }
  const link=document.createElement("a");
  link.href=URL.createObjectURL(blob);link.download=filename;
  document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
}
$("#saveCardImage").onclick=async()=>{
  const button=$("#saveCardImage");button.textContent="Rendering…";
  try{
    await saveDetailCardImage();button.textContent="Image ready ✓";
  }catch(error){
    button.textContent="Image failed";
  }
  setTimeout(()=>button.textContent="Save card image",1800);
};
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"&&document.body.classList.contains("detail-open"))
    closeDetail();
  if(event.key==="Escape"&&document.body.classList.contains("sessions-open"))
    document.body.classList.remove("sessions-open");
});

async function prepareExport(message){
  let collector={};
  try{collector=await fetch("/api/status",{cache:"no-store"}).then(r=>r.json());}
  catch(error){collector={error:String(error)};}
  const summaries=new Map();
  for(const observation of message.observations){
    const key=`${observation.addrType}:${observation.mac}`;
    const summary=summaries.get(key)||{
      id:key,mac:observation.mac,addrType:observation.addrType,
      firstSeen:observation.estimatedObservedAt||observation.receivedAt,
      lastSeen:observation.estimatedObservedAt||observation.receivedAt,
      strongestRssi:observation.rssi,latestRssi:observation.rssi,
      recordedObservations:0,advertisementChanges:0
    };
    summary.lastSeen=observation.estimatedObservedAt||observation.receivedAt;
    summary.latestRssi=observation.rssi;
    summary.strongestRssi=Math.max(summary.strongestRssi,observation.rssi);
    summary.recordedObservations++;
    if(observation.flags&2)summary.advertisementChanges++;
    summaries.set(key,summary);
  }
  const metadata={
    evidenceSchema:"RyancitoSentinal Evidence",
    schemaVersion:2,
    sessionId:message.sessionId,
    sessionStartTime:new Date(message.sessionStartTime).toISOString(),
    sessionEndTime:new Date(message.sessionEndTime).toISOString(),
    firmware:{name:collector.firmware||"unknown",version:collector.version||"unknown"},
    scanConfiguration:collector.config||{},
    exportedAt:new Date().toISOString(),
    observationCount:message.observations.length+message.wifiObservations.length,
    droppedRecordCount:message.dropped,
    observed:{
      bleObservations:message.observations,
      wifiObservations:message.wifiObservations
    },
    timestampProvenance:{
      esp32Field:"deviceMs",
      browserReceiptField:"receivedAt",
      estimatedWallClockField:"estimatedObservedAt",
      uncertaintyField:"timingUncertaintyMs"
    },
    derived:{devices:[...summaries.values()]},
    annotations:{case:message.session?.case||caseContext(),devices:message.annotations||[]},
    hashProcedure:"SHA-256 of UTF-8 JSON.stringify(document) before the top-level sha256 property is added"
  };
  if(message.format==="json"){
    const canonical=JSON.stringify(metadata);
    metadata.sha256=await sha256(canonical);
    download(`RyancitoSentinal-${message.sessionId}.json`,"application/json",JSON.stringify(metadata,null,2));
  }else{
    const lines=["radio,sessionId,sequence,receivedAt,identifier,rssi,channel,security,advType,flags,raw"];
    for(const o of message.observations)lines.push([
      "BLE",o.sessionId,o.seq,new Date(o.receivedAt).toISOString(),o.mac,
      o.rssi,"","",o.advType,o.flags,o.advHex
    ].map(value=>`"${String(value).replaceAll('"','""')}"`).join(","));
    for(const o of message.wifiObservations)lines.push([
      "Wi-Fi",o.sessionId,o.scan,new Date(o.receivedAt).toISOString(),o.bssid,
      o.rssi,o.channel,o.security,"","","SSID: "+o.ssid
    ].map(value=>`"${String(value).replaceAll('"','""')}"`).join(","));
    for(const annotation of message.annotations||[])lines.push([
      "Annotation",annotation.sessionId,"",new Date(annotation.updatedAt||Date.now()).toISOString(),
      annotation.deviceId,"","","","","",JSON.stringify(annotation)
    ].map(value=>`"${String(value??"").replaceAll('"','""')}"`).join(","));
    const body=lines.join("\r\n");
    const hash=await sha256(body);
    download(`RyancitoSentinal-${message.sessionId}.csv`,"text/csv",
      body+`\r\n# SHA-256,"${hash}"\r\n`);
  }
  $("#exportStatus").textContent=`Export ready — ${message.observations.length} BLE and ${(message.wifiObservations||[]).length} WiFi records`;
}

async function sha256(text){
  if(globalThis.crypto&&crypto.subtle){
    try{
      const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text));
      return[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
    }catch(error){}
  }
  return sha256Fallback(new TextEncoder().encode(text));
}

function sha256Fallback(bytes){
  const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const bitLength=bytes.length*8;
  const paddedLength=((bytes.length+9+63)>>6)<<6;
  const data=new Uint8Array(paddedLength);data.set(bytes);data[bytes.length]=0x80;
  const view=new DataView(data.buffer);
  view.setUint32(paddedLength-8,Math.floor(bitLength/0x100000000),false);
  view.setUint32(paddedLength-4,bitLength>>>0,false);
  const w=new Uint32Array(64);
  const rotr=(x,n)=>(x>>>n)|(x<<(32-n));
  for(let offset=0;offset<paddedLength;offset+=64){
    for(let i=0;i<16;i++)w[i]=view.getUint32(offset+i*4,false);
    for(let i=16;i<64;i++){
      const s0=rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>>3);
      const s1=rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>>10);
      w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
    }
    let[a,b,c,d,e,f,g,h]=H;
    for(let i=0;i<64;i++){
      const S1=rotr(e,6)^rotr(e,11)^rotr(e,25);
      const ch=(e&f)^(~e&g);
      const t1=(h+S1+ch+K[i]+w[i])>>>0;
      const S0=rotr(a,2)^rotr(a,13)^rotr(a,22);
      const maj=(a&b)^(a&c)^(b&c);
      const t2=(S0+maj)>>>0;
      h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    H[0]=(H[0]+a)>>>0;H[1]=(H[1]+b)>>>0;H[2]=(H[2]+c)>>>0;H[3]=(H[3]+d)>>>0;
    H[4]=(H[4]+e)>>>0;H[5]=(H[5]+f)>>>0;H[6]=(H[6]+g)>>>0;H[7]=(H[7]+h)>>>0;
  }
  return H.map(value=>value.toString(16).padStart(8,"0")).join("");
}
function download(name,type,content){
  const link=document.createElement("a");
  link.href=URL.createObjectURL(new Blob([content],{type}));
  link.download=name;document.body.appendChild(link);link.click();link.remove();
  $("#exportStatus").textContent=`Preparing ${name}…`;
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
}

function renderSessionList(currentId){
  const container=$("#sessionList");
  if(!savedSessions.length){
    container.innerHTML='<p class="evidence-note">No saved sessions.</p>';return;
  }
  container.innerHTML=savedSessions.map(session=>{
    const active=session.id===currentId;
    const end=session.endTime?formatDate(session.endTime):"Active";
    return `<article class="session-row" data-session="${escapeHtml(session.id)}">
      <input class="session-select" type="checkbox" value="${escapeHtml(session.id)}">
      <div><strong>${escapeHtml(session.name||(active?"Current session":formatDate(session.startTime)))}</strong>
      <span>${escapeHtml(session.id)}<br>${escapeHtml(formatDate(session.startTime))} → ${escapeHtml(end)}</span></div>
      <span>${session.observationCount||0} BLE · ${session.wifiObservationCount||0} WiFi · ${session.dropped||0} dropped</span>
      <div class="session-actions">
        <button data-review-session="${escapeHtml(session.id)}">Review</button>
        <button data-rename-session="${escapeHtml(session.id)}">Rename</button>
        <button data-export-session="${escapeHtml(session.id)}">JSON</button>
        <button data-delete-session="${escapeHtml(session.id)}" ${active?"disabled":""}>Delete</button>
      </div>
    </article>`;
  }).join("");
  container.querySelectorAll("[data-export-session]").forEach(button=>button.onclick=()=>
    worker.postMessage({type:"export",format:"json",sessionId:button.dataset.exportSession}));
  container.querySelectorAll("[data-review-session]").forEach(button=>button.onclick=()=>
    worker.postMessage({type:"sessionAnalysis",sessionIds:[button.dataset.reviewSession]}));
  container.querySelectorAll("[data-rename-session]").forEach(button=>button.onclick=()=>{
    const session=savedSessions.find(item=>item.id===button.dataset.renameSession);
    const name=prompt("Session name",session?.name||"");
    if(name!==null)worker.postMessage({type:"renameSession",sessionId:button.dataset.renameSession,name:name.trim()});
  });
  container.querySelectorAll("[data-delete-session]").forEach(button=>button.onclick=()=>{
    if(confirm("Delete this session and all of its browser evidence?"))
      worker.postMessage({type:"deleteSession",sessionId:button.dataset.deleteSession});
  });
}

function renderSessionComparison(results){
  if(!results.length){$("#sessionAnalysis").textContent="No session data.";return;}
  const ids=result=>new Set(result.identifiers||[]);
  const timeline=result=>(result.timeline||[]).slice(0,20);
  if(results.length===1){
    const result=results[0],identifiers=ids(result);
    $("#sessionAnalysis").innerHTML=`<h3>Session review</h3>
      <article class="insight"><strong>${escapeHtml(result.id)}</strong><span>${result.bleCount} BLE observations · ${result.wifiCount} WiFi observations · ${identifiers.size} identifiers</span></article>
      <h3>Timeline preview</h3><article class="insight"><span>${
        timeline(result).map(event=>`${escapeHtml(formatDate(event.at))} — ${escapeHtml(event.label)}`).join("<br>")||"No events"
      }</span></article>`;
    return;
  }
  const left=ids(results[0]),right=ids(results[1]);
  const shared=[...left].filter(id=>right.has(id));
  const onlyLeft=[...left].filter(id=>!right.has(id));
  const onlyRight=[...right].filter(id=>!left.has(id));
  $("#sessionAnalysis").innerHTML=`
    <h3>Comparison</h3>
    <div class="comparison-grid">
      <article><strong>Only first (${onlyLeft.length})</strong><pre>${escapeHtml(onlyLeft.join("\n")||"None")}</pre></article>
      <article><strong>Shared (${shared.length})</strong><pre>${escapeHtml(shared.join("\n")||"None")}</pre></article>
      <article><strong>Only second (${onlyRight.length})</strong><pre>${escapeHtml(onlyRight.join("\n")||"None")}</pre></article>
    </div>
    <h3>Timeline preview</h3>
    ${results.map(result=>`<article class="insight"><strong>${escapeHtml(result.id)}</strong><span>${
      timeline(result).map(event=>`${escapeHtml(formatDate(event.at))} — ${escapeHtml(event.label)}`).join("<br>")||"No events"
    }</span></article>`).join("")}`;
}

async function refreshStorage(){
  try{
    if(!navigator.storage?.estimate)throw new Error("Storage estimate unavailable");
    const estimate=await navigator.storage.estimate();
    const used=estimate.usage||0,quota=estimate.quota||0;
    const percent=quota?used/quota*100:0;
    $("#storageStatus").textContent=`Browser evidence storage: ${(used/1048576).toFixed(1)} MB of ${(quota/1048576).toFixed(0)} MB (${percent.toFixed(1)}%)`;
    $("#storageStatus").classList.toggle("danger",percent>=85);
  }catch(error){$("#storageStatus").textContent=String(error.message||error);}
}

async function importAndVerify(file){
  const text=await file.text();
  const evidence=JSON.parse(text);
  const expected=evidence.sha256;
  if(!expected)throw new Error("No SHA-256 field found");
  delete evidence.sha256;
  const actual=await sha256(JSON.stringify(evidence));
  const verified=actual.toLowerCase()===String(expected).toLowerCase();
  $("#exportStatus").textContent=verified?
    `Verified ✓ ${file.name} · session ${evidence.sessionId||"unknown"}`:
    `Modified or invalid ✕ ${file.name}`;
  if(!verified)throw new Error(`Hash mismatch. Expected ${expected}; calculated ${actual}`);
}

async function refreshDiagnostics(){
  try{
    const status=await fetch("/api/status",{cache:"no-store"}).then(r=>r.json());
    $("#diagnostics").textContent=JSON.stringify(status,null,2);
    $("#collectorSsid").textContent=status.ssid||"—";
    $("#collectorIp").textContent=status.ip||"—";
    $("#collectorVersion").textContent=`${status.firmware} ${status.version}`;
    $("#collectorHeap").textContent=`${(status.free_heap/1048576).toFixed(2)} MB`;
    $("#collectorBuffer").textContent=`${status.raw_buffer_used}/${status.raw_buffer_capacity} raw`;
  }catch(error){$("#diagnostics").textContent=String(error);}
}
setInterval(refreshDiagnostics,5000);refreshDiagnostics();

function applySettings(){
  document.body.classList.toggle("light",settings.theme==="light");
  $("#theme").value=settings.theme;
  $("#minRssi").value=String(settings.minRssi);
  $("#pollMs").value=String(settings.pollMs);
  $("#showWifi").checked=settings.showWifi;
  $("#showBle").checked=settings.showBle;
  $("#compact").checked=settings.compact;
  $("#wifiMs").value=String(settings.wifiMs);
  $("#maxSessions").value=String(settings.maxSessions);
  $("#printOrientation").value=settings.printOrientation;
  $("#caseId").value=settings.caseId;
  $("#investigator").value=settings.investigator;
  $("#locationLabel").value=settings.locationLabel;
  $("#caseNote").value=settings.caseNote;
  updateConnectionClient();
  $(".wifi-card").hidden=!settings.showWifi;
  $(".devices-card").hidden=!settings.showBle;
  document.body.classList.toggle("compact",settings.compact);
  updateBandFilters();
  updatePrintOrientation();
  wifiDirty=true;
  saveSettings();
}
$("#settingsButton").onclick=()=>document.body.classList.add("drawer-open");
$("#closeSettings").onclick=$("#backdrop").onclick=()=>document.body.classList.remove("drawer-open");
$("#theme").onchange=event=>{settings.theme=event.target.value;applySettings();};
$("#minRssi").onchange=event=>{settings.minRssi=Number(event.target.value);applySettings();};
$("#pollMs").onchange=event=>{settings.pollMs=Number(event.target.value);applySettings();};
$("#showWifi").onchange=event=>{settings.showWifi=event.target.checked;applySettings();};
$("#showBle").onchange=event=>{settings.showBle=event.target.checked;applySettings();};
$("#compact").onchange=event=>{settings.compact=event.target.checked;applySettings();};
$("#wifiMs").onchange=event=>{settings.wifiMs=Number(event.target.value);applySettings();};
$("#maxSessions").onchange=event=>{settings.maxSessions=Number(event.target.value);applySettings();};
for(const [selector,key] of [
  ["#caseId","caseId"],["#investigator","investigator"],
  ["#locationLabel","locationLabel"],["#caseNote","caseNote"]
]){
  $(selector).onchange=event=>{settings[key]=event.target.value.trim();applySettings();};
}
$("#printOrientation").onchange=event=>{
  settings.printOrientation=event.target.value;
  applySettings();
};
$("#search").oninput=()=>dirty=true;
$("#newSession").onclick=()=>{
  $("#exportStatus").textContent="Closing the current session and starting a new one…";
  worker.postMessage({type:"newSession"});
};
$("#saveAnnotation").onclick=()=>{
  if(!detailSelection)return;
  const annotation={
    deviceId:detailSelection.deviceId,
    friendlyName:$("#annotationName").value.trim(),
    classification:$("#annotationClass").value,
    watchlist:$("#annotationWatch").checked,
    tags:$("#annotationTags").value.split(",").map(value=>value.trim()).filter(Boolean),
    note:$("#annotationNote").value.trim()
  };
  worker.postMessage({type:"annotationSave",annotation});
  $("#saveAnnotation").textContent="Saved ✓";
  setTimeout(()=>$("#saveAnnotation").textContent="Save annotation",1400);
};
$("#scanWifiNow").onclick=event=>{
  event.currentTarget.disabled=true;
  event.currentTarget.textContent="Scanning…";
  worker.postMessage({type:"forceWifi"});
};
$("#clearBrowserData").onclick=()=>{
  if(confirm("Permanently delete every saved session, BLE/WiFi observation, and annotation from this browser? This cannot be undone.")){
    $("#exportStatus").textContent="Clearing all browser evidence…";
    worker.postMessage({type:"clear"});
  }
};

function updateBandFilters(){
  document.querySelectorAll(".band-filter").forEach(button=>{
    const active=!hiddenBands.has(button.dataset.band);
    button.classList.toggle("active",active);
    button.setAttribute("aria-pressed",String(active));
  });
}
document.querySelectorAll(".band-filter").forEach(button=>button.onclick=()=>{
  const band=button.dataset.band;
  if(hiddenBands.has(band))hiddenBands.delete(band);else hiddenBands.add(band);
  updateBandFilters();
  saveSettings();
});
$("#clearBleFilters").onclick=()=>{
  hiddenBands.clear();
  hidden.clear();
  settings.showHidden=false;
  settings.minRssi=-100;
  $("#search").value="";
  updateBandFilters();
  applySettings();
};
$("#exportJson").onclick=()=>worker.postMessage({type:"export",format:"json"});
$("#exportCsv").onclick=()=>worker.postMessage({type:"export",format:"csv"});
$("#openSessions").onclick=()=>{
  document.body.classList.remove("drawer-open");
  document.body.classList.add("sessions-open");
  worker.postMessage({type:"listSessions"});
};
$("#refreshSessions").onclick=()=>worker.postMessage({type:"listSessions"});
$("#closeSessions").onclick=$("#closeSessionsBottom").onclick=$("#sessionBackdrop").onclick=()=>
  document.body.classList.remove("sessions-open");
$("#compareSessions").onclick=()=>{
  const ids=[...document.querySelectorAll(".session-select:checked")].map(input=>input.value);
  if(ids.length!==2){$("#sessionAnalysis").textContent="Select exactly two sessions.";return;}
  worker.postMessage({type:"sessionAnalysis",sessionIds:ids});
};
$("#importEvidence").onclick=()=>$("#evidenceFile").click();
$("#evidenceFile").onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  $("#exportStatus").textContent=`Verifying ${file.name}…`;
  try{await importAndVerify(file);}
  catch(error){$("#exportStatus").textContent=`Verification failed: ${error.message||error}`;}
  event.target.value="";
};

function printReport(){
  document.body.classList.remove("drawer-open");
  document.body.classList.add("printing");
  updatePrintOrientation();
  window.print();
}
$("#printReportTop").onclick=printReport;
window.addEventListener("afterprint",()=>document.body.classList.remove("printing"));

function updatePrintOrientation(){
  let style=document.getElementById("dynamicPrintPage");
  if(!style){
    style=document.createElement("style");
    style.id="dynamicPrintPage";
    document.head.appendChild(style);
  }
  const orientation=settings.printOrientation==="portrait"?"portrait":"landscape";
  document.body.classList.toggle("print-portrait",orientation==="portrait");
  style.textContent=`@page { size: ${orientation}; margin: .35in; }`;
}

document.querySelectorAll(".collapse-button").forEach(button=>{
  const target=document.getElementById(button.dataset.target);
  const collapsed=settings.collapsed.includes(button.dataset.target);
  target.hidden=collapsed;button.textContent=collapsed?"⌄":"⌃";
  button.onclick=()=>{
    target.hidden=!target.hidden;
    button.textContent=target.hidden?"⌄":"⌃";
    settings.collapsed=[...document.querySelectorAll(".collapsible[hidden]")].map(node=>node.id);
    saveSettings();
  };
});

function updateSortIndicators(){
  document.querySelectorAll("th[data-ble-sort],th[data-wifi-sort]").forEach(th=>{
    const isBle=th.dataset.bleSort&&th.dataset.bleSort===settings.bleSort;
    const isWifi=th.dataset.wifiSort&&th.dataset.wifiSort===settings.wifiSort;
    const active=isBle||isWifi;
    th.classList.toggle("sort-active",active);
    th.dataset.arrow=active?
      ((isBle?settings.bleSortDir:settings.wifiSortDir)>0?"▲":"▼"):"";
  });
}
document.querySelectorAll("th[data-ble-sort]").forEach(th=>th.onclick=()=>{
  const key=th.dataset.bleSort;
  settings.bleSortDir=settings.bleSort===key?-settings.bleSortDir:(key==="name"||key==="mac"||key==="manufacturer"?1:-1);
  settings.bleSort=key;saveSettings();updateSortIndicators();
});
document.querySelectorAll("th[data-wifi-sort]").forEach(th=>th.onclick=()=>{
  const key=th.dataset.wifiSort;
  settings.wifiSortDir=settings.wifiSort===key?-settings.wifiSortDir:(key==="ssid"||key==="security"||key==="bssid"?1:-1);
  settings.wifiSort=key;wifiDirty=true;dirty=true;saveSettings();updateSortIndicators();
});
$("#pauseDisplay").onclick=event=>{
  paused=!paused;
  event.target.textContent=paused?"Resume display":"Pause display";
  if(paused){
    connectionStatus="Display paused · recording continues";
  }else{
    connectionStatus="Live";
  }
  updateConnectionClient();
  if(!paused){dirty=true;render();}
};
updateSortIndicators();
updatePrintOrientation();
applySettings();
refreshStorage();
setInterval(refreshStorage,30000);
