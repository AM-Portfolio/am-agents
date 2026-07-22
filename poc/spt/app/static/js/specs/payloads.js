/* Specs — payload sets, active payloads, OpenAPI enrich */
function sptApiSlug(value){
  return String(value||"").trim().toLowerCase().replace(/[^a-z0-9]+/g,".").replace(/^\.+|\.+$/g,"") || "op";
}

function normalizeOpPath(path){
  return String(path||"").replace(/\u200b/g,"").replace(/\s+/g,"").replace(/\/+$/,"") || "/";
}

function opApiIds(method, path, operationId){
  const ids = [];
  const p = normalizeOpPath(path);
  if(operationId) ids.push(sptApiSlug(operationId));
  ids.push(sptApiSlug(method+"."+p));
  ids.push(sptApiSlug(method+" "+p));
  // Compact form without separators (matches older saves like getdashboardperformance)
  ids.push(sptApiSlug(String(method||"")+String(p||"").replace(/^\//,"")));
  return ids.filter((v,i,a)=>a.indexOf(v)===i);
}

/** Resolve active / set payload for an operation (id aliases + method/path fallback). */
function findActivePayload(method, path, operationId){
  const ids = opApiIds(method, path, operationId);
  for(let i=0;i<ids.length;i++){
    const a = specsActivePayloads[ids[i]];
    if(a) return { apiId: ids[i], payload: a };
  }
  const m = String(method||"").toLowerCase();
  const p = normalizeOpPath(path);
  const keys = Object.keys(specsActivePayloads||{});
  for(let i=0;i<keys.length;i++){
    const a = specsActivePayloads[keys[i]];
    if(!a) continue;
    if(String(a.method||"").toLowerCase() === m && normalizeOpPath(a.path) === p){
      return { apiId: keys[i], payload: a };
    }
  }
  return null;
}

function primaryApiId(op){
  const ids = opApiIds(op.method, op.path, op.operationId);
  return ids[0] || sptApiSlug(op.method+"."+op.path);
}

function activePayloadStorageKey(service){
  return "spt_active_payloads_"+String(service||"");
}

function loadActivePayloadsFromStorage(service){
  try {
    const raw = localStorage.getItem(activePayloadStorageKey(service));
    specsActivePayloads = raw ? (JSON.parse(raw)||{}) : {};
  } catch(_){ specsActivePayloads = {}; }
}

function persistActivePayloads(service){
  try {
    localStorage.setItem(activePayloadStorageKey(service||selectedSpecService), JSON.stringify(specsActivePayloads||{}));
  } catch(_){}
}

function payloadsForApi(apiId){
  return (specsPayloadIndex||[]).filter(r=>String(r.api_id)===String(apiId))
    .sort((a,b)=>Number(b.version||0)-Number(a.version||0));
}

function defaultWorkingRequest(op, doc){
  const components = (doc && doc.components) || {};
  const query = {};
  const pathParams = {};
  (op.parameters||[]).forEach(p=>{
    if(!p || !p.name) return;
    const ex = exampleFromParam(p);
    if(ex == null) return;
    if(p.in === "query") query[p.name] = ex;
    if(p.in === "path") pathParams[p.name] = ex;
  });
  let body = null;
  const rb = op.requestBody;
  if(rb && rb.content){
    const ct = Object.keys(rb.content).find(k=>String(k).indexOf("json")>=0) || Object.keys(rb.content)[0];
    const media = rb.content[ct] || {};
    if(media.example != null) body = media.example;
    else if(media.examples){
      const first = media.examples[Object.keys(media.examples)[0]];
      if(first && first.value != null) body = first.value;
    } else {
      body = exampleFromSchema(media.schema, components, 0);
    }
  }
  return {
    method: op.method,
    path: op.path,
    query: query,
    pathParams: pathParams,
    body: body,
    name: "working",
    version: null
  };
}

function collectPayloadRefsForRun(){
  // Prefer whole service set when selected
  if(specsPayloadSetVersion != null){
    return [];
  }
  return Object.keys(specsActivePayloads||{}).map(apiId=>{
    const a = specsActivePayloads[apiId];
    if(!a || !a.name) return null;
    const ref = { api_id: apiId, name: a.name };
    if(a.version != null) ref.version = a.version;
    if(a.set_version != null){ ref.set_version = a.set_version; ref.from_set = true; }
    return ref;
  }).filter(Boolean);
}

function collectPayloadSetVersionForRun(){
  return specsPayloadSetVersion != null ? Number(specsPayloadSetVersion) : null;
}

function specsLoadApiStorageKey(service){
  return "spt_load_api_ids_"+String(service||"");
}

function loadSpecsLoadApiIds(service){
  try {
    const raw = localStorage.getItem(specsLoadApiStorageKey(service));
    specsLoadApiIds = raw ? (JSON.parse(raw)||[]) : [];
    if(!Array.isArray(specsLoadApiIds)) specsLoadApiIds = [];
  } catch(_){ specsLoadApiIds = []; }
  syncSpecsLoadApiIdsToRunPicker();
}

function persistSpecsLoadApiIds(service){
  try {
    localStorage.setItem(specsLoadApiStorageKey(service||selectedSpecService), JSON.stringify(specsLoadApiIds||[]));
  } catch(_){}
  syncSpecsLoadApiIdsToRunPicker();
}

/** Keep header Run test / APIs picker in sync with OpenAPI checkboxes */
function syncSpecsLoadApiIdsToRunPicker(){
  if(typeof selectedApiIds === "undefined") return;
  if(specsLoadApiIds && specsLoadApiIds.length){
    selectedApiIds = specsLoadApiIds.slice();
  }
  const btn = document.getElementById("btn-api-picker");
  if(btn){
    btn.textContent = (specsLoadApiIds && specsLoadApiIds.length)
      ? ("APIs ("+specsLoadApiIds.length+")")
      : "APIs (all)";
  }
}

function isSpecsLoadApiChecked(apiId){
  return (specsLoadApiIds||[]).indexOf(String(apiId)) >= 0;
}

function setSpecsLoadApiChecked(apiId, on){
  const id = String(apiId||"");
  if(!id) return;
  const set = new Set(specsLoadApiIds||[]);
  if(on) set.add(id);
  else set.delete(id);
  specsLoadApiIds = Array.from(set);
  persistSpecsLoadApiIds(selectedSpecService);
}

function setSpecsLoadApiIds(ids){
  specsLoadApiIds = (ids||[]).map(String).filter(Boolean);
  persistSpecsLoadApiIds(selectedSpecService);
}

function payloadSetStorageKey(service){
  return "spt_payload_set_version_"+String(service||"");
}

function persistPayloadSetVersion(service, version){
  try {
    if(version == null) localStorage.removeItem(payloadSetStorageKey(service));
    else localStorage.setItem(payloadSetStorageKey(service), String(version));
  } catch(_){}
}

function loadPayloadSetVersionFromStorage(service){
  try {
    const v = localStorage.getItem(payloadSetStorageKey(service));
    return v != null && v !== "" ? Number(v) : null;
  } catch(_){ return null; }
}

async function loadServicePayloadSets(service, force){
  if(!service) return null;
  if(!force && specsPayloadSetService === service && specsPayloadSetDetail){
    return specsPayloadSetDetail;
  }
  try {
    await fetchJson("/api/payload-sets/"+encodeURIComponent(service)+"/ensure", { method: "POST" });
  } catch(_){}
  let list;
  try {
    list = await fetchJson("/api/payload-sets/"+encodeURIComponent(service));
  } catch(_){
    list = { sets: [], active_version: null };
  }
  specsPayloadSets = list.sets || [];
  const stored = loadPayloadSetVersionFromStorage(service);
  // Prefer in-memory (user just picked) → localStorage (reload) → server active
  let ver = specsPayloadSetVersion;
  if(ver == null) ver = stored;
  if(ver == null) ver = list.active_version;
  if(ver == null && specsPayloadSets.length) ver = specsPayloadSets[0].version;
  // Drop stale versions that no longer exist
  if(ver != null && specsPayloadSets.length){
    const exists = specsPayloadSets.some(s=> Number(s.version) === Number(ver));
    if(!exists){
      ver = list.active_version != null ? list.active_version
        : (specsPayloadSets[0] && specsPayloadSets[0].version);
    }
  }
  specsPayloadSetVersion = ver != null ? Number(ver) : null;
  specsPayloadSetService = service;
  if(specsPayloadSetVersion != null){
    try {
      specsPayloadSetDetail = await fetchJson(
        "/api/payload-sets/"+encodeURIComponent(service)+"/"+encodeURIComponent(specsPayloadSetVersion)
      );
    } catch(_){
      specsPayloadSetDetail = null;
      // Fall back to server active if stored version fetch fails
      if(list.active_version != null && Number(list.active_version) !== Number(specsPayloadSetVersion)){
        specsPayloadSetVersion = Number(list.active_version);
        try {
          specsPayloadSetDetail = await fetchJson(
            "/api/payload-sets/"+encodeURIComponent(service)+"/"+encodeURIComponent(specsPayloadSetVersion)
          );
        } catch(__){ specsPayloadSetDetail = null; }
      }
    }
  } else {
    specsPayloadSetDetail = null;
  }
  persistPayloadSetVersion(service, specsPayloadSetVersion);
  applyPayloadSetToActive(specsPayloadSetDetail);
  try { if(typeof syncPortalUrl === "function") syncPortalUrl({ replace: true }); } catch(_){}
  return specsPayloadSetDetail;
}

function applyPayloadSetToActive(payloadSet){
  specsActivePayloads = {};
  if(!payloadSet || !payloadSet.apis){
    persistActivePayloads(selectedSpecService);
    return;
  }
  const setVer = payloadSet.version;
  Object.keys(payloadSet.apis).forEach(apiId=>{
    const entry = payloadSet.apis[apiId] || {};
    const req = entry.request || {};
    let body = req.body;
    if(typeof body === "string"){
      try { body = JSON.parse(body); } catch(_){}
    }
    const method = String(req.method || "").toLowerCase();
    const path = req.path || "";
    const payload = {
      name: entry.name || "working",
      version: null,
      set_version: setVer,
      method: method,
      path: path,
      body: body,
      query: req.query || {},
      pathParams: req.path_params || req.pathParams || {}
    };
    // Index under every alias so Swagger opblock lookup always hits
    const aliases = opApiIds(method, path, apiId).concat([apiId, sptApiSlug(apiId)]);
    aliases.filter((v,i,a)=>a.indexOf(v)===i).forEach(id=>{
      specsActivePayloads[id] = payload;
    });
  });
  persistActivePayloads(selectedSpecService);
}

function apiRegisteredInSet(apiId){
  const apis = (specsPayloadSetDetail && specsPayloadSetDetail.apis) || {};
  if(apis[apiId]) return true;
  return false;
}

function opRegisteredInSet(op){
  const apis = (specsPayloadSetDetail && specsPayloadSetDetail.apis) || {};
  const ids = opApiIds(op.method, op.path, op.operationId);
  for(let i=0;i<ids.length;i++){
    if(apis[ids[i]]) return ids[i];
  }
  return null;
}

function renderPayloadSetBar(extraClass, opts){
  opts = opts || {};
  // Try APIs: set picker only — version create lives under Edit → New version
  const showLoad = opts.showLoad === true;
  const showNew = opts.showNewVersion === true;
  const sets = specsPayloadSets || [];
  const ver = specsPayloadSetVersion;
  const detail = specsPayloadSetDetail || {};
  const n = detail.apis ? Object.keys(detail.apis).length : 0;
  const optsHtml = sets.length
    ? sets.map(s=>{
        const sel = Number(s.version)===Number(ver) ? " selected" : "";
        return '<option value="'+esc(String(s.version))+'"'+sel+'>'+
          esc("v"+s.version+(s.label?" "+s.label:"")+" · "+(s.api_count||0))+
        '</option>';
      }).join("")
    : '<option value="">—</option>';
  return '<div class="oas-set-bar '+(extraClass||'')+'">'+
    '<label class="sub">Set</label>'+
    '<select id="oas-set-select" title="Select set version (auto-loads)">'+optsHtml+'</select>'+
    (showLoad ? '<button type="button" class="secondary" id="oas-set-load">Load</button>' : '')+
    (showNew ? '<button type="button" class="secondary" id="oas-set-new">+ version</button>' : '')+
    '<span class="sub" id="oas-set-status">'+(ver!=null?('v'+esc(String(ver))+' · '+n+' APIs'):'')+'</span>'+
  '</div>';
}

async function bindPayloadSetBar(){
  const sel = document.getElementById("oas-set-select");
  const loadBtn = document.getElementById("oas-set-load");
  const newBtn = document.getElementById("oas-set-new");
  const status = document.getElementById("oas-set-status");
  const service = selectedSpecService;
  if(!service) return;

  if(sel && !sel._sptBound){
    sel._sptBound = true;
    sel.onchange = async ()=>{
      const v = sel.value ? Number(sel.value) : null;
      specsPayloadSetVersion = v;
      persistPayloadSetVersion(service, v);
      if(v != null){
        try {
          await fetchJson("/api/payload-sets/"+encodeURIComponent(service)+"/"+v+"/activate", { method: "POST" });
        } catch(_){}
        await loadServicePayloadSets(service, true);
        applyPayloadSetToActive(specsPayloadSetDetail);
        if(status){
          const n = specsPayloadSetDetail && specsPayloadSetDetail.apis
            ? Object.keys(specsPayloadSetDetail.apis).length : 0;
          status.innerHTML = 'Active set <strong>v'+esc(String(v))+'</strong> · '+n+' API payload(s) registered';
        }
        try { syncPortalUrl({ replace: true }); } catch(_){}
        if(specsView === "swagger") await renderSpecDetail();
        else if(specsView === "overview") await renderSpecDetail();
      }
    };
  }
  if(loadBtn){
    loadBtn.onclick = async ()=>{
      const selVer = sel && sel.value ? Number(sel.value) : specsPayloadSetVersion;
      if(selVer != null) specsPayloadSetVersion = selVer;
      persistPayloadSetVersion(service, specsPayloadSetVersion);
      // Keep server active in sync so reload + other tabs see the same set
      if(specsPayloadSetVersion != null){
        try {
          await fetchJson(
            "/api/payload-sets/"+encodeURIComponent(service)+"/"+specsPayloadSetVersion+"/activate",
            { method: "POST" }
          );
        } catch(_){}
      }
      await loadServicePayloadSets(service, true);
      applyPayloadSetToActive(specsPayloadSetDetail);
      const n = Object.keys(specsActivePayloads||{}).length;
      if(status) status.textContent = "Loaded set v"+specsPayloadSetVersion+" → "+n+" active API payload(s)";
      try { syncPortalUrl({ replace: true }); } catch(_){}
      // Remount Swagger so param/body examples come from the set (not stale official defaults)
      await renderSpecDetail();
    };
  }
  if(newBtn){
    newBtn.onclick = async ()=>{
      const label = prompt("Label for new service payload set version:", "v"+((specsPayloadSetVersion||0)+1));
      if(label == null) return;
      try {
        const created = await fetchJson("/api/payload-sets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            service: service,
            label: label || null,
            clone_from: specsPayloadSetVersion,
            make_active: true
          })
        });
        specsPayloadSetVersion = created.version;
        persistPayloadSetVersion(service, created.version);
        await loadServicePayloadSets(service, true);
        applyPayloadSetToActive(specsPayloadSetDetail);
        await renderSpecDetail();
      } catch(e){
        alert("Create set failed: "+e.message);
      }
    };
  }
}

function workingRequestForOp(op, doc){
  const apiId = primaryApiId(op);
  const apis = (specsPayloadSetDetail && specsPayloadSetDetail.apis) || {};
  let setEntry = apis[apiId];
  if(!setEntry){
    const ids = opApiIds(op.method, op.path, op.operationId);
    for(let i=0;i<ids.length;i++){
      if(apis[ids[i]]){ setEntry = apis[ids[i]]; break; }
    }
  }
  if(!setEntry){
    const hit = findActivePayload(op.method, op.path, op.operationId);
    if(hit && hit.payload){
      const a = hit.payload;
      return {
        apiId: hit.apiId || apiId,
        method: a.method || op.method,
        path: a.path || op.path,
        query: a.query || {},
        pathParams: a.pathParams || {},
        body: a.body,
        name: a.name || "working",
        version: null,
        set_version: a.set_version != null ? a.set_version : specsPayloadSetVersion
      };
    }
  }
  if(setEntry && setEntry.request){
    const req = setEntry.request || {};
    let body = req.body;
    if(typeof body === "string"){ try { body = JSON.parse(body); } catch(_){} }
    return {
      apiId: apiId,
      method: req.method || op.method,
      path: req.path || op.path,
      query: req.query || {},
      pathParams: req.path_params || req.pathParams || {},
      body: body,
      name: setEntry.name || "working",
      version: null,
      set_version: specsPayloadSetVersion
    };
  }
  const active = specsActivePayloads[apiId];
  if(active && (active.body != null || active.query || active.pathParams)){
    return Object.assign(defaultWorkingRequest(op, doc), active, { apiId: apiId });
  }
  // Prefer latest saved payload for this api
  const saved = payloadsForApi(apiId)[0];
  if(saved){
    const cat = (specsPayloadCatalog||[]).find(p=>p.apiId===apiId && p.name===saved.name);
    if(cat){
      return {
        apiId: apiId,
        method: cat.method || op.method,
        path: cat.path || op.path,
        query: cat.query || {},
        pathParams: cat.pathParams || {},
        body: cat.body,
        name: cat.name || "working",
        version: cat.version
      };
    }
  }
  return Object.assign(defaultWorkingRequest(op, doc), { apiId: apiId });
}

function setActivePayload(apiId, payload){
  if(!apiId || !payload) return;
  specsActivePayloads[apiId] = {
    name: payload.name || "working",
    version: payload.version != null ? payload.version : null,
    method: payload.method || null,
    path: payload.path || null,
    body: payload.body,
    query: payload.query || {},
    pathParams: payload.pathParams || {}
  };
  persistActivePayloads(selectedSpecService);
}

function activeEntryForOpMeta(opMeta){
  if(!opMeta) return null;
  const hit = findActivePayload(opMeta.method, opMeta.path, opMeta.operationId);
  if(!hit) return null;
  const a = hit.payload;
  if(!(a.body != null || (a.query && Object.keys(a.query).length) || (a.pathParams && Object.keys(a.pathParams).length))){
    return null;
  }
  return {
    key: "spt-active|"+hit.apiId,
    name: a.name || "working",
    label: "Active: "+(a.name||"working")+
      (a.set_version!=null?" set v"+a.set_version:(a.version!=null?" v"+a.version:"")),
    apiId: hit.apiId,
    body: a.body,
    query: a.query || {},
    pathParams: a.pathParams || {},
    version: a.version,
    set_version: a.set_version
  };
}

async function hydrateActivePayloadBodies(service){
  const ids = Object.keys(specsActivePayloads||{});
  await Promise.all(ids.map(async apiId=>{
    const a = specsActivePayloads[apiId];
    if(!a || a.body != null || !a.name) return;
    try {
      const full = await fetchJson(
        "/api/payloads/"+encodeURIComponent(service)+"/"+encodeURIComponent(apiId)+"/"+
        encodeURIComponent(a.name)+(a.version!=null?("?version="+encodeURIComponent(a.version)):"")
      );
      const req = full.request || {};
      let body = req.body;
      if(typeof body === "string"){
        try { body = JSON.parse(body); } catch(_){}
      }
      a.body = body;
      a.query = req.query || a.query || {};
      a.pathParams = req.path_params || req.pathParams || a.pathParams || {};
      a.method = (req.method || a.method || "").toLowerCase();
      a.path = req.path || a.path || "";
      if(full.version != null) a.version = full.version;
    } catch(_){}
  }));
  persistActivePayloads(service);
}

/** Fill parameter/body examples so Swagger Try it out is ready immediately. */
function enrichOpenApiForTryIt(doc, payloadCatalog){
  if(!doc || typeof doc !== "object") return doc;
  const components = doc.components || (doc.components = {});
  const schemes = components.securitySchemes || (components.securitySchemes = {});
  const hasBearer = Object.keys(schemes).some(n=>{
    const s = schemes[n] || {};
    return s.type === "http" && String(s.scheme||"").toLowerCase() === "bearer";
  });
  if(!hasBearer){
    schemes.bearerAuth = { type: "http", scheme: "bearer", bearerFormat: "JWT", description: "SPT platform try-token (auto-filled)" };
  }
  if(!doc.security || !doc.security.length){
    const bearerName = Object.keys(schemes).find(n=>{
      const s = schemes[n] || {};
      return s.type === "http" && String(s.scheme||"").toLowerCase() === "bearer";
    }) || "bearerAuth";
    doc.security = [{ [bearerName]: [] }];
  }
  const byApi = {};
  (payloadCatalog||[]).forEach(p=>{
    if(!p || !p.apiId) return;
    (byApi[p.apiId] || (byApi[p.apiId]=[])).push(p);
  });
  const paths = doc.paths || {};
  Object.keys(paths).forEach(path=>{
    const item = paths[path];
    if(!item || typeof item !== "object") return;
    ["get","post","put","patch","delete","head","options"].forEach(method=>{
      const op = item[method];
      if(!op || typeof op !== "object") return;
      const apiIds = opApiIds(method, path, op.operationId);
      const activeHit = findActivePayload(method, path, op.operationId);
      const active = activeHit && activeHit.payload;
      const params = [].concat(item.parameters||[], op.parameters||[]);
      params.forEach(p=>{
        if(!p || typeof p !== "object" || !p.name) return;
        // Service-set values win over official / generated defaults
        let fromActive = null;
        if(active){
          if(p.in === "query" && active.query && active.query[p.name] != null) fromActive = active.query[p.name];
          else if(p.in === "path" && active.pathParams && active.pathParams[p.name] != null) fromActive = active.pathParams[p.name];
          else if(p.in === "header" && active.headers && active.headers[p.name] != null) fromActive = active.headers[p.name];
        }
        if(fromActive != null){
          p.example = fromActive;
          if(p.schema && typeof p.schema === "object") p.schema.example = fromActive;
          return;
        }
        if(p.example != null || (p.schema && p.schema.example != null)) return;
        const ex = exampleFromParam(p);
        if(ex != null){
          p.example = ex;
          if(p.schema && typeof p.schema === "object" && p.schema.example == null) p.schema.example = ex;
        }
      });
      const rb = op.requestBody;
      if(rb && rb.content){
        const saved = [];
        apiIds.forEach(id=>{ (byApi[id]||[]).forEach(p=> saved.push(p)); });
        Object.keys(rb.content).forEach(ct=>{
          const media = rb.content[ct];
          if(!media || typeof media !== "object") return;
          const examples = (media.examples && typeof media.examples === "object")
            ? Object.assign({}, media.examples)
            : {};
          if(media.example != null && !examples.official){
            examples.official = { summary: "Official (from OpenAPI)", value: media.example };
          }
          const generated = exampleFromSchema(media.schema, components, 0);
          if(generated != null && !examples["spt-generated"]){
            examples["spt-generated"] = { summary: "SPT generated", value: generated };
          }
          saved.forEach(p=>{
            if(p.body == null) return;
            const key = "spt:"+p.name;
            if(examples[key]) return;
            examples[key] = {
              summary: "SPT saved: "+p.name+(p.version!=null?" v"+p.version:""),
              value: p.body
            };
          });
          // Active set / Overview payload → default Try-it-out body
          let activeBody = null;
          if(active && active.body != null){
            activeBody = active.body;
            examples["spt-active"] = {
              summary: "Active: "+(active.name||"working")+
                (active.set_version!=null?" set v"+active.set_version:""),
              value: activeBody
            };
          }
          if(Object.keys(examples).length){
            media.examples = examples;
            if(activeBody != null) media.example = activeBody;
            else if(examples.official) media.example = examples.official.value;
            else if(examples["spt-generated"]) media.example = examples["spt-generated"].value;
            else {
              const first = examples[Object.keys(examples)[0]];
              if(first) media.example = first.value;
            }
          } else if(media.example == null && generated != null){
            media.example = generated;
          }
        });
      }
    });
  });
  return doc;
}

function exampleFromParam(p){
  const schema = p.schema || {};
  if(schema.example != null) return schema.example;
  if(schema.default != null) return schema.default;
  if(Array.isArray(schema.enum) && schema.enum.length) return schema.enum[0];
  const name = String(p.name||"").toLowerCase();
  if(name === "timeframe" || name === "time_frame") return "1M";
  if(name === "page" || name === "offset") return 0;
  if(name === "size" || name === "limit") return 10;
  if(name === "symbol" || name === "ticker") return "AAPL";
  // Leave path ids blank so user pastes real values (not fake "1"/"example")
  if(name === "type") return "";
  if(name === "id" || name.endsWith("_id") || name.endsWith("id")) return "";
  if(schema.type === "integer" || schema.type === "number") return 1;
  if(schema.type === "boolean") return true;
  if(schema.type === "array") return [exampleFromSchema(schema.items||{type:"string"}, {}, 0)];
  if(p.in === "path") return "";
  return schema.type === "string" ? "" : null;
}

function paramValueHints(p){
  const name = String(p.name||"").toLowerCase();
  const schema = p.schema || {};
  if(Array.isArray(schema.enum) && schema.enum.length) return schema.enum.map(String);
  if(name === "timeframe" || name === "time_frame") return ["1D","1W","1M","3M","6M","1Y","YTD","ALL"];
  if(name === "type") return ["portfolio","account","strategy","watchlist"];
  return [];
}

function resolveParamValue(p, wr){
  const name = p.name || "";
  if(p.in === "path" && wr.pathParams && wr.pathParams[name] != null && wr.pathParams[name] !== "") return String(wr.pathParams[name]);
  if(p.in === "query" && wr.query && wr.query[name] != null && wr.query[name] !== "") return String(wr.query[name]);
  const ex = exampleFromParam(p);
  return ex == null ? "" : String(ex);
}

function buildResolvedPath(template, pathParams){
  let out = String(template || "/");
  const params = pathParams || {};
  Object.keys(params).forEach(k=>{
    out = out.replace(new RegExp("\\{"+k+"\\}","g"), encodeURIComponent(String(params[k])));
  });
  return out;
}

function suggestedWorkingOps(ops){
  const prefer = [
    "/v1/analysis/dashboard/summary",
    "/v1/analysis/dashboard/performance",
    "/v1/analysis/dashboard/top-movers",
    "/v1/analysis/dashboard/recent-activity"
  ];
  const out = [];
  prefer.forEach(path=>{
    const hit = (ops||[]).find(o=>String(o.path)===path && String(o.method).toUpperCase()==="GET");
    if(hit) out.push(hit);
  });
  return out;
}

function exampleFromSchema(schema, components, depth){
  if(!schema || typeof schema !== "object" || depth > 4) return null;
  if(schema.example != null) return schema.example;
  if(schema.default != null) return schema.default;
  if(schema.$ref){
    const ref = String(schema.$ref);
    const name = ref.split("/").pop();
    const resolved = ((components||{}).schemas||{})[name];
    return exampleFromSchema(resolved, components, depth+1);
  }
  if(Array.isArray(schema.enum) && schema.enum.length) return schema.enum[0];
  if(schema.type === "object" || schema.properties){
    const out = {};
    const props = schema.properties || {};
    Object.keys(props).slice(0, 12).forEach(k=>{
      const v = exampleFromSchema(props[k], components, depth+1);
      if(v != null) out[k] = v;
    });
    return out;
  }
  if(schema.type === "array"){
    const item = exampleFromSchema(schema.items||{type:"string"}, components, depth+1);
    return item != null ? [item] : [];
  }
  if(schema.type === "integer" || schema.type === "number") return 1;
  if(schema.type === "boolean") return true;
  if(schema.type === "string"){
    if(schema.format === "date") return "2026-01-01";
    if(schema.format === "date-time") return "2026-01-01T00:00:00Z";
    if(schema.format === "uuid") return "00000000-0000-0000-0000-000000000001";
    return "example";
  }
  return null;
}

async function loadServicePayloadCatalog(service){
  if(!service) return [];
  if(specsPayloadService === service && specsPayloadCatalog.length){
    await hydrateActivePayloadBodies(service);
    return specsPayloadCatalog;
  }
  try {
    const data = await fetchJson("/api/payloads?service="+encodeURIComponent(service));
    specsPayloadIndex = data.payloads || [];
  } catch(_){
    specsPayloadIndex = [];
  }
  // Latest version per api_id+name; fetch body in parallel (cap)
  const latest = {};
  specsPayloadIndex.forEach(row=>{
    const k = (row.api_id||"")+"|"+(row.name||"default");
    const prev = latest[k];
    if(!prev || Number(row.version||0) > Number(prev.version||0)) latest[k] = row;
  });
  const rows = Object.values(latest).slice(0, 40);
  const catalog = [];
  await Promise.all(rows.map(async row=>{
    try {
      const full = await fetchJson(
        "/api/payloads/"+encodeURIComponent(row.service)+"/"+encodeURIComponent(row.api_id)+"/"+
        encodeURIComponent(row.name)+(row.version!=null?("?version="+encodeURIComponent(row.version)):"")
      );
      const req = full.request || {};
      let body = req.body;
      if(typeof body === "string"){
        try { body = JSON.parse(body); } catch(_){}
      }
      catalog.push({
        key: "spt:"+row.name+"|"+row.api_id,
        name: row.name || "default",
        version: row.version,
        apiId: row.api_id,
        method: (req.method || row.method || "").toLowerCase(),
        path: req.path || row.path || "",
        body: body,
        query: req.query || {},
        pathParams: req.path_params || req.pathParams || {},
        label: "SPT: "+(row.name||"default")+(row.version!=null?" v"+row.version:"")+" ("+row.api_id+")"
      });
    } catch(_){}
  }));
  // Built-in synthetic options (always available)
  const builtins = [
    { key: "official", name: "official", label: "Official (OpenAPI)", body: null, apiId: "*" },
    { key: "spt-generated", name: "spt-generated", label: "SPT generated", body: null, apiId: "*" }
  ];
  specsPayloadCatalog = builtins.concat(catalog);
  specsPayloadService = service;
  specsPayloadCursor = 0;
  await hydrateActivePayloadBodies(service);
  return specsPayloadCatalog;
}

function fillPayloadSelect(catalog){
  const sel = document.getElementById("oas-payload-select");
  if(!sel) return;
  // Deduplicate active aliases (same method/path indexed under many apiIds)
  const seen = {};
  const activeOpts = [];
  Object.keys(specsActivePayloads||{}).forEach(apiId=>{
    const a = specsActivePayloads[apiId];
    if(!a) return;
    const dedupe = String(a.method||"").toLowerCase()+"|"+normalizeOpPath(a.path)+"|"+(a.name||"working");
    if(seen[dedupe]) return;
    seen[dedupe] = true;
    const setLabel = a.set_version != null ? " set v"+a.set_version : (a.version!=null?" v"+a.version:"");
    activeOpts.push({
      key: "spt-active|"+apiId,
      label: "★ "+(a.name||"working")+setLabel+" · "+apiId,
      apiId: apiId,
      name: a.name,
      body: a.body,
      query: a.query,
      pathParams: a.pathParams,
      version: a.version,
      set_version: a.set_version
    });
  });
  const extras = (catalog||[]).filter(p=>{
    if(!p || !p.apiId) return false;
    if(String(p.key||"").indexOf("spt-set:")===0) return false; // already covered by active
    if(String(p.key||"").indexOf("spt-active|")===0) return false;
    const dedupe = String(p.method||"").toLowerCase()+"|"+normalizeOpPath(p.path)+"|"+(p.name||"");
    if(seen[dedupe]) return false;
    return true;
  });
  const merged = activeOpts.concat(extras);
  const opts = merged.map(p=>'<option value="'+esc(p.key)+'">'+esc(p.label||p.key)+'</option>');
  sel.innerHTML = opts.join("") || '<option value="">No set payloads — Load a set above</option>';
  specsPayloadCatalog = merged;
  if(activeOpts.length) sel.value = activeOpts[0].key;
  else if(merged[0]) sel.value = merged[0].key;
}
