let selectedApiId = null;
let selectedTraceIndex = null;

function apiStatusBadge(row){
  const ok = row.checks_passed;
  return '<span class="badge '+(ok?"passed":"failed")+'">'+(ok?"pass":"fail")+'</span>';
}

function compactBody(body){
  if(body==null || body==="") return "(empty)";
  if(typeof body === "object") return JSON.stringify(body);
  const s = String(body);
  try { return JSON.stringify(JSON.parse(s)); } catch(e){ return s; }
}

function prettyBody(body){
  if(body==null || body==="") return "(empty)";
  if(typeof body === "object") return JSON.stringify(body, null, 2);
  const s = String(body);
  try { return JSON.stringify(JSON.parse(s), null, 2); } catch(e){ return s; }
}

function formatBody(body){
  return (window._jsonPretty !== false) ? prettyBody(body) : compactBody(body);
}

function kvTable(obj){
  const entries = Object.entries(obj||{});
  if(!entries.length) return '<p class="sub">None</p>';
  return '<table class="kv"><tbody>'+entries.map(([k,v])=>'<tr><th>'+esc(k)+'</th><td>'+esc(typeof v==="object"?JSON.stringify(v):v)+'</td></tr>').join("")+'</tbody></table>';
}

function statusClass(code){
  const n = Number(code);
  return (n>=200 && n<300) ? "ok" : "bad";
}

function renderPostmanShell(traces){
  if(!traces.length){
    return '<p class="sub">No calls for this API'+(document.getElementById("api-failed-only")?.checked?' (failed only)':'')+'. Pick another API from the dropdown, or re-run the load test.</p>';
  }
  const list = traces.map((t, i)=>{
    const idx = t.index != null ? t.index : i;
    const callNo = i + 1; // number within selected API group
    const st = t.status!=null ? t.status : (t.checks_passed?"pass":"fail");
    const active = Number(selectedTraceIndex) === Number(idx);
    const pathHint = (t.path || t.url || "").toString();
    const shortPath = pathHint.length > 48 ? pathHint.slice(0, 48) + "…" : pathHint;
    return '<div class="pm-item '+(active?"active":"")+'" data-trace-index="'+esc(idx)+'" data-api-id="'+esc(t.api_id||"")+'">'+
      '<div><span class="sub">#'+esc(callNo)+'</span> '+apiDisplayName(t)+' '+apiStatusBadge(t)+'</div>'+
      '<div class="sub">'+esc(shortPath)+(t.duration_ms!=null?' · '+esc(t.duration_ms)+' ms':'')+' · HTTP '+esc(st)+'</div></div>';
  }).join("");
  return '<div class="pm">'+
    '<div class="pm-list" id="pm-list">'+list+'</div>'+
    '<div class="pm-detail" id="pm-detail"><div class="empty">Select a call to inspect request & response.</div></div>'+
  '</div>';
}

function highlightJson(text){
  const raw = formatBody(text);
  if(raw === "(empty)") return esc(raw);
  const e = esc(raw);
  if(window._jsonPretty === false) return e;
  return e
    .replace(/("(?:\\.|[^"\\])*")(\s*:)/g, '<span class="jk">$1</span>$2')
    .replace(/:\s*("(?:\\.|[^"\\])*")/g, ': <span class="js">$1</span>')
    .replace(/:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, ': <span class="jn">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="jb">$1</span>');
}

function jsonPane(title, body, copyKey){
  const formatted = formatBody(body);
  const bytes = formatted === "(empty)" ? 0 : formatted.length;
  const prettyOn = window._jsonPretty !== false;
  return '<div class="json-pane">'+
    '<div class="json-pane-h"><span class="label">'+esc(title)+' <span class="sub">('+esc(bytes)+' chars)</span></span>'+
      '<span class="actions">'+
        '<button type="button" class="secondary" data-beautify-toggle="1">'+(prettyOn?"Raw":"Beautify")+'</button>'+
        '<button type="button" class="secondary" data-copy-key="'+esc(copyKey)+'">Copy</button>'+
        '<button type="button" class="secondary" data-wrap-toggle="1">Wrap</button>'+
      '</span></div>'+
    '<div class="json-scroll"><pre data-json-pre="1">'+highlightJson(body)+'</pre></div></div>';
}

function renderTracePanel(trace){
  if(!trace) return '<div class="empty">Select an API to inspect request & response.</div>';
  const req = trace.request||{};
  const res = trace.response||{};
  const method = trace.method||"GET";
  const status = res.status;
  const ms = (trace.timings||{}).duration_ms;
  const tab = window._pmTab || "both";
  const prettyOn = window._jsonPretty !== false;
  window._copyBuffers = {
    request: prettyBody(req.body),
    response: prettyBody(res.body),
    headers: JSON.stringify({request: req.headers||{}, response: res.headers||{}}, null, 2),
    query: (trace.url&&trace.url.includes("?")) ? (trace.url.split("?")[1]||"") : ""
  };
  let bodyHtml = "";
  if(tab==="headers"){
    bodyHtml = '<div class="pm-split">'+
      '<div class="json-pane"><div class="json-pane-h"><span class="label">Request headers</span>'+
        '<span class="actions"><button type="button" class="secondary" data-copy-key="headers">Copy all</button></span></div>'+
        '<div class="json-scroll kv-scroll">'+kvTable(req.headers)+'</div></div>'+
      '<div class="json-pane"><div class="json-pane-h"><span class="label">Response headers</span>'+
        '<span class="actions"><button type="button" class="secondary" data-copy-key="headers">Copy all</button></span></div>'+
        '<div class="json-scroll kv-scroll">'+kvTable(res.headers)+'</div></div></div>';
  } else if(tab==="request"){
    bodyHtml = '<div class="pm-split">'+
      jsonPane("Request body", req.body, "request")+
      '<div class="json-pane"><div class="json-pane-h"><span class="label">Query / params</span>'+
        '<span class="actions"><button type="button" class="secondary" data-copy-key="query">Copy</button></span></div>'+
        '<div class="json-scroll"><pre>'+esc(window._copyBuffers.query||"(none)")+'</pre></div></div></div>';
  } else if(tab==="response"){
    bodyHtml = jsonPane("Response body", res.body, "response");
  } else {
    bodyHtml = '<div class="pm-split">'+
      jsonPane("Request body", req.body, "request")+
      jsonPane("Response body", res.body, "response")+
    '</div>';
  }
  return '<div class="pm-urlbar">'+
      '<span class="method pm-method '+esc(method)+'">'+esc(method)+'</span>'+
      '<span class="url" title="'+esc(trace.url||"")+'">'+esc(trace.url||"")+'</span>'+
      '<span class="status '+statusClass(status)+'">'+esc(status)+'</span>'+
      (ms!=null?'<span class="sub">'+esc(ms)+' ms</span>':'')+
      (trace.checks_passed!=null?' '+apiStatusBadge({checks_passed:trace.checks_passed}):'')+
    '</div>'+
    '<div class="toolbar" style="padding:.4rem .55rem;border-bottom:1px solid var(--border);margin:0;flex-shrink:0">'+
      '<button type="button" onclick="saveCurrentPayload()">Save payload</button>'+
      '<select id="payload-version-select" onchange="loadPayloadVersion()" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:5px;font-size:.75rem;min-width:160px">'+
        '<option value="">Library versions…</option></select>'+
      '<span class="sub" id="payload-lib-hint">Save to reuse / version this API request</span>'+
    '</div>'+
    '<div class="pm-tabs">'+
      '<button class="'+(tab==="both"?"active":"")+'" data-pm-tab="both">Request | Response</button>'+
      '<button class="'+(tab==="response"?"active":"")+'" data-pm-tab="response">Response</button>'+
      '<button class="'+(tab==="request"?"active":"")+'" data-pm-tab="request">Request</button>'+
      '<button class="'+(tab==="headers"?"active":"")+'" data-pm-tab="headers">Headers</button>'+
      '<button type="button" class="secondary" style="margin-left:auto" onclick="toggleBeautifyAll()">'+(prettyOn?"Show raw":"Beautify JSON")+'</button>'+
      '<button type="button" class="secondary" onclick="copyActiveJson()">Copy JSON</button>'+
    '</div>'+
    '<div class="pm-body">'+bodyHtml+'</div>';
}

function copyText(text){
  const t = text == null ? "" : String(text);
  if(navigator.clipboard && navigator.clipboard.writeText){
    return navigator.clipboard.writeText(t).then(()=>true).catch(()=>false);
  }
  const ta = document.createElement("textarea");
  ta.value = t; document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); } catch(e){}
  document.body.removeChild(ta);
  return Promise.resolve(true);
}

function copyActiveJson(){
  const tab = window._pmTab || "both";
  const buf = window._copyBuffers || {};
  let text = "";
  if(tab==="request") text = buf.request || "";
  else if(tab==="headers") text = buf.headers || "";
  else if(tab==="both") text = JSON.stringify({request: tryParseJson(buf.request), response: tryParseJson(buf.response)}, null, 2);
  else text = buf.response || "";
  copyText(text).then(()=>{
    const hint = document.getElementById("payload-lib-hint");
    if(hint){ const prev = hint.textContent; hint.textContent = "Copied to clipboard"; setTimeout(()=>{ if(hint) hint.textContent = prev; }, 1200); }
  });
}

function tryParseJson(s){
  if(s==null || s==="(empty)") return null;
  try { return JSON.parse(s); } catch(e){ return s; }
}

function toggleBeautifyAll(){
  window._jsonPretty = !(window._jsonPretty !== false);
  const detail = document.getElementById("pm-detail");
  if(detail && window._lastTrace){
    detail.innerHTML = renderTracePanel(window._lastTrace);
    bindPmTabs(detail);
  }
}

function bindJsonPaneActions(root){
  root.querySelectorAll("[data-copy-key]").forEach(btn=>{
    btn.onclick = ()=>{
      const key = btn.getAttribute("data-copy-key");
      const text = (window._copyBuffers||{})[key] || "";
      copyText(text).then(()=>{
        const prev = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(()=>{ btn.textContent = prev.indexOf("all")>=0 ? "Copy all" : "Copy"; }, 1000);
      });
    };
  });
  root.querySelectorAll("[data-wrap-toggle]").forEach(btn=>{
    btn.onclick = ()=>{
      const pane = btn.closest(".json-pane");
      const pre = pane && pane.querySelector("[data-json-pre]");
      if(!pre) return;
      const on = pre.classList.toggle("wrap");
      btn.textContent = on ? "No wrap" : "Wrap";
    };
  });
  root.querySelectorAll("[data-beautify-toggle]").forEach(btn=>{
    btn.onclick = ()=> toggleBeautifyAll();
  });
}

async function loadRunApis(runId, opts){
  opts = opts || {};
  const params = new URLSearchParams();
  if(opts.failedOnly) params.set("failed_only","true");
  if(opts.q) params.set("q", opts.q);
  const q = params.toString();
  return (await fetchJson("/api/runs/"+runId+"/apis"+(q?"?"+q:""))).apis || [];
}

async function loadRunTraces(runId, opts){
  opts = opts || {};
  const params = new URLSearchParams();
  if(opts.failedOnly) params.set("failed_only","true");
  if(opts.apiId) params.set("api_id", opts.apiId);
  const q = params.toString();
  return (await fetchJson("/api/runs/"+runId+"/traces"+(q?"?"+q:""))).traces || [];
}

function bindPostmanList(){
  const list = document.getElementById("pm-list");
  if(!list) return;
  list.querySelectorAll("[data-trace-index]").forEach(node=>{
    node.addEventListener("click", ()=> selectTrace(Number(node.getAttribute("data-trace-index"))));
  });
}

async function selectTrace(index){
  selectedTraceIndex = index;
  window._pmTab = window._pmTab || "both";
  if(window._jsonPretty == null) window._jsonPretty = true;
  if(!selectedRunId) return;
  const detail = document.getElementById("pm-detail");
  if(detail) detail.innerHTML = '<div class="empty">Loading…</div>';
  const row = (window._runTraces || []).find(t => Number(t.index) === Number(index));
  if(row) selectedApiId = row.api_id;
  document.querySelectorAll("#pm-list .pm-item").forEach(node=>{
    node.classList.toggle("active", Number(node.getAttribute("data-trace-index")) === Number(index));
  });
  document.querySelectorAll("#results-table tbody tr").forEach(node=>{
    node.classList.toggle("active", selectedApiId && node.getAttribute("data-api-id")===selectedApiId);
  });
  try {
    const data = await fetchJson("/api/runs/"+selectedRunId+"/traces/"+encodeURIComponent(index));
    window._lastTrace = data.trace;
    if(detail){
      detail.innerHTML = renderTracePanel(data.trace);
      bindPmTabs(detail);
    }
    await refreshPayloadVersions();
    const insp = document.getElementById("api-inspector-wrap");
    if(insp) insp.scrollIntoView({behavior:"smooth", block:"nearest"});
  } catch(e){
    if(detail) detail.innerHTML = '<div class="empty">Could not load this call trace.</div>';
  }
}

function populateApiFilter(apis){
  const sel = document.getElementById("api-filter");
  const wrap = document.getElementById("api-filter-wrap");
  const hint = document.getElementById("api-filter-hint");
  if(!sel) return;
  const cur = selectedApiId || "";
  if(wrap) wrap.style.display = "";
  if(hint){ hint.style.display = "none"; hint.textContent = ""; }
  if(!apis.length){
    sel.innerHTML = '<option value="">No APIs</option>';
    return;
  }
  sel.innerHTML = apis.map(a=>{
    const calls = a.request_count != null ? Number(a.request_count) : null;
    const fail = Number(a.fail_count || 0);
    let label = apiPlainName(a);
    if(calls != null) label += " · " + calls + " calls";
    if(fail) label += " · " + fail + " fail";
    return '<option value="'+esc(a.api_id)+'">'+esc(label)+'</option>';
  }).join("");
  if(cur && apis.some(a => a.api_id === cur)) sel.value = cur;
  else {
    selectedApiId = apis[0].api_id;
    sel.value = selectedApiId;
  }
}

function onApiFilterChange(){
  const sel = document.getElementById("api-filter");
  selectedApiId = sel && sel.value ? sel.value : null;
  selectedTraceIndex = null;
  if(selectedRunId) refreshApiSection(selectedRunId);
}

async function selectApi(apiId){
  selectedApiId = apiId;
  selectedTraceIndex = null;
  const sel = document.getElementById("api-filter");
  if(sel && apiId) sel.value = apiId;
  document.querySelectorAll("#results-table tbody tr").forEach(node=>{
    node.classList.toggle("active", node.getAttribute("data-api-id")===apiId);
  });
  if(selectedRunId) await refreshApiSection(selectedRunId);
}

async function currentRunService(){
  if(!selectedRunId) return "am-analysis";
  const r = await fetchJson("/api/runs/"+selectedRunId);
  return r.service || "am-analysis";
}

async function refreshPayloadVersions(){
  const sel = document.getElementById("payload-version-select");
  if(!sel || !selectedApiId) return;
  try {
    const service = await currentRunService();
    const data = await fetchJson("/api/payloads/"+encodeURIComponent(service)+"/"+encodeURIComponent(selectedApiId));
    const rows = data.payloads || [];
    sel.innerHTML = '<option value="">Library versions…</option>'+
      rows.map(p=>'<option value="'+esc(p.name)+'@'+esc(p.version)+'">'+esc(p.name)+' v'+esc(p.version)+(p.status!=null?' · HTTP '+esc(p.status):'')+'</option>').join("");
    const hint = document.getElementById("payload-lib-hint");
    if(hint) hint.textContent = rows.length ? (rows.length+" saved version(s)") : "Save to reuse / version this API request";
  } catch(e){ /* ignore */ }
}

async function saveCurrentPayload(){
  if(!selectedRunId || !selectedApiId) return alert("Select a run API first");
  const name = prompt("Payload name (versions auto-bump):", "default");
  if(!name) return;
  try {
    const saved = await fetchJson(
      "/api/runs/"+selectedRunId+"/apis/"+encodeURIComponent(selectedApiId)+"/save-payload",
      {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({name})}
    );
    const hint = document.getElementById("payload-lib-hint");
    if(hint) hint.textContent = "Saved "+saved.name+" v"+saved.version;
    await refreshPayloadVersions();
  } catch(e){
    alert("Save failed: "+e.message);
  }
}

async function loadPayloadVersion(){
  const sel = document.getElementById("payload-version-select");
  if(!sel || !sel.value || !selectedApiId) return;
  const [name, ver] = sel.value.split("@");
  try {
    const service = await currentRunService();
    const p = await fetchJson(
      "/api/payloads/"+encodeURIComponent(service)+"/"+encodeURIComponent(selectedApiId)+"/"+encodeURIComponent(name)+
      (ver?("?version="+encodeURIComponent(ver)):"")
    );
    const req = p.request||{};
    const res = p.response||{};
    const fakeTrace = {
      api_id: p.api_id,
      method: req.method,
      url: (p.meta&&p.meta.url) || req.path,
      path: req.path,
      request: req,
      response: res,
      timings: {duration_ms: (p.meta||{}).duration_ms},
      checks_passed: (p.meta||{}).checks_passed
    };
    window._lastTrace = fakeTrace;
    window._pmTab = "request";
    const detail = document.getElementById("pm-detail");
    if(detail){
      detail.innerHTML = renderTracePanel(fakeTrace);
      bindPmTabs(detail);
      await refreshPayloadVersions();
      const sel2 = document.getElementById("payload-version-select");
      if(sel2) sel2.value = name+"@"+p.version;
      const hint = document.getElementById("payload-lib-hint");
      if(hint) hint.textContent = "Viewing library "+p.name+" v"+p.version+" (not live run)";
    }
  } catch(e){
    alert("Load failed: "+e.message);
  }
}

function bindPmTabs(detail){
  detail.querySelectorAll("[data-pm-tab]").forEach(btn=>{
    btn.onclick = ()=>{
      window._pmTab = btn.getAttribute("data-pm-tab");
      detail.innerHTML = renderTracePanel(window._lastTrace);
      bindPmTabs(detail);
      bindJsonPaneActions(detail);
    };
  });
  bindJsonPaneActions(detail);
}

async function refreshApiSection(runId){
  const failedOnly = document.getElementById("api-failed-only")?.checked;
  const allApis = await loadRunApis(runId, {});
  window._runApisAll = allApis;
  const apis = failedOnly
    ? allApis.filter(a => !a.checks_passed || Number(a.fail_count||0) > 0)
    : allApis;
  window._runApis = apis;
  populateApiFilter(allApis.length ? allApis : apis);
  if(!selectedApiId && allApis.length) selectedApiId = allApis[0].api_id;

  const traces = await loadRunTraces(runId, {
    failedOnly,
    apiId: selectedApiId || undefined,
  });
  window._runTraces = traces;

  const results = document.getElementById("api-results-wrap");
  if(results){
    results.innerHTML = renderResultsTable(apis);
    bindResultsTable();
  }
  const wrap = document.getElementById("api-inspector-wrap");
  if(wrap){
    wrap.innerHTML = renderPostmanShell(traces);
    bindPostmanList();
    if(selectedTraceIndex != null && traces.some(t => Number(t.index) === Number(selectedTraceIndex))){
      selectTrace(selectedTraceIndex);
    } else if(traces.length){
      selectTrace(traces[0].index);
    }
  }
}
