/* Specs — Swagger Try-it-out apply + mount */
function findOpenOpblock(){
  return document.querySelector("#swagger-ui .opblock.is-open");
}

function ensureTryItOutOpen(opblock){
  if(!opblock) return false;
  const btn = opblock.querySelector("button.try-out__btn");
  if(btn && !/cancel/i.test((btn.textContent||"").trim())){
    btn.click();
    return true;
  }
  return !!(opblock.querySelector(".execute-wrapper, textarea.body-param__text, .body-param textarea"));
}

function findSwaggerBodyTextarea(opblock){
  const root = opblock || document.getElementById("swagger-ui");
  if(!root) return null;
  const candidates = root.querySelectorAll(
    "textarea.body-param__text, .body-param textarea, .opblock-body textarea"
  );
  for(let i=0;i<candidates.length;i++){
    const t = candidates[i];
    if(t && t.offsetParent !== null) return t;
  }
  return null;
}

function setReactInputValue(el, value){
  if(!el) return false;
  const proto = el.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  try {
    const tracker = el._valueTracker;
    if(tracker) tracker.setValue(el.value);
  } catch(_){}
  if(desc && desc.set) desc.set.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function openOpMeta(opblock){
  if(!opblock) return { method: "", path: "", apiIds: [], operationId: "" };
  const mEl = opblock.querySelector(".opblock-summary-method");
  const pEl = opblock.querySelector(".opblock-summary-path");
  const method = ((mEl && mEl.textContent) || "").trim().toLowerCase();
  let path = ((pEl && (pEl.getAttribute("data-path") || pEl.textContent)) || "").trim();
  path = normalizeOpPath(path);
  let operationId = opblock.getAttribute("data-operation-id") || "";
  if(!operationId){
    const oidAttr = opblock.getAttribute("id") || "";
    const m = oidAttr.match(/^operations-[^-]+-(.+)$/);
    if(m) operationId = m[1];
  }
  return { method: method, path: path, apiIds: opApiIds(method, path, operationId), operationId: operationId };
}

function exampleValueFromSpec(entry, opMeta){
  if(entry && entry.body != null) return entry.body;
  const doc = specsEnrichedDoc;
  if(!doc || !opMeta || !opMeta.path) return null;
  const item = (doc.paths || {})[opMeta.path] || {};
  const op = item[opMeta.method];
  if(!op || !op.requestBody || !op.requestBody.content) return null;
  const content = op.requestBody.content;
  const ct = Object.keys(content).find(function(k){ return k.indexOf("json") >= 0; }) || Object.keys(content)[0];
  const media = content[ct] || {};
  const examples = media.examples || {};
  const key = entry && entry.key;
  if(key && examples[key] && examples[key].value != null) return examples[key].value;
  if(key === "official" && examples.official) return examples.official.value;
  if(key === "spt-generated" && examples["spt-generated"]) return examples["spt-generated"].value;
  if(key && String(key).indexOf("spt-active") === 0 && examples["spt-active"]) return examples["spt-active"].value;
  if(key && String(key).indexOf("spt:") === 0){
    const name = entry.name;
    const hitKey = Object.keys(examples).find(function(k){
      return k === ("spt:"+name) || String((examples[k]&&examples[k].summary)||"").indexOf(name) >= 0;
    });
    if(hitKey) return examples[hitKey].value;
  }
  if(media.example != null) return media.example;
  return null;
}

function selectSwaggerExampleOption(opblock, entry){
  if(!opblock || !entry) return false;
  const want = [];
  if(entry.key) want.push(String(entry.key).split("|")[0]);
  if(entry.name) want.push(entry.name);
  const selects = opblock.querySelectorAll("select");
  for(let s=0;s<selects.length;s++){
    const exSel = selects[s];
    for(let i=0;i<exSel.options.length;i++){
      const o = exSel.options[i];
      const ov = String(o.value||"");
      const ot = String(o.text||"");
      const match = want.some(function(k){
        return ov === k || ot.indexOf(k) >= 0
          || (k === "official" && /official/i.test(ot))
          || (k === "spt-generated" && /generated/i.test(ot))
          || (String(k).indexOf("spt-active")===0 && /active/i.test(ot));
      });
      if(match){
        exSel.selectedIndex = i;
        exSel.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }
  }
  return false;
}

function setSwaggerParamInputs(opblock, query, pathParams){
  const root = opblock || document.getElementById("swagger-ui");
  if(!root) return;
  const map = Object.assign({}, pathParams||{}, query||{});
  Object.keys(map).forEach(function(name){
    const val = map[name];
    if(val == null) return;
    const rows = root.querySelectorAll("tr[data-param-name], tr");
    for(let i=0;i<rows.length;i++){
      const row = rows[i];
      const byAttr = row.getAttribute("data-param-name");
      let pname = byAttr || "";
      if(!pname){
        const label = row.querySelector(".parameter__name");
        if(!label) continue;
        pname = (label.childNodes[0] ? label.childNodes[0].textContent : label.textContent).trim();
      }
      if(pname !== name) continue;
      const inp = row.querySelector("input, textarea, select");
      if(inp) setReactInputValue(inp, val);
    }
  });
}

function readSwaggerParamValues(opblock){
  const query = {};
  const pathParams = {};
  const root = opblock || document.getElementById("swagger-ui");
  if(!root) return { query: query, pathParams: pathParams };
  const rows = root.querySelectorAll("tr");
  for(let i=0;i<rows.length;i++){
    const row = rows[i];
    const label = row.querySelector(".parameter__name");
    if(!label) continue;
    const pname = (label.childNodes[0] ? label.childNodes[0].textContent : label.textContent).trim();
    if(!pname) continue;
    const inp = row.querySelector("input, textarea, select");
    if(!inp) continue;
    const val = inp.value;
    if(val == null || String(val).trim() === "") continue;
    const inEl = row.querySelector(".parameter__in, .parameters-col_description .parameter__type");
    const inText = ((inEl && inEl.textContent) || "").toLowerCase();
    const isPath = /\(path\)|path/.test(inText) || (row.querySelector(".parameter__name.required") && /\{/.test(pname));
    // Swagger marks location next to name as .parameter__in
    const loc = row.querySelector(".parameter__in");
    const locText = ((loc && loc.textContent) || "").toLowerCase().replace(/[()]/g,"").trim();
    if(locText === "path" || (isPath && locText !== "query" && locText !== "header")){
      pathParams[pname] = val;
    } else if(locText === "header" || locText === "cookie"){
      // skip for set storage for now
    } else {
      query[pname] = val;
    }
  }
  return { query: query, pathParams: pathParams };
}

function readSwaggerTryRequest(opblock){
  if(opblock) ensureTryItOutOpen(opblock);
  const meta = openOpMeta(opblock);
  const params = readSwaggerParamValues(opblock);
  const ta = findSwaggerBodyTextarea(opblock);
  let body = null;
  let bodyMode = "none";
  if(ta && String(ta.value||"").trim()){
    bodyMode = "raw";
    body = ta.value;
    try { body = JSON.parse(ta.value); } catch(_){}
  }
  const apiId = (meta.apiIds && meta.apiIds[0]) || sptApiSlug((meta.method||"get")+"."+(meta.path||"/"));
  const active = activeEntryForOpMeta(meta);
  return {
    apiId: apiId,
    name: (active && active.name) || "working",
    method: meta.method || "get",
    path: meta.path || "/",
    query: params.query,
    pathParams: params.pathParams,
    body: body,
    body_mode: bodyMode
  };
}

function applyPayloadToTryIt(entry){
  if(!entry) return false;
  const opblock = findOpenOpblock();
  const status = document.getElementById("oas-payload-status");
  if(!opblock){
    if(status) status.textContent = "Open an operation first, then click Apply";
    return false;
  }
  ensureTryItOutOpen(opblock);
  const opMeta = openOpMeta(opblock);
  selectSwaggerExampleOption(opblock, entry);
  const bodyVal = exampleValueFromSpec(entry, opMeta);

  function writeBody(){
    const ta = findSwaggerBodyTextarea(opblock);
    if(bodyVal == null || !ta) return false;
    const text = typeof bodyVal === "string" ? bodyVal : JSON.stringify(bodyVal, null, 2);
    setReactInputValue(ta, text);
    if(ta.value !== text){
      ta.value = text;
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return true;
  }

  writeBody();
  setTimeout(writeBody, 60);
  setTimeout(writeBody, 180);
  setSwaggerParamInputs(opblock, entry.query, entry.pathParams);
  if(status){
    const qn = entry.query ? Object.keys(entry.query).length : 0;
    const pn = entry.pathParams ? Object.keys(entry.pathParams).length : 0;
    status.textContent = "Applied "+(entry.label||entry.key)+
      (bodyVal!=null?" · body":"")+
      (qn||pn ? " · "+(qn+pn)+" param(s)" : "");
  }
  return true;
}

function onPayloadApply(){
  const sel = document.getElementById("oas-payload-select");
  if(!sel) return;
  let entry = specsPayloadCatalog.find(function(p){ return p.key === sel.value; });
  if(!entry && String(sel.value||"").indexOf("spt-active|")===0){
    const apiId = sel.value.split("|")[1];
    const a = specsActivePayloads[apiId];
    if(a){
      entry = {
        key: sel.value,
        name: a.name || "working",
        label: "Active: "+(a.name||"working"),
        apiId: apiId,
        body: a.body,
        query: a.query || {},
        pathParams: a.pathParams || {}
      };
    }
  }
  if(!entry){
    const status = document.getElementById("oas-payload-status");
    if(status) status.textContent = "Pick a payload first";
    return;
  }
  specsPayloadCursor = Math.max(0, specsPayloadCatalog.indexOf(entry));
  applyPayloadToTryIt(entry);
}

function applyActivePayloadForOpblock(opblock){
  if(!opblock) return false;
  ensureTryItOutOpen(opblock);
  const entry = activeEntryForOpMeta(openOpMeta(opblock));
  if(!entry) return false;
  const sel = document.getElementById("oas-payload-select");
  if(sel){
    const opt = Array.from(sel.options||[]).find(o=>o.value===entry.key || String(o.value).indexOf("spt-active|")===0);
    if(opt) sel.value = opt.value;
  }
  return applyPayloadToTryIt(entry);
}

function watchSwaggerForActivePayload(){
  const host = document.getElementById("swagger-ui");
  if(!host) return;
  if(host._sptActiveMo){
    try { host._sptActiveMo.disconnect(); } catch(_){}
  }
  host._sptActiveWatch = true;
  let lastKey = "";
  const tryApply = (force)=>{
    const opblock = findOpenOpblock();
    if(!opblock) return;
    const meta = openOpMeta(opblock);
    const key = (meta.method||"")+" "+(meta.path||"");
    if(!force && key === lastKey) return;
    lastKey = key;
    setTimeout(()=> applyActivePayloadForOpblock(opblock), 50);
    setTimeout(()=> applyActivePayloadForOpblock(opblock), 160);
    setTimeout(()=> applyActivePayloadForOpblock(opblock), 400);
  };
  host.addEventListener("click", (e)=>{
    const t = e.target;
    if(!t || !t.closest) return;
    if(t.closest(".opblock-summary") || t.closest(".try-out__btn") || t.closest(".opblock-control-arrow")){
      setTimeout(()=> tryApply(true), 30);
    }
  }, true);
  const mo = new MutationObserver(()=> tryApply(false));
  mo.observe(host, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  host._sptActiveMo = mo;
  setTimeout(()=> tryApply(true), 120);
}

/** Save Try it out (params + body) into the service payload set. */
async function onPayloadUpdateSet(bumpSet){
  const service = selectedSpecService;
  if(!service) return alert("No service selected");
  if(specsPayloadSetVersion == null && !bumpSet){
    return alert("Load a set version first (Set bar above).");
  }
  const opblock = findOpenOpblock();
  if(!opblock){
    return alert("Open an operation and enable Try it out first.");
  }
  ensureTryItOutOpen(opblock);
  const draft = readSwaggerTryRequest(opblock);
  const hasParams = Object.keys(draft.query).length || Object.keys(draft.pathParams).length;
  if(draft.body == null && !hasParams){
    return alert("Nothing to save — fill query/path params or a request body in Try it out.");
  }
  const name = draft.name || "working";
  try {
    const res = await fetchJson("/api/payloads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service: service,
        api_id: draft.apiId,
        name: name,
        request: {
          method: String(draft.method||"get").toUpperCase(),
          path: draft.path,
          query: draft.query,
          path_params: draft.pathParams,
          body: draft.body,
          body_mode: draft.body_mode || (draft.body != null ? "raw" : "none")
        },
        response: {},
        meta: { source: "swagger-try" },
        bump: false,
        into_set: true,
        set_version: bumpSet ? null : specsPayloadSetVersion,
        bump_set: !!bumpSet
      })
    });
    const pset = res.payload_set || res;
    if(pset && pset.version != null){
      specsPayloadSetVersion = pset.version;
      persistPayloadSetVersion(service, pset.version);
    }
    specsPayloadService = null;
    specsPayloadSetService = null;
    await loadServicePayloadSets(service, true);
    applyPayloadSetToActive(specsPayloadSetDetail);
    const catalog = await loadServicePayloadCatalog(service);
    fillPayloadSelect(catalog);
    // Keep set bar in sync without full remount if possible
    const setSel = document.getElementById("oas-set-select");
    const setStatus = document.getElementById("oas-set-status");
    if(setSel && specsPayloadSets.length){
      setSel.innerHTML = specsPayloadSets.map(s=>{
        const selAttr = Number(s.version)===Number(specsPayloadSetVersion) ? " selected" : "";
        return '<option value="'+esc(String(s.version))+'"'+selAttr+'>'+
          esc("v"+s.version+(s.label?" "+s.label:"")+" · "+(s.api_count||0))+
        '</option>';
      }).join("");
    }
    const n = specsPayloadSetDetail && specsPayloadSetDetail.apis
      ? Object.keys(specsPayloadSetDetail.apis).length : 0;
    if(setStatus){
      setStatus.innerHTML = 'Active set <strong>v'+esc(String(specsPayloadSetVersion))+'</strong> · '+n+' API payload(s)';
    }
    const status = document.getElementById("oas-payload-status");
    if(status){
      status.textContent = (bumpSet?"New set ":"Updated set ")+"v"+specsPayloadSetVersion+
        " · "+draft.apiId+(hasParams?" · params":"")+(draft.body!=null?" · body":"");
    }
  } catch(e){
    alert("Update set failed: "+e.message);
  }
}

function bindPayloadBar(){
  const apply = document.getElementById("oas-payload-apply");
  const save = document.getElementById("oas-payload-save");
  const saveNew = document.getElementById("oas-payload-save-new");
  const sel = document.getElementById("oas-payload-select");
  if(apply) apply.onclick = ()=> onPayloadApply();
  if(save) save.onclick = ()=> onPayloadUpdateSet(false);
  if(saveNew) saveNew.onclick = ()=> onPayloadUpdateSet(true);
  if(sel && !sel._sptBound){
    sel._sptBound = true;
    sel.addEventListener("change", ()=> onPayloadApply());
  }
}

async function mountSwaggerUi(data){
  const host = document.getElementById("swagger-ui-host");
  if(!host) return;
  if(!data.ok || !data.document){
    host.innerHTML = '<div class="empty">OpenAPI unavailable'+(data.error?': '+esc(data.error):'.')+
      '<br/><button type="button" class="secondary" id="oas-swagger-retry">Retry</button></div>';
    const retry = document.getElementById("oas-swagger-retry");
    if(retry) retry.onclick = ()=> mountSwaggerUi(data);
    return;
  }
  host.innerHTML = '<div class="empty">Loading Swagger UI…</div>';
  try {
    await ensureSwaggerSdk();
  } catch(e){
    host.innerHTML = '<div class="empty">Swagger UI SDK failed to load: '+esc(e.message)+
      '<br/><button type="button" class="secondary" id="oas-swagger-retry">Retry</button>'+
      ' <button type="button" class="secondary" onclick="setSpecsView(\'overview\')">Open overview</button></div>';
    const retry = document.getElementById("oas-swagger-retry");
    if(retry) retry.onclick = ()=> mountSwaggerUi(data);
    return;
  }
  if(!window.SwaggerUIBundle){
    host.innerHTML = '<div class="empty">SwaggerUIBundle missing after load.'+
      '<br/><button type="button" class="secondary" id="oas-swagger-retry">Retry</button></div>';
    const retry = document.getElementById("oas-swagger-retry");
    if(retry) retry.onclick = ()=> mountSwaggerUi(data);
    return;
  }
  const service = data.service || selectedSpecService;
  const [token, catalog] = await Promise.all([
    loadTryToken(false),
    loadServicePayloadCatalog(service),
  ]);
  // Always refetch the selected set so Swagger isn't stuck on stale official examples
  await loadServicePayloadSets(service, true);
  applyPayloadSetToActive(specsPayloadSetDetail);
  fillPayloadSelect(catalog);
  bindPayloadBar();
  bindPayloadSetBar();
  // Include set payloads in enrichment catalog
  const setCatalog = [];
  const setApis = (specsPayloadSetDetail && specsPayloadSetDetail.apis) || {};
  Object.keys(setApis).forEach(apiId=>{
    const entry = setApis[apiId] || {};
    const req = entry.request || {};
    let body = req.body;
    if(typeof body === "string"){ try { body = JSON.parse(body); } catch(_){} }
    const method = (req.method || "").toLowerCase();
    const path = req.path || "";
    const aliases = opApiIds(method, path, apiId).concat([apiId]);
    aliases.filter((v,i,a)=>a.indexOf(v)===i).forEach(aid=>{
      setCatalog.push({
        key: "spt-set:"+aid,
        name: entry.name || ("set-v"+specsPayloadSetVersion),
        version: specsPayloadSetVersion,
        apiId: aid,
        method: method,
        path: path,
        body: body,
        query: req.query || {},
        pathParams: req.path_params || req.pathParams || {},
        label: "Set v"+specsPayloadSetVersion+": "+apiId
      });
    });
  });
  const mergedCatalog = setCatalog.concat(catalog.filter(p=>p.apiId && p.apiId !== "*"));
  const spec = swaggerSpecForUi(data, mergedCatalog);
  specsEnrichedDoc = spec;
  host.innerHTML = "";
  const el = document.createElement("div");
  el.id = "swagger-ui";
  host.appendChild(el);

  function showSwaggerEmpty(msg){
    host.innerHTML = '<div class="empty">'+(msg||"Swagger panel did not render.")+
      '<br/><button type="button" class="secondary" id="oas-swagger-retry">Refresh Swagger</button>'+
      ' <button type="button" class="secondary" onclick="setSpecsView(\'overview\')">Open overview</button></div>';
    const retry = document.getElementById("oas-swagger-retry");
    if(retry) retry.onclick = ()=> mountSwaggerUi(data);
  }

  function afterSwaggerReady(){
    watchSwaggerForActivePayload();
    const status = document.getElementById("oas-payload-status");
    const nSet = specsPayloadSetDetail && specsPayloadSetDetail.apis
      ? Object.keys(specsPayloadSetDetail.apis).length : 0;
    if(status){
      status.textContent = nSet
        ? "Set v"+(specsPayloadSetVersion||"?")+" ("+nSet+" API(s)) — edit Try it out, then Update set"
        : "Pick a set above, then edit Try it out";
    }
  }

  try {
    // Prefer BaseLayout — StandaloneLayout often paints a blank white panel when the
    // standalone preset/topbar path fails inside our embedded portal.
    const presets = [window.SwaggerUIBundle.presets.apis];
    if(window.SwaggerUIStandalonePreset) presets.push(window.SwaggerUIStandalonePreset);
    const uiOpts = {
      spec: spec,
      dom_id: "#swagger-ui",
      deepLinking: false,
      docExpansion: "list",
      defaultModelsExpandDepth: -1,
      defaultModelExpandDepth: 1,
      tryItOutEnabled: true,
      filter: true,
      displayRequestDuration: true,
      persistAuthorization: true,
      presets: presets,
      plugins: [window.SwaggerUIBundle.plugins.DownloadUrl],
      layout: "BaseLayout",
      requestInterceptor: (req)=>{
        if(token && req && req.headers){
          if(!req.headers.Authorization && !req.headers.authorization){
            req.headers.Authorization = "Bearer "+token;
          }
        }
        return req;
      },
      onComplete: ()=>{
        if(token && specsSwaggerUi){
          const schemes = ((spec.components||{}).securitySchemes) || {};
          Object.keys(schemes).forEach(name=>{
            try { specsSwaggerUi.preauthorizeApiKey(name, token); } catch(_){}
          });
          try {
            const authorized = {};
            Object.keys(schemes).forEach(name=>{
              const sch = schemes[name] || {};
              if(sch.type === "http" && String(sch.scheme||"").toLowerCase() === "bearer"){
                authorized[name] = { name, schema: sch, value: token };
              } else if(sch.type === "apiKey"){
                authorized[name] = { name, schema: sch, value: token };
              }
            });
            if(Object.keys(authorized).length && specsSwaggerUi.authActions){
              specsSwaggerUi.authActions.authorize(authorized);
            }
          } catch(_){}
        }
        afterSwaggerReady();
      }
    };
    specsSwaggerUi = window.SwaggerUIBundle(uiOpts);

    // If React tree stays empty (blank white), offer retry
    setTimeout(()=>{
      const root = document.getElementById("swagger-ui");
      if(!root) return;
      const hasOps = root.querySelector(".opblock, .opblock-tag-section, .information-container, .scheme-container");
      if(!hasOps){
        showSwaggerEmpty("Swagger stayed blank — click Refresh Swagger.");
      }
    }, 1800);
  } catch(e){
    showSwaggerEmpty("Swagger UI init failed: "+e.message);
  }
}
