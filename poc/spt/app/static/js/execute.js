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

function readLoadOverrides(){
  const out = {};
  const vus = parseInt(document.getElementById("run-vus")?.value, 10);
  const calls = parseInt(document.getElementById("run-calls")?.value, 10);
  if(Number.isFinite(vus) && vus > 0) out.vus = vus;
  if(Number.isFinite(calls) && calls > 0) out.iterations = calls;
  return out;
}

function profileBenchDefaults(c){
  const bench = (c && c.payloads && c.payloads.bench_run) || {};
  return {
    vus: bench.vus != null ? Number(bench.vus) : null,
    iterations: bench.iterations != null ? Number(bench.iterations) : null,
    duration: bench.duration || null,
    run_profile: (c && c.run_profile) || "load"
  };
}

function readOverrideDiffs(configId){
  const c = (typeof configs !== "undefined" ? configs : []).find(x=>x.id===configId) || {};
  const base = profileBenchDefaults(c);
  const cur = readLoadOverrides();
  const prof = document.getElementById("run-profile")?.value || "load";
  const preset = document.getElementById("run-preset")?.value || "";
  const out = {};
  if(preset) out.preset = preset;
  if(cur.vus != null && base.vus != null && Number(cur.vus) !== Number(base.vus)) out.vus = cur.vus;
  else if(cur.vus != null && base.vus == null) out.vus = cur.vus;
  if(cur.iterations != null && base.iterations != null && Number(cur.iterations) !== Number(base.iterations)) out.iterations = cur.iterations;
  else if(cur.iterations != null && base.iterations == null && cur.iterations) out.iterations = cur.iterations;
  if(prof && prof !== base.run_profile) out.profile = prof;
  else if(prof) out.profile = prof; // still send profile for apply_run_profile consistency when multi
  return out;
}

function refreshOverrideChip(){
  const chip = document.getElementById("override-chip");
  if(!chip) return;
  const id = document.getElementById("run-config")?.value;
  const c = (typeof configs !== "undefined" ? configs : []).find(x=>x.id===id);
  if(!c){ chip.style.display = "none"; return; }
  const base = profileBenchDefaults(c);
  const cur = readLoadOverrides();
  const prof = document.getElementById("run-profile")?.value || "load";
  const preset = document.getElementById("run-preset")?.value || "";
  let overriding = !!preset;
  if(cur.vus != null && base.vus != null && Number(cur.vus) !== Number(base.vus)) overriding = true;
  if(cur.iterations != null && base.iterations != null && Number(cur.iterations) !== Number(base.iterations)) overriding = true;
  if(prof && base.run_profile && prof !== base.run_profile) overriding = true;
  chip.style.display = overriding ? "inline-block" : "none";
}

function onPresetChange(){
  const c = (typeof activeProfile === "function") ? activeProfile() : null;
  if(c && !audienceAllowsMultiLoad(c.audience)){
    applyAudienceLoadLimits(c.audience);
    refreshOverrideChip();
    return;
  }
  const p = document.getElementById("run-preset").value;
  const vusEl = document.getElementById("run-vus");
  const callsEl = document.getElementById("run-calls");
  const profEl = document.getElementById("run-profile");
  if(!vusEl || !callsEl) return;
  if(p === "20u-50"){ vusEl.value = 20; callsEl.value = 50; if(profEl) profEl.value = "load"; }
  else if(p === "smoke"){ vusEl.value = 3; callsEl.value = ""; }
  else if(p === "load"){ vusEl.value = 10; callsEl.value = ""; if(profEl) profEl.value = "load"; }
  else if(p === "stress"){ vusEl.value = 25; callsEl.value = ""; if(profEl) profEl.value = "load"; }
  refreshOverrideChip();
}

function toggleSidebar(){
  document.body.classList.toggle("sidebar-collapsed");
  const collapsed = document.body.classList.contains("sidebar-collapsed");
  localStorage.setItem("spt_sidebar_collapsed", collapsed ? "1" : "0");
  const btn = document.getElementById("btn-toggle-sidebar");
  if(btn) btn.textContent = collapsed ? "Show list" : "Hide list";
}

function onProfileChange(){
  const prof = document.getElementById("run-profile")?.value;
  if(prof !== "debug"){ refreshOverrideChip(); return; }
  const vus = parseInt(document.getElementById("run-vus")?.value, 10);
  const calls = parseInt(document.getElementById("run-calls")?.value, 10);
  if((Number.isFinite(vus) && vus > 1) || (Number.isFinite(calls) && calls > 1)){
    const vusEl = document.getElementById("run-vus");
    const callsEl = document.getElementById("run-calls");
    const presetEl = document.getElementById("run-preset");
    if(vusEl) vusEl.value = 1;
    if(callsEl) callsEl.value = 1;
    if(presetEl) presetEl.value = "";
  }
  refreshOverrideChip();
}

async function executeConfig(configId, preset){
  document.getElementById("main").innerHTML = '<div class="empty">Starting run…</div>';
  const cfgMeta = configs.find(x=>x.id===configId) || {};
  const allow = audienceAllowsMultiLoad(cfgMeta.audience);
  let overrides = readOverrideDiffs(configId);
  if(preset) overrides.preset = preset;
  if(!allow){
    overrides = { vus: 1, iterations: 1, profile: "load" };
    const presetEl = document.getElementById("run-preset");
    if(presetEl) presetEl.value = "";
    preset = "";
  } else if(overrides.preset === "20u-50" || (overrides.vus && overrides.vus > 1) || (overrides.iterations && overrides.iterations > 1)){
    overrides.profile = "load";
  }
  // If no load diffs, still send profile from header for apply_run_profile
  if(!overrides.profile){
    overrides.profile = document.getElementById("run-profile")?.value || "load";
  }
  const body = {config_id: configId, triggered_by: "manual", wait: false, ...overrides};
  if(!allow){
    body.profile = "load";
  }
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
  if(body.payload_set_version == null){
    const c = cfgMeta;
    const fromCfg = c && (c.payload_set_version != null
      ? c.payload_set_version
      : (c.payloads && c.payloads.payload_set_version));
    if(fromCfg != null) body.payload_set_version = Number(fromCfg);
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

function applyProfileToHeader(c){
  if(!c) return;
  const bench = (c.payloads && c.payloads.bench_run) || {};
  const allow = audienceAllowsMultiLoad(c.audience);
  const vusEl = document.getElementById("run-vus");
  const callsEl = document.getElementById("run-calls");
  const profEl = document.getElementById("run-profile");
  const presetEl = document.getElementById("run-preset");
  if(!allow){
    if(vusEl) vusEl.value = 1;
    if(callsEl) callsEl.value = 1;
    if(presetEl) presetEl.value = "";
    if(profEl) profEl.value = "load";
  } else {
    if(vusEl && bench.vus != null) vusEl.value = bench.vus;
    if(callsEl){
      if(bench.iterations != null) callsEl.value = bench.iterations;
      else if(bench.duration && !bench.iterations) callsEl.value = "";
    }
    if(profEl && c.run_profile) profEl.value = c.run_profile;
    if(presetEl) presetEl.value = "";
  }
  applyAudienceLoadLimits(c.audience || "developer");
  if(typeof syncProfileControls === "function") syncProfileControls(c.id);
  else {
    const sel = document.getElementById("run-config");
    if(sel && c.id && [].some.call(sel.options, o=>o.value===c.id)) sel.value = c.id;
  }
  if(typeof refreshOverrideChip === "function") refreshOverrideChip();
}

function cfgInputStyle(){
  return 'width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem';
}

function durationPresetValue(duration){
  const d = String(duration||"").trim().toLowerCase();
  if(d === "15m" || d === "15min") return "15m";
  if(d === "30m" || d === "30min") return "30m";
  if(d === "1h" || d === "60m" || d === "1hr") return "1h";
  if(d) return "custom";
  return "30m";
}

function durationPresetHtml(duration, hasIterations){
  const preset = hasIterations ? "" : durationPresetValue(duration);
  const customVal = (!hasIterations && preset === "custom") ? esc(duration||"") : (preset && preset !== "custom" ? preset : "");
  const customShow = preset === "custom" ? "block" : "none";
  const tags = [
    {v:"", label:"Calls"},
    {v:"15m", label:"15m"},
    {v:"30m", label:"30m"},
    {v:"1h", label:"1h"},
    {v:"custom", label:"Custom"}
  ];
  return '<div class="dur-tags" id="cfg-duration-tags" role="group" aria-label="Duration">'+
    tags.map(t=>'<button type="button" class="dur-tag'+(preset===t.v?" active":"")+'" data-dur="'+t.v+'" onclick="pickDurationTag(\''+t.v+'\')">'+t.label+'</button>').join("")+
  '</div>'+
  '<input type="hidden" id="cfg-duration-preset" value="'+esc(preset)+'"/>'+
  '<input id="cfg-duration" value="'+customVal+'" style="'+cfgInputStyle()+';display:'+customShow+'" placeholder="e.g. 45m or 90s" oninput="document.getElementById(\'cfg-duration-preset\').value=\'custom\'"/>'+
  '<p class="sub">One click. Time modes clear Calls; Calls mode clears duration.</p>';
}

function pickDurationTag(preset){
  const hidden = document.getElementById("cfg-duration-preset");
  const custom = document.getElementById("cfg-duration");
  const calls = document.getElementById("cfg-calls");
  if(hidden) hidden.value = preset == null ? "" : String(preset);
  document.querySelectorAll("#cfg-duration-tags .dur-tag").forEach(btn=>{
    btn.classList.toggle("active", btn.getAttribute("data-dur") === String(preset));
  });
  if(preset && preset !== "custom"){
    if(calls) calls.value = "";
    if(custom){ custom.style.display = "none"; custom.value = preset; }
  } else if(preset === "custom"){
    if(calls) calls.value = "";
    if(custom){
      custom.style.display = "block";
      if(!custom.value || ["15m","30m","1h",""].indexOf(custom.value)>=0) custom.value = "45m";
      custom.focus();
    }
  } else {
    if(custom){ custom.style.display = "none"; custom.value = ""; }
  }
}

function onDurationPresetChange(){
  const preset = document.getElementById("cfg-duration-preset")?.value || "";
  pickDurationTag(preset);
}

function audienceAllowsMultiLoad(audience){
  return String(audience || "developer").toLowerCase() === "developer";
}

function applyAudienceLoadLimits(audience){
  const allow = audienceAllowsMultiLoad(audience);
  const vusEl = document.getElementById("run-vus");
  const callsEl = document.getElementById("run-calls");
  const presetEl = document.getElementById("run-preset");
  const profEl = document.getElementById("run-profile");
  if(!allow){
    if(vusEl){ vusEl.value = 1; vusEl.max = 1; vusEl.title = "Non-developer profiles: 1 VU only (single call with traces)"; }
    if(callsEl){ callsEl.value = 1; callsEl.max = 1; callsEl.title = "Non-developer profiles: 1 call with traces"; }
    if(presetEl){ presetEl.value = ""; presetEl.disabled = true; }
    if(profEl){ profEl.value = "load"; }
  } else {
    if(vusEl){ vusEl.max = 50; vusEl.title = ""; }
    if(callsEl){ callsEl.max = 10000; callsEl.title = ""; }
    if(presetEl) presetEl.disabled = false;
  }
  const lock = document.getElementById("audience-load-lock");
  if(lock){
    lock.style.display = allow ? "none" : "block";
    lock.textContent = allow
      ? ""
      : "Audience “"+(audience||"other")+"” — single call with traces only. Multi-VU / multi-load is limited to developer profiles.";
  }
}

function targetDomainBits(url){
  try {
    const u = new URL(url);
    return { host: u.host, path: u.pathname === "/" ? "" : u.pathname };
  } catch(_){
    return { host: "", path: "" };
  }
}

function setTargetHint(url, meta){
  const hint = document.getElementById("cfg-target-hint");
  if(!hint) return;
  const bits = targetDomainBits(url||"");
  const parts = [];
  if(bits.host) parts.push("domain "+bits.host);
  if(bits.path) parts.push("path "+bits.path);
  if(meta && meta.runtime) parts.push("runtime="+meta.runtime);
  if(meta && meta.source) parts.push(meta.source);
  if(meta && meta.openapi_version) parts.push("API "+meta.openapi_version);
  hint.textContent = parts.length
    ? ("Auto from service+env · " + parts.join(" · "))
    : "Auto from service targets[env]; edit only to override.";
}

async function resolveTargetForServiceEnv(service, environment){
  if(!service) return null;
  // Fast path: registration targets already in catalog (if loaded)
  try {
    const svc = (catalog.services||[]).find(s=>s.id===service);
    const targets = (svc && svc.targets) || {};
    const env = environment || "dev";
    const localPick = targets["public_"+env] || targets.public || targets[env];
    if(localPick && String(localPick).startsWith("http") && String(localPick).indexOf(".svc.cluster.local") < 0){
      return { target_url: String(localPick).replace(/\/$/,""), source: "catalog.targets" };
    }
  } catch(_){}
  try {
    const data = await fetchJson(
      "/api/catalog/"+encodeURIComponent(service)+"/target?environment="+encodeURIComponent(environment||"dev")
    );
    if(data && data.target_url) return data;
  } catch(_){}
  try {
    const data = await fetchJson(
      "/api/catalog/"+encodeURIComponent(service)+"/apis?environment="+encodeURIComponent(environment||"dev")
    );
    if(data && data.target_url) return data;
  } catch(_){}
  return null;
}

async function autoFillTargetUrl(opts){
  opts = opts || {};
  const service = document.getElementById("cfg-service")?.value;
  const environment = document.getElementById("cfg-env")?.value || "dev";
  const target = document.getElementById("cfg-target");
  if(!service || !target) return;
  const data = await resolveTargetForServiceEnv(service, environment);
  if(!data || !data.target_url){
    setTargetHint(target.value, { source: "no target for "+service+"/"+environment });
    return;
  }
  const next = String(data.target_url).replace(/\/$/,"");
  const cur = (target.value||"").trim();
  const staleCluster = cur.indexOf(".svc.cluster.local") >= 0;
  const empty = !cur;
  if(opts.force || empty || staleCluster || opts.always){
    target.value = next;
  }
  setTargetHint(target.value, data);
}

async function selectConfig(id, opts){
  opts = opts || {};
  selectedConfigId=id; selectedRunId=null; renderList();
  // Keep profile filter aligned when opening a profile from the list
  if(typeof syncProfileControls === "function") syncProfileControls(id);
  const c = await fetchJson("/api/configs/"+id);
  editPayloads = JSON.parse(JSON.stringify(c.payloads||{}));
  applyProfileToHeader(c);
  const bench = (c.payloads||{}).bench_run || {vus:1, duration:"30m"};
  const auth = (c.payloads||{}).auth_env || {};
  const audience = c.audience || "developer";
  const setVer = c.payload_set_version != null
    ? c.payload_set_version
    : ((c.payloads||{}).payload_set_version);
  const hasIters = bench.iterations != null && bench.iterations !== "";
  document.getElementById("main").innerHTML =
    '<h2>Profile: '+esc(c.name)+'</h2>'+
    '<p class="sub">SPT run settings profile — who / where / payloads / load. Header can override for one run.</p>'+
    '<div class="toolbar"><button onclick="saveConfig(\''+c.id+'\')">Save profile</button>'+
      '<button class="secondary" onclick="executeConfig(\''+c.id+'\')">Run with this profile</button></div>'+
    '<div class="section"><div class="section-h">Identity</div><div class="section-b">'+
      row("Name", '<input id="cfg-name" value="'+esc(c.name)+'" style="'+cfgInputStyle()+'"/>')+
      row("Description", '<input id="cfg-desc" value="'+esc(c.description||"")+'" style="'+cfgInputStyle()+'"/>')+
      row("Audience", selAudience(audience))+
    '</div></div>'+
    '<div class="section"><div class="section-h">Target</div><div class="section-b">'+
      row("Service", selService(c.service))+
      row("Environment", selEnv(c.environment))+
      row("API version", '<select id="cfg-openapi-version" style="'+cfgInputStyle()+'"><option value="">Loading…</option></select><p class="sub">OpenAPI contract (info.version) used to discover APIs.</p>')+
      row("Target URL", '<input id="cfg-target" value="'+esc(c.target_url||"")+'" style="'+cfgInputStyle()+'" placeholder="Auto-filled from service + env"/>'+
        '<p class="sub" id="cfg-target-hint">Selecting service + env auto-fills the reachable URL (e.g. https://am-dev.asrax.in/analysis).</p>')+
    '</div></div>'+
    '<div class="section"><div class="section-h">Payloads</div><div class="section-b">'+
      row("Payload set", '<select id="cfg-payload-set" style="'+cfgInputStyle()+'"><option value="">Loading…</option></select><p class="sub">Same sets as OpenAPI → Set. Applied on run when header/OpenAPI does not override.</p>')+
    '</div></div>'+
    '<div class="section"><div class="section-h">Auth</div><div class="section-b">'+
      row("Default user", '<input id="cfg-username" value="'+esc(auth.username||"")+'" style="'+cfgInputStyle()+'" autocomplete="username"/><p class="sub">SPT resolves credentials; password is not stored here.</p>')+
    '</div></div>'+
    '<div class="section"><div class="section-h">Load defaults</div><div class="section-b">'+
      '<div class="audience-lock" id="cfg-audience-lock" style="display:'+(audienceAllowsMultiLoad(audience)?"none":"block")+'">'+
        (audienceAllowsMultiLoad(audience)?"":('Audience “'+esc(audience)+'” — single call with traces only. Multi-VU / multi-duration load is for developer profiles.'))+
      '</div>'+
      row("Run profile", '<select id="cfg-run-profile" style="'+cfgInputStyle()+'"'+(audienceAllowsMultiLoad(audience)?"":" disabled")+'>'+
        '<option value="debug"'+(c.run_profile==="debug"?" selected":"")+'>debug (1×1 forced)</option>'+
        '<option value="load"'+(c.run_profile!=="debug"?" selected":"")+'>load</option></select>')+
      row("VUs", '<input id="cfg-vus" type="number" min="1" max="'+(audienceAllowsMultiLoad(audience)?50:1)+'" value="'+(audienceAllowsMultiLoad(audience)?(bench.vus!=null?esc(String(bench.vus)):"1"):"1")+'" style="'+cfgInputStyle()+'"'+(audienceAllowsMultiLoad(audience)?"":" disabled")+'/>')+
      row("Calls (iterations)", '<input id="cfg-calls" type="number" min="1" max="'+(audienceAllowsMultiLoad(audience)?10000:1)+'" value="'+(audienceAllowsMultiLoad(audience)?(hasIters?esc(String(bench.iterations)):""):"1")+'" style="'+cfgInputStyle()+'" placeholder="e.g. 50" oninput="onCallsInputChange()"'+(audienceAllowsMultiLoad(audience)?"":" disabled")+'/><p class="sub">Total shared calls. Clears Duration when set.</p>')+
      row("Duration", audienceAllowsMultiLoad(audience)
        ? durationPresetHtml(bench.duration||"30m", hasIters)
        : '<p class="sub">Locked to 1 call (traces on). Switch audience to <strong>developer</strong> for multi-load.</p><input type="hidden" id="cfg-duration-preset" value=""/><input type="hidden" id="cfg-duration" value=""/>')+
    '</div></div>';
  const audSel = document.getElementById("cfg-audience");
  if(audSel) audSel.addEventListener("change", ()=>{
    // Re-render form limits when audience changes (save still required)
    const note = document.getElementById("cfg-audience-lock");
    const a = audSel.value;
    if(note){
      note.style.display = audienceAllowsMultiLoad(a) ? "none" : "block";
      note.textContent = audienceAllowsMultiLoad(a) ? "" :
        'Audience “'+a+'” — single call with traces only. Multi-VU / multi-duration load is for developer profiles.';
    }
    applyAudienceLoadLimits(a);
  });
  const svc = document.getElementById("cfg-service");
  const env = document.getElementById("cfg-env");
  if(svc) svc.addEventListener("change", onConfigServiceEnvChange);
  if(env) env.addEventListener("change", onConfigServiceEnvChange);
  await fillConfigOpenApiVersions(c.service, c.environment, c.openapi_version);
  await fillConfigPayloadSets(c.service, setVer);
  await autoFillTargetUrl({ force: !c.target_url || String(c.target_url).indexOf(".svc.cluster.local")>=0, always: false });
  await refreshRunOpenApiVersionSelect(c.environment, c.openapi_version);
  if(!opts.skipUrl) syncPortalUrl({ replace: !!opts.replaceUrl });
}

function onCallsInputChange(){
  const calls = parseInt(document.getElementById("cfg-calls")?.value, 10);
  if(Number.isFinite(calls) && calls > 0){
    pickDurationTag("");
  }
}

async function fillConfigPayloadSets(service, selectedVersion){
  const sel = document.getElementById("cfg-payload-set");
  if(!sel) return;
  if(!service){
    sel.innerHTML = '<option value="">— pick service —</option>';
    return;
  }
  try {
    const data = await fetchJson("/api/payload-sets/"+encodeURIComponent(service));
    const sets = data.sets || data.versions || [];
    const active = data.active_version;
    const opts = ['<option value="">active'+(active!=null?(" (v"+active+")"):"")+'</option>'];
    sets.forEach(s=>{
      const ver = s.version != null ? s.version : s;
      const label = (s.label || ("v"+ver)) + (Number(ver)===Number(active) ? " · active" : "");
      const n = s.api_count != null ? (" · "+s.api_count+" APIs") : "";
      const selected = selectedVersion != null && Number(selectedVersion)===Number(ver) ? " selected" : "";
      opts.push('<option value="'+esc(String(ver))+'"'+selected+'>'+esc(label+n)+'</option>');
    });
    sel.innerHTML = opts.join("");
  } catch(e){
    sel.innerHTML = '<option value="">No payload sets ('+esc(e.message)+')</option>';
  }
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
  // Always refresh reachable target when service or env changes
  await autoFillTargetUrl({ force: true, always: true });
  try {
    const data = await fetchJson("/api/catalog/"+encodeURIComponent(service)+"/apis?environment="+encodeURIComponent(environment));
    serviceApisCache[service + "|" + environment] = data;
    if(data.target_url){
      const target = document.getElementById("cfg-target");
      if(target) target.value = String(data.target_url).replace(/\/$/,"");
      setTargetHint(target && target.value, data);
    }
    await fillConfigOpenApiVersions(service, environment, data.openapi_version || null);
    await fillConfigPayloadSets(service, document.getElementById("cfg-payload-set")?.value || null);
    await refreshRunOpenApiVersionSelect(environment, data.openapi_version || null);
  } catch(e){
    console.warn("target refresh failed", e);
  }
}

function row(l, html){ return '<div style="margin-bottom:.5rem"><label style="font-size:.72rem;color:var(--muted)">'+l+'</label><div>'+html+'</div></div>'; }
function selAudience(v){
  const opts = ["developer","agent","ci","shared"];
  return '<select id="cfg-audience" style="'+cfgInputStyle()+'">'+
    opts.map(a=>'<option value="'+a+'"'+(a===v?" selected":"")+'>'+a+'</option>').join("")+'</select>';
}
function selService(v){
  const services = (catalog.services||[]).slice();
  if(v && !services.some(s=>s.id===v)) services.unshift({id:v, label:v+" (saved)"});
  return '<select id="cfg-service" style="'+cfgInputStyle()+'">'+
    (services.length?"":'<option value="'+esc(v||"")+'">'+esc(v||"—")+'</option>')+
    services.map(s=>'<option value="'+esc(s.id)+'"'+(s.id===v?" selected":"")+'>'+esc(s.label||s.id)+'</option>').join("")+'</select>';
}
function selEnv(v){
  const envs = (catalog.environments||[]).slice();
  if(v && envs.indexOf(v) < 0) envs.unshift(v);
  return '<select id="cfg-env" style="'+cfgInputStyle()+'">'+
    (envs.length?"":'<option>'+esc(v||"dev")+'</option>')+
    envs.map(e=>'<option'+(e===v?" selected":"")+'>'+esc(e)+'</option>').join("")+'</select>';
}

async function saveConfig(id){
  const audience = document.getElementById("cfg-audience")?.value || "developer";
  const allow = audienceAllowsMultiLoad(audience);
  const vus = parseInt(document.getElementById("cfg-vus")?.value, 10);
  const calls = parseInt(document.getElementById("cfg-calls")?.value, 10);
  const preset = document.getElementById("cfg-duration-preset")?.value || "";
  const customDur = (document.getElementById("cfg-duration")?.value || "").trim();
  let duration = "";
  if(preset && preset !== "custom") duration = preset;
  else if(preset === "custom") duration = customDur;
  const bench = {};
  if(!allow){
    bench.vus = 1;
    bench.iterations = 1;
  } else {
    if(Number.isFinite(vus) && vus > 0) bench.vus = vus;
    if(Number.isFinite(calls) && calls > 0){
      bench.iterations = calls;
    } else if(duration){
      bench.duration = duration;
    } else {
      bench.duration = "30m";
    }
  }
  const setRaw = document.getElementById("cfg-payload-set")?.value;
  const payloadSetVersion = setRaw !== "" && setRaw != null ? Number(setRaw) : null;
  const username = (document.getElementById("cfg-username")?.value || "").trim();
  const body = {
    name: document.getElementById("cfg-name").value,
    description: document.getElementById("cfg-desc")?.value || "",
    service: document.getElementById("cfg-service").value,
    environment: document.getElementById("cfg-env").value,
    audience: audience,
    openapi_version: document.getElementById("cfg-openapi-version")?.value || null,
    target_url: document.getElementById("cfg-target").value,
    run_profile: allow ? (document.getElementById("cfg-run-profile")?.value || "load") : "load",
    payload_set_version: payloadSetVersion,
    payloads: {
      bench_run: bench,
      auth_env: { username: username || undefined },
      payload_set_version: payloadSetVersion
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
    const base = Object.assign({}, c);
    delete base.id;
    delete base.created_at;
    delete base.updated_at;
    base.name = "new-profile";
    base.audience = document.getElementById("f-audience")?.value || "developer";
    base.description = "New SPT run settings profile";
    const saved = await fetchJson("/api/configs", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(base)});
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
