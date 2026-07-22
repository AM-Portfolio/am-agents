/* Specs — Swagger SDK + try-token / proxy URL */
function staticUrl(path){
  const base = (window.SPT && SPT.static) ? SPT.static : (BASE ? BASE+"/static" : "/static");
  return base.replace(/\/$/,"") + (path.startsWith("/") ? path : "/"+path);
}

function loadCssOnce(href, id){
  return new Promise((resolve, reject)=>{
    if(id && document.getElementById(id)) return resolve();
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    if(id) link.id = id;
    link.onload = ()=> resolve();
    link.onerror = ()=> reject(new Error("CSS load failed: "+href));
    document.head.appendChild(link);
  });
}

function loadScriptOnce(src, id){
  return new Promise((resolve, reject)=>{
    if(id && document.getElementById(id)) return resolve();
    if(window.SwaggerUIBundle && id && id.indexOf("bundle")>=0) return resolve();
    const s = document.createElement("script");
    s.src = src;
    if(id) s.id = id;
    s.onload = ()=> resolve();
    s.onerror = ()=> reject(new Error("Script load failed: "+src));
    document.body.appendChild(s);
  });
}

async function ensureSwaggerSdk(){
  if(window.SwaggerUIBundle && window.SwaggerUIStandalonePreset) return true;
  const v = staticUrl("/vendor/swagger-ui");
  await loadCssOnce(v+"/swagger-ui.css", "spt-swagger-ui-css");
  await loadScriptOnce(v+"/swagger-ui-bundle.min.js", "spt-swagger-ui-bundle");
  await loadScriptOnce(v+"/swagger-ui-standalone-preset.min.js", "spt-swagger-ui-preset");
  return !!(window.SwaggerUIBundle && window.SwaggerUIStandalonePreset);
}

async function loadTryToken(force){
  const fresh = Date.now() - specsTryTokenAt < 4*60*1000;
  if(!force && specsTryToken && fresh) return specsTryToken;
  try {
    const data = await fetchJson("/api/platform/try-token");
    specsTryToken = data.access_token || null;
    specsTryTokenAt = Date.now();
  } catch(_){
    specsTryToken = null;
  }
  return specsTryToken;
}

function tryProxyServerUrl(service, env){
  const rel = api("/api/catalog/"+encodeURIComponent(service)+"/try/"+encodeURIComponent(env||"dev"));
  // Absolute same-origin URL so Swagger never hits cluster DNS / CORS / invalid schemes
  return window.location.origin + rel;
}

function tryUpstreamHint(data){
  const targets = ((data && data.registration)||{}).targets || {};
  const pub = targets["public_"+specsEnv] || targets.public || targets.public_dev;
  if(pub) return String(pub).replace(/\/$/,"");
  const t = data && data.target_url;
  if(t && String(t).indexOf(".svc.cluster.local") < 0) return String(t).replace(/\/$/,"");
  return "(cluster target via SPT)";
}

function swaggerSpecForUi(data, payloadCatalog){
  const doc = enrichOpenApiForTryIt(
    JSON.parse(JSON.stringify(data.document || {})),
    payloadCatalog || []
  );
  const service = data.service || selectedSpecService;
  const upstream = tryUpstreamHint(data);
  doc.servers = [{
    url: tryProxyServerUrl(service, specsEnv),
    description: "SPT proxy → "+upstream+" · env "+specsEnv
  }];
  return doc;
}
