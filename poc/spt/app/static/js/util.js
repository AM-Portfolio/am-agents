/* SPT portal - shared utils + shell state */
const BASE = (window.SPT && window.SPT.root) || (document.querySelector('meta[name="api-base"]') || {}).content || "";
const GRAFANA = (window.SPT && window.SPT.grafana) || "";
function api(p){ return BASE + (p.startsWith("/") ? p : "/"+p); }
function esc(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;"); }
function badge(st){
  if(st==="passed") return '<span class="badge passed">passed</span>';
  if(st==="running") return '<span class="badge running">running</span>';
  if(st==="partial") return '<span class="badge partial">partial</span>';
  if(st==="cancelled") return '<span class="badge cancelled">cancelled</span>';
  return '<span class="badge failed">'+(st||"failed")+'</span>';
}

function runOutcomeBadge(r){
  if(r.status === "running") return badge("running");
  if(r.status === "cancelled") return badge("cancelled");
  const pass = r.api_pass_count != null ? Number(r.api_pass_count) : null;
  const fail = r.api_fail_count != null ? Number(r.api_fail_count) : null;
  if(pass != null && fail != null && (pass > 0 || fail > 0)){
    if(fail === 0) return '<span class="badge passed">'+pass+' pass</span>';
    if(pass === 0) return '<span class="badge failed">'+fail+' fail</span>';
    return '<span class="badge partial">'+pass+' pass · '+fail+' fail</span>';
  }
  return badge(r.status);
}

function runOutcomeLine(r){
  const pass = r.api_pass_count != null ? Number(r.api_pass_count) : null;
  const fail = r.api_fail_count != null ? Number(r.api_fail_count) : null;
  const total = r.api_count != null ? Number(r.api_count) : ((pass||0)+(fail||0));
  if(pass == null && fail == null) return "";
  return '<div class="outcome">APIs '+esc(total)+' · <span class="ok">'+esc(pass||0)+' pass</span> · <span class="bad">'+esc(fail||0)+' fail</span></div>';
}

function fmtT(iso){ if(!iso) return "—"; try{return new Date(iso).toLocaleString();}catch(e){return iso||"—";} }

/** Client-side Grafana deep-link (mirrors app/grafana_links.py). */
function grafanaRunUrl(r){
  const base = (GRAFANA || "").replace(/\/$/,"");
  if(!base || !r) return "";
  const pad = 30 * 60 * 1000;
  let fromMs = r.started_at ? Date.parse(r.started_at) : Date.now();
  let toMs = r.finished_at ? Date.parse(r.finished_at) : (r.started_at ? Date.parse(r.started_at) : Date.now());
  if(!Number.isFinite(fromMs)) fromMs = Date.now();
  if(!Number.isFinite(toMs)) toMs = fromMs;
  fromMs -= pad;
  toMs += pad;
  if(toMs <= fromMs) toMs = fromMs + 60 * 60 * 1000;
  const q = new URLSearchParams({
    orgId: "1",
    from: String(fromMs),
    to: String(toMs),
    "var-service": r.service || "All",
    "var-environment": r.environment || "All",
    "var-run_id": r.id || "All",
    "var-api_id": "All"
  });
  return base + "/d/spt-load-testing/spt-load-testing?" + q.toString();
}
function grafanaEmbedUrl(r){
  const u = grafanaRunUrl(r);
  return u ? u + "&kiosk=tv" : "";
}
