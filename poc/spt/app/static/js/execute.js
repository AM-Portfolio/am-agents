function card(l,v){ return '<div class="card"><label>'+esc(l)+'</label><div class="v">'+esc(v)+'</div></div>'; }
function cardHtml(l,v){ return '<div class="card"><label>'+esc(l)+'</label><div class="v">'+v+'</div></div>'; }

let openApiVersionCache = {}; // service -> versions payload
let selectedRunOpenApiEnv = null; // env chosen in header version select
let selectedRunOpenApiVersion = null; // info.version string

function updateStopButton(running){
  const btn = document.getElementById("btn-stop-run");
  if(btn) btn.style.display = running ? "inline-block" : "none";
}

async function loadOpenApiVersions(service){
  if(!service) return [];
  if(openApiVersionCache[service]) return openApiVersionCache[service];
  try {
    const data = await fetchJson("/api/catalog/"+encodeURIComponent(service)+"/openapi/versions");
    openApiVersionCache[service] = data.environments || [];
  } catch(_){
    openApiVersionCache[service] = [];
  }
  return openApiVersionCache[service];
}

function parseVersionOptionValue(val){
  // value format: environment|version
  if(!val) return { environment: null, version: null };
  const i = String(val).indexOf("|");
  if(i < 0) return { environment: val, version: null };
  return { environment: val.slice(0,i), version: val.slice(i+1) || null };
}

async function refreshRunOpenApiVersionSelect(preferredEnv, preferredVersion){
  const sel = document.getElementById("run-openapi-version");
  if(!sel) return;
  const cfgId = document.getElementById("run-config")?.value;
  let service = "am-analysis";
  let environment = preferredEnv || selectedRunOpenApiEnv || "dev";
  let openapiVersion = preferredVersion || selectedRunOpenApiVersion || null;
  if(cfgId){
    const c = configs.find(x=>x.id===cfgId) || (await fetchJson("/api/configs/"+cfgId));
    service = c.service || service;
    environment = preferredEnv || c.environment || environment;
    openapiVersion = preferredVersion != null ? preferredVersion : (c.openapi_version || openapiVersion);
  }
  const versions = await loadOpenApiVersions(service);
  const opts = ['<option value="">API version (auto - '+esc(environment)+')</option>'];
  versions.forEach(v=>{
    const value = (v.environment||"")+"|"+(v.version||"unknown");
    const label = v.label || (v.ok ? (v.environment+" - "+(v.version||"?")) : (v.environment+" - fail"));
    const disabled = v.ok ? "" : " disabled";
    const selected = (v.environment===environment && (!openapiVersion || String(v.version)===String(openapiVersion))) ? " selected" : "";
    opts.push('<option value="'+esc(value)+'"'+disabled+selected+'>'+esc(label)+'</option>');
  });
  sel.innerHTML = opts.join("");
  // If preferred matched a disabled option, keep auto
  if(sel.selectedIndex < 0) sel.value = "";
  const cur = parseVersionOptionValue(sel.value);
  selectedRunOpenApiEnv = cur.environment || environment;
  selectedRunOpenApiVersion = cur.version && cur.version !== "unknown" ? cur.version : openapiVersion;
  syncSidebarApiVersionSelect(sel.value);
}

function syncSidebarApiVersionSelect(value){
  const side = document.getElementById("f-api-version");
  const head = document.getElementById("run-openapi-version");
  if(!side || !head) return;
  // Mirror header options into sidebar (aligned with other filters)
  if(side.innerHTML !== head.innerHTML){
    const prev = value != null ? value : side.value;
    side.innerHTML = head.innerHTML;
    if(prev && [].some.call(side.options, o=>o.value===prev)) side.value = prev;
    else if(value != null) side.value = value;
  } else if(value != null){
    side.value = value;
  }
}

async function onRunOpenApiVersionChange(){
  const sel = document.getElementById("run-openapi-version");
  const parsed = parseVersionOptionValue(sel && sel.value);
  selectedRunOpenApiEnv = parsed.environment;
  selectedRunOpenApiVersion = parsed.version && parsed.version !== "unknown" ? parsed.version : null;
  syncSidebarApiVersionSelect(sel && sel.value);
  // Changing version changes which OpenAPI catalog feeds API picker
  selectedApiIds = null;
  serviceApisCache = {};
  const btn = document.getElementById("btn-api-picker");
  if(btn) btn.textContent = "APIs (all)";
  const picker = document.getElementById("api-picker");
  if(picker && picker.style.display !== "none"){
    await toggleApiPicker(true);
  }
}

function applyOpenApiVersionToBody(body){
  const sel = document.getElementById("run-openapi-version");
  const parsed = parseVersionOptionValue(sel && sel.value);
  if(parsed.environment) body.environment = parsed.environment;
  if(parsed.version && parsed.version !== "unknown") body.openapi_version = parsed.version;
  else if(selectedRunOpenApiVersion) body.openapi_version = selectedRunOpenApiVersion;
  return body;
}

async function stopSelectedRun(runId){
  const id = runId || selectedRunId;
  if(!id) return alert("No running test selected");
  if(!confirm("Stop this load test?")) return;
  try {
    await fetchJson("/api/runs/"+id+"/stop", {method:"POST"});
    stopRunWatch();
    updateStopButton(false);
    await refreshRuns({resetPage: true});
    await selectRun(id);
  } catch(e){
    alert("Stop failed: "+e.message);
  }
}

function readSelectedApiIds(){
  if(selectedApiIds == null) return null;
  return selectedApiIds.length ? selectedApiIds.slice() : null;
}

function applyApiIdsToBody(body){
  const ids = readSelectedApiIds();
  if(ids && ids.length) body.api_ids = ids;
  return body;
}

async function loadServiceApisForConfig(){
  const cfgId = document.getElementById("run-config")?.value;
  let service = null;
  let environment = null;
  if(cfgId){
    const c = configs.find(x=>x.id===cfgId) || (await fetchJson("/api/configs/"+cfgId));
    service = c.service;
    environment = c.environment;
  }
  const envEl = document.getElementById("cfg-env");
  if(envEl && envEl.value) environment = envEl.value;
  const svcEl = document.getElementById("cfg-service");
  if(svcEl && svcEl.value) service = svcEl.value;
  // Header API-version select wins for the next run / API picker
  const verSel = document.getElementById("run-openapi-version");
  const parsed = parseVersionOptionValue(verSel && verSel.value);
  if(parsed.environment) environment = parsed.environment;
  else if(selectedRunOpenApiEnv) environment = selectedRunOpenApiEnv;
  if(!service && configs[0]) service = configs[0].service;
  if(!service) service = "am-analysis";
  if(!environment) environment = "dev";
  const cacheKey = service + "|" + environment;
  if(!serviceApisCache[cacheKey]){
    const data = await fetchJson("/api/catalog/"+encodeURIComponent(service)+"/apis?environment="+encodeURIComponent(environment));
    serviceApisCache[cacheKey] = data;
  }
  const data = serviceApisCache[cacheKey];
  return {
    service,
    environment,
    apis: data.apis || [],
    target_url: data.target_url,
    runtime: data.runtime,
    source: data.source,
    openapi_version: data.openapi_version || selectedRunOpenApiVersion
  };
}

function renderApiPicker(service, apis, meta){
  const el = document.getElementById("api-picker");
  if(!el) return;
  meta = meta || {};
  const allIds = apis.map(a=>String(a.id)).filter(Boolean);
  if(selectedApiIds == null) selectedApiIds = allIds.slice();
  const checked = new Set(selectedApiIds);
  const n = checked.size;
  const ver = meta.openapi_version || selectedRunOpenApiVersion || "—";
  const env = meta.environment || selectedRunOpenApiEnv || "—";
  el.innerHTML =
    '<div class="picker-h">'+
      '<strong>APIs for next run</strong> <span class="sub">'+esc(service)+' · env '+esc(env)+' · API '+esc(ver)+' · '+esc(n)+' / '+esc(allIds.length)+' selected</span>'+
      '<button type="button" class="secondary" onclick="apiPickerSelectAll()">Select all</button>'+
      '<button type="button" class="secondary" onclick="apiPickerClear()">Clear</button>'+
      '<button type="button" class="secondary" onclick="toggleApiPicker(false)">Close</button>'+
    '</div>'+
    '<div class="picker-list">'+
      apis.map(a=>{
        const id = String(a.id||"");
        const on = checked.has(id);
        return '<label><input type="checkbox" data-api-pick="'+esc(id)+'"'+(on?" checked":"")+' onchange="onApiPickChange()"/>'+
          '<span><span class="pm-method '+esc((a.method||"GET").toUpperCase())+'">'+esc((a.method||"GET").toUpperCase())+'</span> '+
          esc(a.name||a.path||id)+'<span class="sub">'+esc(a.path||id)+'</span></span></label>';
      }).join("")+
    '</div>';
}

function onApiPickChange(){
  const boxes = document.querySelectorAll("#api-picker [data-api-pick]");
  if(boxes.length){
    selectedApiIds = Array.from(boxes).filter(b=>b.checked).map(b=>b.getAttribute("data-api-pick"));
  }
  const btn = document.getElementById("btn-api-picker");
  if(btn){
    if(selectedApiIds == null) btn.textContent = "APIs (all)";
    else btn.textContent = "APIs ("+selectedApiIds.length+")";
  }
}

async function apiPickerSelectAll(){
  const meta = await loadServiceApisForConfig();
  selectedApiIds = meta.apis.map(a=>String(a.id)).filter(Boolean);
  renderApiPicker(meta.service, meta.apis, meta);
  onApiPickChange();
}

async function apiPickerClear(){
  selectedApiIds = [];
  const meta = await loadServiceApisForConfig();
  renderApiPicker(meta.service, meta.apis, meta);
  onApiPickChange();
}

async function toggleApiPicker(force){
  const el = document.getElementById("api-picker");
  if(!el) return;
  const open = force === false ? false : (force === true ? true : el.style.display === "none");
  if(!open){ el.style.display = "none"; return; }
  try {
    const meta = await loadServiceApisForConfig();
    renderApiPicker(meta.service, meta.apis, meta);
    el.style.display = "block";
    onApiPickChange();
  } catch(e){
    alert("Could not load APIs: "+e.message);
  }
}

function syncPayloadEditor(){
  const ed = document.getElementById("payload-editor");
  if(!ed) return;
  ed.value = JSON.stringify(editPayloads.bench_run||{vus:1,duration:"1s",iterations:1}, null, 2);
}

function syncPayloadEdit(){
  const ed = document.getElementById("payload-editor");
  if(!ed) return;
  try { editPayloads.bench_run = JSON.parse(ed.value); } catch(e){}
}

async function rerunRun(runId){
  const r = await fetchJson("/api/runs/"+runId);
  const preset = document.getElementById("run-preset")?.value || "";
  if(r.config_id){ await executeConfig(r.config_id, preset); return; }
  await runWithEdited(runId);
}

async function saveFromRun(runId){
  const name = prompt("Config name:", "from-run-"+runId.slice(0,8));
  if(!name) return;
  await fetch(api("/api/runs/"+runId+"/save-config?name="+encodeURIComponent(name)), {method:"POST"});
  await refreshConfigs();
  setMode("configs");
}

async function executeSelected(){
  const id = document.getElementById("run-config").value;
  const preset = document.getElementById("run-preset").value;
  if(!id) return alert("Pick a config");
  await executeConfig(id, preset);
}

function onPresetChange(){
  const p = document.getElementById("run-preset").value;
  const vusEl = document.getElementById("run-vus");
  const callsEl = document.getElementById("run-calls");
  const profEl = document.getElementById("run-profile");
  if(!vusEl || !callsEl) return;
  if(p === "20u-50"){ vusEl.value = 20; callsEl.value = 50; if(profEl) profEl.value = "load"; }
  else if(p === "smoke"){ vusEl.value = 3; callsEl.value = ""; }
  else if(p === "load"){ vusEl.value = 10; callsEl.value = ""; if(profEl) profEl.value = "load"; }
  else if(p === "stress"){ vusEl.value = 25; callsEl.value = ""; if(profEl) profEl.value = "load"; }
}

function onProfileChange(){
  const prof = document.getElementById("run-profile")?.value;
  if(prof !== "debug") return;
  const vus = parseInt(document.getElementById("run-vus")?.value, 10);
  const calls = parseInt(document.getElementById("run-calls")?.value, 10);
  if((Number.isFinite(vus) && vus > 1) || (Number.isFinite(calls) && calls > 1)){
    // debug always runs 1×1 — clear multi-load inputs so UI matches actual run
    const vusEl = document.getElementById("run-vus");
    const callsEl = document.getElementById("run-calls");
    const presetEl = document.getElementById("run-preset");
    if(vusEl) vusEl.value = 1;
    if(callsEl) callsEl.value = 1;
    if(presetEl) presetEl.value = "";
  }
}

function readLoadOverrides(){
  const out = {};
  const vus = parseInt(document.getElementById("run-vus")?.value, 10);
  const calls = parseInt(document.getElementById("run-calls")?.value, 10);
  if(Number.isFinite(vus) && vus > 0) out.vus = vus;
  if(Number.isFinite(calls) && calls > 0) out.iterations = calls;
  return out;
}

function toggleSidebar(){
  document.body.classList.toggle("sidebar-collapsed");
  const collapsed = document.body.classList.contains("sidebar-collapsed");
  localStorage.setItem("spt_sidebar_collapsed", collapsed ? "1" : "0");
  const btn = document.getElementById("btn-toggle-sidebar");
  if(btn) btn.textContent = collapsed ? "Show list" : "Hide list";
}

async function executeConfig(configId, preset){
  document.getElementById("main").innerHTML = '<div class="empty">Starting run…</div>';
  const overrides = readLoadOverrides();
  const body = {config_id: configId, triggered_by: "manual", wait: false, ...overrides};
  if(preset) body.preset = preset;
  let prof = document.getElementById("run-profile")?.value || "load";
  // Never send debug with 20/50 — backend would otherwise force 1×1
  if(preset === "20u-50" || (overrides.vus && overrides.vus > 1) || (overrides.iterations && overrides.iterations > 1)){
    prof = "load";
    const profEl = document.getElementById("run-profile");
    if(profEl) profEl.value = "load";
  }
  body.profile = prof;
  if(body.iterations) delete body.duration;
  applyApiIdsToBody(body);
  applyOpenApiVersionToBody(body);
  if(body.api_ids && !body.api_ids.length){
    alert("Select at least one API (APIs button), or Select all");
    return;
  }
  if(typeof collectPayloadSetVersionForRun === "function"){
    const setVer = collectPayloadSetVersionForRun();
    if(setVer != null) body.payload_set_version = setVer;
  }
  if(typeof collectPayloadRefsForRun === "function"){
    const refs = collectPayloadRefsForRun();
    if(refs && refs.length) body.payload_refs = refs;
  }
  const res = await fetchJson("/api/runs/execute", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
  updateStopButton(true);
  await refreshRuns({resetPage: true});
  setMode("runs");
  await selectRun(res.id);
}

async function runDebug(runId){
  const r = await fetchJson("/api/runs/"+runId);
  document.getElementById("main").innerHTML = '<div class="empty">Starting debug run…</div>';
  const body = {
    config: {
      name: r.config_name,
      service: r.service,
      environment: r.environment,
      openapi_version: r.openapi_version || null,
      test_type: r.test_type,
      target_url: r.target_url,
      run_profile: "debug",
      payloads: r.payloads_used || {},
      scripts: (r.config_snapshot||{}).scripts || {}
    },
    profile: "debug",
    wait: false,
    triggered_by: "manual"
  };
  applyApiIdsToBody(body);
  applyOpenApiVersionToBody(body);
  applyOpenApiVersionToBody(body);
  const res = await fetchJson("/api/runs/execute", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
  updateStopButton(true);
  await refreshRuns({resetPage: true});
  await selectRun(res.id);
}

async function runWithEdited(runId){
  syncPayloadEdit();
  const r = await fetchJson("/api/runs/"+runId);
  document.getElementById("main").innerHTML = '<div class="empty">Starting run…</div>';
  const body = {
    config: {
      name: r.config_name,
      service: r.service,
      environment: r.environment,
      openapi_version: r.openapi_version || null,
      test_type: r.test_type,
      target_url: r.target_url,
      payloads: editPayloads,
      scripts: (r.config_snapshot||{}).scripts || {}
    },
    wait: false,
    triggered_by: "manual"
  };
  applyApiIdsToBody(body);
  applyOpenApiVersionToBody(body);
  const res = await fetchJson("/api/runs/execute", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
  updateStopButton(true);
  await refreshRuns({resetPage: true});
  await selectRun(res.id);
}

async function selectConfig(id, opts){
  opts = opts || {};
  selectedConfigId=id; selectedRunId=null; renderList();
  const c = await fetchJson("/api/configs/"+id);
  editPayloads = JSON.parse(JSON.stringify(c.payloads||{}));
  document.getElementById("main").innerHTML =
    '<h2>Config: '+esc(c.name)+'</h2>'+
    '<div class="toolbar"><button onclick="saveConfig(\''+c.id+'\')">Save</button><button class="secondary" onclick="executeConfig(\''+c.id+'\')">Run</button></div>'+
    '<div class="section"><div class="section-b">'+
      row("Name", '<input id="cfg-name" value="'+esc(c.name)+'" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem"/>')+
      row("Service", selService(c.service))+
      row("Environment", selEnv(c.environment))+
      row("API version", '<select id="cfg-openapi-version" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem"><option value="">Loading…</option></select><p class="sub">OpenAPI info.version used to discover APIs for load tests (tied to environment).</p>')+
      row("Target URL", '<input id="cfg-target" value="'+esc(c.target_url||"")+'" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem"/><p class="sub" id="cfg-target-hint">Auto from service targets[env]; edit only to override.</p>')+
    '</div></div>'+
    '<div class="section"><div class="section-h">Load settings</div><div class="section-b">'+
      '<label class="sub">bench (VUs / duration)</label><textarea class="code" id="cfg-bench">'+esc(JSON.stringify((c.payloads||{}).bench_run||{vus:1,duration:"30s"},null,2))+'</textarea>'+
      '<p class="sub">APIs are discovered from the selected OpenAPI version. Auth is owned by SPT.</p>'+
    '</div></div>';
  const svc = document.getElementById("cfg-service");
  const env = document.getElementById("cfg-env");
  if(svc) svc.addEventListener("change", onConfigServiceEnvChange);
  if(env) env.addEventListener("change", onConfigServiceEnvChange);
  await fillConfigOpenApiVersions(c.service, c.environment, c.openapi_version);
  await refreshRunOpenApiVersionSelect(c.environment, c.openapi_version);
  if(!opts.skipUrl) syncPortalUrl({ replace: !!opts.replaceUrl });
}

async function fillConfigOpenApiVersions(service, environment, selectedVersion){
  const sel = document.getElementById("cfg-openapi-version");
  if(!sel) return;
  const versions = await loadOpenApiVersions(service);
  const opts = ['<option value="">auto (from env OpenAPI)</option>'];
  versions.forEach(v=>{
    if(v.environment !== environment) return;
    const ver = v.version || "";
    const label = v.ok ? ((ver||"unknown")+" · "+(v.operation_count||0)+" ops") : "unreachable";
    const selected = (selectedVersion && String(selectedVersion)===String(ver)) ? " selected" : (!selectedVersion && v.ok ? " selected" : "");
    opts.push('<option value="'+esc(ver)+'"'+(v.ok?"":" disabled")+selected+'>'+esc(label)+'</option>');
  });
  // Also list other envs as hints (switching env is separate)
  versions.filter(v=>v.environment!==environment).forEach(v=>{
    opts.push('<option value="" disabled>'+esc((v.label||v.environment)+" (switch Environment)")+'</option>');
  });
  sel.innerHTML = opts.join("");
  sel.onchange = ()=>{
    selectedRunOpenApiVersion = sel.value || null;
    refreshRunOpenApiVersionSelect(environment, sel.value || null);
  };
}

async function onConfigServiceEnvChange(){
  const service = document.getElementById("cfg-service")?.value;
  const environment = document.getElementById("cfg-env")?.value || "dev";
  if(!service) return;
  delete openApiVersionCache[service];
  try {
    const data = await fetchJson("/api/catalog/"+encodeURIComponent(service)+"/apis?environment="+encodeURIComponent(environment));
    serviceApisCache[service + "|" + environment] = data;
    const target = document.getElementById("cfg-target");
    if(target && data.target_url) target.value = data.target_url;
    const hint = document.getElementById("cfg-target-hint");
    if(hint){
      hint.textContent = (data.runtime ? ("runtime="+data.runtime+" · ") : "") +
        (data.source || "catalog") +
        (data.openapi_version ? (" · API "+data.openapi_version) : "") +
        (data.openapi_url ? (" · " + data.openapi_url) : "");
    }
    await fillConfigOpenApiVersions(service, environment, data.openapi_version || null);
    await refreshRunOpenApiVersionSelect(environment, data.openapi_version || null);
  } catch(e){
    console.warn("target refresh failed", e);
  }
}

function row(l, html){ return '<div style="margin-bottom:.5rem"><label style="font-size:.72rem;color:var(--muted)">'+l+'</label><div>'+html+'</div></div>'; }
function selService(v){
  return '<select id="cfg-service" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem">'+
    (catalog.services||[]).map(s=>'<option value="'+esc(s.id)+'"'+(s.id===v?" selected":"")+'>'+esc(s.label)+'</option>').join("")+'</select>';
}
function selEnv(v){
  return '<select id="cfg-env" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem">'+
    (catalog.environments||[]).map(e=>'<option'+(e===v?" selected":"")+'>'+esc(e)+'</option>').join("")+'</select>';
}

async function saveConfig(id){
  const body = {
    name: document.getElementById("cfg-name").value,
    service: document.getElementById("cfg-service").value,
    environment: document.getElementById("cfg-env").value,
    openapi_version: document.getElementById("cfg-openapi-version")?.value || null,
    target_url: document.getElementById("cfg-target").value,
    payloads: {
      bench_run: JSON.parse(document.getElementById("cfg-bench").value)
    }
  };
  await fetchJson("/api/configs/"+id, {method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
  await refreshConfigs();
  selectConfig(id);
}

function newConfig(){
  setMode("configs");
  document.getElementById("main").innerHTML = '<div class="empty">Creating…</div>';
  fetchJson("/api/configs/default").then(async c=>{
    c.name = "new-load-test";
    const saved = await fetchJson("/api/configs", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(c)});
    await refreshConfigs();
    selectConfig(saved.id);
  });
}

async function boot(){
  if(localStorage.getItem("spt_sidebar_collapsed")==="1"){
    document.body.classList.add("sidebar-collapsed");
    const btn = document.getElementById("btn-toggle-sidebar");
    if(btn) btn.textContent = "Show list";
  }
  onPresetChange();
  const urlParams = readUrlState();
  applyUrlStateToFilters(urlParams);
  const wantConfig = urlParams.get("config");
  const wantRun = urlParams.get("run");
  const wantSpec = urlParams.get("spec");
  const wantSet = urlParams.get("set");
  const wantView = urlParams.get("view");
  if(urlParams.get("spec_env")) specsEnv = urlParams.get("spec_env");
  if(wantView === "swagger" || wantView === "ops" || wantView === "raw" || wantView === "config" || wantView === "versions" || wantView === "trace"){
    specsView = wantView === "ops" ? "swagger" : wantView;
  }
  setMode(wantSpec ? "specs" : (wantConfig ? "configs" : "runs"));
  try { await loadCatalog(); applyUrlStateToFilters(urlParams); } catch(e){ showBanner("Catalog load failed: "+e.message); }
  try { await loadHealth(); } catch(e){ /* non-fatal */ }
  try { await refreshConfigs(); } catch(e){ /* shown in sidebar when on configs tab */ }
  try { await refreshRuns(); } catch(e){ /* refreshRuns handles sidebar message */ }
  try { await refreshSpecsList(); } catch(e){ /* optional */ }
  const btn = document.getElementById("btn-api-picker");
  if(btn) btn.textContent = "APIs (all)";
  try {
    if(wantSpec){
      setMode("specs");
      await selectSpec(wantSpec, {
        skipUrl: true,
        replaceUrl: true,
        setVersion: wantSet != null && wantSet !== "" ? Number(wantSet) : undefined
      });
      syncPortalUrl({ replace: true });
    } else if(wantConfig){
      setMode("configs");
      await selectConfig(wantConfig, { skipUrl: true, replaceUrl: true });
      syncPortalUrl({ replace: true });
    } else if(wantRun){
      await selectRun(wantRun, { skipUrl: true, replaceUrl: true });
      syncPortalUrl({ replace: true });
    } else if(runs.length){
      await selectRun(runs[0].id, { replaceUrl: true });
    } else {
      syncPortalUrl({ replace: true });
    }
  } catch(e){
    showBanner("Detail load failed: "+e.message);
    if(runs.length && !wantRun && !wantSpec){
      try { await selectRun(runs[0].id, { replaceUrl: true }); } catch(_){}
    }
  }
}

window.addEventListener("popstate", async ()=>{
  const params = readUrlState();
  applyUrlStateToFilters(params);
  const wantConfig = params.get("config");
  const wantRun = params.get("run");
  const wantSpec = params.get("spec");
  const wantSet = params.get("set");
  const wantView = params.get("view");
  if(params.get("spec_env")) specsEnv = params.get("spec_env");
  if(wantView === "swagger" || wantView === "ops" || wantView === "raw" || wantView === "config" || wantView === "versions" || wantView === "trace"){
    specsView = wantView === "ops" ? "swagger" : wantView;
  } else if(wantSpec){
    specsView = "overview";
  }
  try {
    if(wantSpec){
      setMode("specs");
      await refreshSpecsList();
      await selectSpec(wantSpec, {
        skipUrl: true,
        setVersion: wantSet != null && wantSet !== "" ? Number(wantSet) : undefined
      });
    } else if(wantConfig){
      setMode("configs");
      await refreshConfigs();
      await selectConfig(wantConfig, { skipUrl: true });
    } else {
      setMode("runs");
      await refreshRuns({resetPage: true});
      if(wantRun) await selectRun(wantRun, { skipUrl: true });
      else if(runs.length) await selectRun(runs[0].id, { skipUrl: true });
    }
  } catch(e){
    showBanner("Navigation failed: "+e.message);
  }
});

boot();
