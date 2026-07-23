/* Specs — service list / OpenAPI fetch */
async function refreshSpecsList(){
  try {
    const data = await fetchJson("/api/catalog/registrations");
    const registered = data.services || [];
    const byId = {};
    registered.forEach(s=>{ byId[s.id] = s; });
    // Keep full catalog service list visible (not only spt.yaml registrations)
    (catalog.services||[]).forEach(s=>{
      if(!s || !s.id || byId[s.id]) return;
      byId[s.id] = {
        id: s.id,
        label: s.label || s.id,
        runtime: s.runtime || "?",
        openapi_path: (s.openapi && s.openapi.path) || null,
        targets: s.targets || {},
        owners: s.owners || null,
        source: s.source || "catalog",
        trace: { registered_by: (s.owners||[])[0] || null }
      };
    });
    specsList = Object.keys(byId).sort((a,b)=>{
      const ra = byId[a].source === "registration" ? 0 : 1;
      const rb = byId[b].source === "registration" ? 0 : 1;
      if(ra !== rb) return ra - rb;
      return a.localeCompare(b);
    }).map(k=>byId[k]);
  } catch(e){
    specsList = [];
    if(mode === "specs") setSidebarMessage("Could not load registrations: "+e.message);
  }
  updateCounts();
  if(mode === "specs") renderList();
}

async function selectSpec(service, opts){
  opts = opts || {};
  selectedSpecService = service;
  selectedRunId = null;
  // Do not clear profile filter — OpenAPI keeps the selected profile intact
  if(specsPayloadService !== service){
    specsPayloadService = null;
    specsPayloadCatalog = [];
    specsPayloadIndex = [];
    specsPayloadCursor = 0;
    specsPayloadSetService = null;
    specsPayloadSets = [];
    specsPayloadSetDetail = null;
    // Keep the last chosen set for this service across reload / re-select
    if(opts.setVersion != null && !Number.isNaN(Number(opts.setVersion))){
      specsPayloadSetVersion = Number(opts.setVersion);
    } else {
      specsPayloadSetVersion = loadPayloadSetVersionFromStorage(service);
    }
    loadActivePayloadsFromStorage(service);
    loadSpecsLoadApiIds(service);
    specsContractVersion = null;
    try {
      const raw = localStorage.getItem("spt_specs_contract_"+service);
      if(raw){
        const saved = JSON.parse(raw);
        if(saved && saved.env){
          specsEnv = saved.env;
          specsContractVersion = saved.version || null;
        }
      }
    } catch(_){}
  } else if(opts.setVersion != null && !Number.isNaN(Number(opts.setVersion))){
    specsPayloadSetVersion = Number(opts.setVersion);
  }
  stopRunWatch && stopRunWatch();
  if(mode !== "specs") setMode("specs");
  else renderList();
  await renderSpecDetail();
  if(!opts.skipUrl) syncPortalUrl({ replace: !!opts.replaceUrl });
}

async function loadSpecPayload(service, env){
  const key = specsCacheKey(service, env);
  if(specsCache[key]) return specsCache[key];
  const data = await fetchJson(
    "/api/catalog/"+encodeURIComponent(service)+"/openapi?environment="+encodeURIComponent(env)
  );
  specsCache[key] = data;
  return data;
}

async function loadSpecVersions(service){
  if(specsVersionsCache[service]) return specsVersionsCache[service];
  const data = await fetchJson("/api/catalog/"+encodeURIComponent(service)+"/openapi/versions");
  specsVersionsCache[service] = data;
  return data;
}
