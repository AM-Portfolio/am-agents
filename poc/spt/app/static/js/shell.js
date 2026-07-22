let mode="runs", runs=[], configs=[], catalog={}, selectedRunId=null, selectedConfigId=null, editPayloads={};
let sidebarError = "";
let runPollTimer = null;
let selectedApiIds = null; // null = all APIs; string[] = subset
let serviceApisCache = {}; // service -> apis list
const RUNS_PAGE_SIZE = 10;
let runsPage = 1;
let runsTotal = 0;

function setSidebarMessage(msg){ sidebarError = msg || ""; document.getElementById("sidebar-list").innerHTML = '<div class="empty">'+esc(msg)+'</div>'; }
function updateCounts(){
  const rc = document.getElementById("runs-count");
  const cc = document.getElementById("configs-count");
  const sc = document.getElementById("specs-count");
  if(rc) rc.textContent = runsTotal ? String(runsTotal) : (runs.length ? String(runs.length) : "");
  if(cc) cc.textContent = configs.length ? String(configs.length) : "";
  if(sc) sc.textContent = (typeof specsList !== "undefined" && specsList.length) ? String(specsList.length) : "";
}

async function fetchJson(path, opts){
  const r = await fetch(api(path), opts);
  if(!r.ok) throw new Error(path+" HTTP "+r.status);
  return r.json();
}

function showBanner(msg){ const b=document.getElementById("banner"); b.style.display="block"; b.textContent=msg; }

function openDatePicker(el){
  if(!el) return;
  try {
    if(typeof el.showPicker === "function") el.showPicker();
  } catch(_){ /* browser may block if not a user gesture; click handler covers that */ }
}

function filterParams(extra){
  const p = new URLSearchParams();
  const service = document.getElementById("f-service").value;
  const environment = document.getElementById("f-env").value;
  const status = document.getElementById("f-status").value;
  const from = document.getElementById("f-from") && document.getElementById("f-from").value;
  const to = document.getElementById("f-to") && document.getElementById("f-to").value;
  const q = document.getElementById("f-q").value.trim();
  if(service) p.set("service", service);
  if(environment) p.set("environment", environment);
  if(status) p.set("status", status);
  if(from) p.set("from", from);
  if(to) p.set("to", to);
  if(q) p.set("q", q);
  if(extra){
    Object.keys(extra).forEach(k=>{
      if(extra[k] != null && extra[k] !== "") p.set(k, String(extra[k]));
    });
  }
  return p.toString() ? "?"+p.toString() : "";
}

function portalUiPath(){
  return location.pathname.replace(/\/$/, "") || "/ui";
}

function readUrlState(){
  return new URLSearchParams(location.search);
}

function applyUrlStateToFilters(params){
  params = params || readUrlState();
  const map = {
    "f-service": "service",
    "f-env": "environment",
    "f-status": "status",
    "f-from": "from",
    "f-to": "to",
    "f-q": "q"
  };
  Object.keys(map).forEach(id=>{
    const el = document.getElementById(id);
    if(!el) return;
    const v = params.get(map[id]);
    if(v != null) el.value = v;
  });
}

function syncPortalUrl(opts){
  opts = opts || {};
  const p = new URLSearchParams();
  const service = document.getElementById("f-service") && document.getElementById("f-service").value;
  const environment = document.getElementById("f-env") && document.getElementById("f-env").value;
  const status = document.getElementById("f-status") && document.getElementById("f-status").value;
  const from = document.getElementById("f-from") && document.getElementById("f-from").value;
  const to = document.getElementById("f-to") && document.getElementById("f-to").value;
  const q = document.getElementById("f-q") && document.getElementById("f-q").value.trim();
  if(service) p.set("service", service);
  if(environment) p.set("environment", environment);
  if(status) p.set("status", status);
  if(from) p.set("from", from);
  if(to) p.set("to", to);
  if(q) p.set("q", q);
  if(mode === "configs" && selectedConfigId) p.set("config", selectedConfigId);
  else if(mode === "specs" && selectedSpecService) p.set("spec", selectedSpecService);
  else if(selectedRunId) p.set("run", selectedRunId);
  if(mode === "specs" && specsEnv) p.set("spec_env", specsEnv);
  if(mode === "specs" && typeof specsPayloadSetVersion !== "undefined" && specsPayloadSetVersion != null){
    p.set("set", String(specsPayloadSetVersion));
  }
  if(mode === "specs" && typeof specsView !== "undefined" && specsView && specsView !== "overview"){
    p.set("view", specsView);
  }
  const next = portalUiPath() + (p.toString() ? "?" + p.toString() : "");
  const cur = location.pathname.replace(/\/$/, "") + (location.search || "");
  if(next === cur) return;
  const state = { run: selectedRunId, config: selectedConfigId, mode: mode };
  if(opts.replace) history.replaceState(state, "", next);
  else history.pushState(state, "", next);
}

async function loadCatalog(){
  catalog = await fetchJson("/api/catalog");
  const ss = document.getElementById("f-service");
  ss.innerHTML = '<option value="">All services</option>' + (catalog.services||[]).map(s=>'<option value="'+esc(s.id)+'">'+esc(s.label)+'</option>').join("");
  const es = document.getElementById("f-env");
  es.innerHTML = '<option value="">All envs</option>' + (catalog.environments||[]).map(e=>'<option value="'+esc(e)+'">'+esc(e)+'</option>').join("");
}

async function loadHealth(){
  try {
    const h = await fetchJson("/api/platform/health");
    const el = document.getElementById("health-bar");
    const k6 = h.k6_binary ? '<span class="ok">k6</span>' : '<span class="bad">k6 missing</span>';
    const inf = h.influxdb && h.influxdb.configured ? '<span class="ok">influx</span>' : '<span>influx off</span>';
    el.innerHTML = k6 + inf + ' · Grafana linked';
  } catch(e){ document.getElementById("health-bar").textContent = "platform check failed"; }
}

function setMode(m){
  mode=m;
  document.body.classList.remove("mode-runs","mode-configs","mode-specs");
  document.body.classList.add("mode-"+m);
  document.getElementById("tab-runs").classList.toggle("active", m==="runs");
  document.getElementById("tab-configs").classList.toggle("active", m==="configs");
  const tabSpecs = document.getElementById("tab-specs");
  if(tabSpecs) tabSpecs.classList.toggle("active", m==="specs");
  if(m === "specs"){
    // Prefetch Swagger assets so first paint is faster
    try { ensureSwaggerSdk(); } catch(_){}
    try { loadTryToken(false); } catch(_){}
    refreshSpecsList().then(async ()=>{
      updateCounts();
      renderList();
      if(!selectedSpecService && specsList.length){
        // Prefer a registered OpenAPI service so Try it out works immediately
        const preferred = specsList.find(s=>s.source==="registration" && s.openapi_path)
          || specsList.find(s=>s.openapi_path)
          || specsList[0];
        if(preferred) await selectSpec(preferred.id, { replaceUrl: true });
        return;
      }
      if(selectedSpecService) renderSpecDetail();
      else {
        document.getElementById("main").innerHTML = '<div class="empty">Select a service to view OpenAPI.</div>';
      }
    });
  } else {
    renderList();
  }
}

async function applyFilters(){
  const verEl = document.getElementById("f-api-version");
  const head = document.getElementById("run-openapi-version");
  if(verEl && head && verEl.options.length > 1 && verEl.value !== head.value){
    head.value = verEl.value;
    if(typeof onRunOpenApiVersionChange === "function") await onRunOpenApiVersionChange();
  }
  if(mode==="runs"){
    runsPage = 1;
    await refreshRuns();
  }
  else if(mode==="configs") await refreshConfigs();
  else if(mode==="specs"){
    const envEl = document.getElementById("f-env");
    if(envEl && envEl.value && envEl.value !== specsEnv){
      specsEnv = envEl.value;
      if(selectedSpecService) delete specsCache[specsCacheKey(selectedSpecService, specsEnv)];
    }
    if(verEl && verEl.value && typeof parseVersionOptionValue === "function"){
      const parsed = parseVersionOptionValue(verEl.value);
      if(parsed.environment && parsed.environment !== specsEnv){
        specsEnv = parsed.environment;
        if(selectedSpecService) delete specsCache[specsCacheKey(selectedSpecService, specsEnv)];
      }
    }
    await refreshSpecsList();
    if(selectedSpecService) await renderSpecDetail();
  }
  syncPortalUrl({ replace: true });
}

async function refreshRuns(opts){
  opts = opts || {};
  if(opts.resetPage) runsPage = 1;
  setSidebarMessage("Loading runs…");
  try {
    const offset = Math.max(0, (runsPage - 1) * RUNS_PAGE_SIZE);
    const data = await fetchJson("/api/runs"+filterParams({
      limit: RUNS_PAGE_SIZE,
      offset: offset,
    }));
    runs = data.runs || [];
    runsTotal = data.total != null ? data.total : runs.length;
    const pages = Math.max(1, Math.ceil(runsTotal / RUNS_PAGE_SIZE) || 1);
    if(runsPage > pages){
      runsPage = pages;
      return refreshRuns();
    }
    sidebarError = "";
    updateCounts();
    renderList();
    await refreshConfigSelect();
  } catch(e) {
    runs = [];
    runsTotal = 0;
    updateCounts();
    setSidebarMessage("Could not load runs: "+e.message);
    renderRunsPager();
    showBanner("Runs API failed — open https://am.asrax.in/spt-poc/ui and hard-refresh");
  }
}

function runsPageCount(){
  return Math.max(1, Math.ceil((runsTotal || 0) / RUNS_PAGE_SIZE) || 1);
}

function renderRunsPager(){
  const pager = document.getElementById("runs-pager");
  if(!pager) return;
  if(mode !== "runs" || !runsTotal){
    pager.style.display = "none";
    pager.innerHTML = "";
    return;
  }
  const pages = runsPageCount();
  if(pages <= 1){
    pager.style.display = "flex";
    pager.innerHTML = '<span class="sub">'+esc(runsTotal)+' run'+(runsTotal===1?"":"s")+'</span>';
    return;
  }
  const from = (runsPage - 1) * RUNS_PAGE_SIZE + 1;
  const to = Math.min(runsTotal, runsPage * RUNS_PAGE_SIZE);
  pager.style.display = "flex";
  pager.innerHTML =
    '<button type="button" class="secondary" '+(runsPage<=1?"disabled":"")+' onclick="goRunsPage('+(runsPage-1)+')" title="Previous">‹</button>'+
    '<span class="sub">'+esc(from)+'–'+esc(to)+' of '+esc(runsTotal)+'</span>'+
    '<button type="button" class="secondary" '+(runsPage>=pages?"disabled":"")+' onclick="goRunsPage('+(runsPage+1)+')" title="Next">›</button>';
}

async function goRunsPage(page){
  const pages = runsPageCount();
  const next = Math.min(pages, Math.max(1, Number(page) || 1));
  if(next === runsPage && runs.length) return;
  runsPage = next;
  await refreshRuns();
}

async function refreshConfigs(){
  try {
    configs = (await fetchJson("/api/configs"+(document.getElementById("f-service").value ? "?service="+encodeURIComponent(document.getElementById("f-service").value) : ""))).configs || [];
    updateCounts();
    if(mode==="configs") renderList();
    await refreshConfigSelect();
  } catch(e) {
    configs = [];
    updateCounts();
    if(mode==="configs") setSidebarMessage("Could not load configs: "+e.message);
  }
}

async function refreshConfigSelect(){
  if(!configs.length) configs = (await fetchJson("/api/configs")).configs || [];
  const sel = document.getElementById("run-config");
  if(!sel) return;
  const prev = sel.value;
  sel.innerHTML = configs.map(c=>'<option value="'+c.id+'">'+esc(c.name)+' ('+esc(c.service)+')</option>').join("");
  if(prev && configs.some(c=>c.id===prev)) sel.value = prev;
  if(!sel._sptBound){
    sel._sptBound = true;
    sel.addEventListener("change", async ()=>{
      selectedApiIds = null;
      serviceApisCache = {};
      openApiVersionCache = {};
      const c = configs.find(x=>x.id===sel.value);
      try { await refreshRunOpenApiVersionSelect(c && c.environment, c && c.openapi_version); } catch(_){}
      const btn = document.getElementById("btn-api-picker");
      if(btn) btn.textContent = "APIs (all)";
    });
  }
  const c = configs.find(x=>x.id===sel.value) || configs[0];
  if(c && typeof refreshRunOpenApiVersionSelect === "function"){
    try { await refreshRunOpenApiVersionSelect(c.environment, c.openapi_version); } catch(_){}
  }
}

function renderList(){
  const el = document.getElementById("sidebar-list");
  if(mode === "specs"){
    const pager = document.getElementById("runs-pager");
    if(pager){ pager.style.display = "none"; pager.innerHTML = ""; }
    renderSpecsSidebar();
    return;
  }
  if(mode === "configs"){
    const pager = document.getElementById("runs-pager");
    if(pager){ pager.style.display = "none"; pager.innerHTML = ""; }
  }
  if(sidebarError && mode==="runs"){ el.innerHTML = '<div class="empty">'+esc(sidebarError)+'</div>'; renderRunsPager(); return; }
  if(mode==="runs"){
    if(!runs.length){ el.innerHTML='<div class="empty">No runs yet. Click <strong>Run test</strong> above.</div>'; renderRunsPager(); return; }
    el.innerHTML = runs.map(r=>'<div class="item '+(r.id===selectedRunId?"active":"")+'" data-run-id="'+esc(r.id)+'">'+
      '<div><strong>'+esc(r.config_name)+'</strong> '+runOutcomeBadge(r)+'</div>'+
      runOutcomeLine(r)+
      '<div class="sub">'+esc(r.service)+' · '+fmtT(r.started_at)+' · VUs '+(r.payloads_used&&r.payloads_used.bench_run&&r.payloads_used.bench_run.vus||"—")+(r.payloads_used&&r.payloads_used.auth_env&&r.payloads_used.auth_env.username?' · '+esc(r.payloads_used.auth_env.username):'')+'</div></div>').join("");
    el.querySelectorAll("[data-run-id]").forEach(node=>{
      node.addEventListener("click", ()=> selectRun(node.getAttribute("data-run-id")));
    });
    renderRunsPager();
  } else {
    if(!configs.length){ el.innerHTML='<div class="empty">No configs. Click <strong>+ New config</strong>.</div>'; return; }
    el.innerHTML = configs.map(c=>'<div class="item '+(c.id===selectedConfigId?"active":"")+'" data-config-id="'+esc(c.id)+'">'+
      '<div><strong>'+esc(c.name)+'</strong></div><div class="sub">'+esc(c.service)+' · '+esc(c.environment)+'</div></div>').join("");
    el.querySelectorAll("[data-config-id]").forEach(node=>{
      node.addEventListener("click", ()=> selectConfig(node.getAttribute("data-config-id")));
    });
  }
}

async function selectRun(id, opts){
  opts = opts || {};
  stopRunWatch();
  selectedRunId=id; selectedConfigId=null; renderList();
  const r = await fetchJson("/api/runs/"+id);
  editPayloads = JSON.parse(JSON.stringify(r.payloads_used||{}));
  showRunDetail(r, {preserveApi: !!opts.preserveApi});
  if(r.status === "running") startRunWatch(id);
  if(!opts.skipUrl) syncPortalUrl({ replace: !!opts.replaceUrl });
}

function metricStrip(m){
  m = m || {};
  const keys = ["throughput.requestsPerSecond","errorRate","responseTime.p90","responseTime.avg"];
  const parts = [];
  keys.forEach(k=>{
    if(m[k]!=null) parts.push('<div class="metric"><div class="k">'+esc(k)+'</div><div class="n">'+esc(m[k])+'</div></div>');
  });
  if(!parts.length) return "";
  return '<div class="metrics">'+parts.join("")+'</div>';
}
