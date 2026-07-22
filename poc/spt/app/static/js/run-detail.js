function apiDisplayName(a){
  const method = (a.method || "GET").toUpperCase();
  let label = String(a.name || a.path || a.api_id || "");
  // Avoid "GET GET /path" when catalog name already includes the method
  label = label.replace(new RegExp("^"+method+"\\s+", "i"), "").trim();
  if(!label || label === method) label = a.path || a.api_id || "—";
  return '<span class="pm-method '+esc(method)+'">'+esc(method)+'</span> '+esc(label);
}

/** Plain text for <select> options (HTML is not rendered inside options). */
function apiPlainName(a){
  const method = (a.method || "GET").toUpperCase();
  let label = String(a.name || a.path || a.api_id || "");
  label = label.replace(new RegExp("^"+method+"\\s+", "i"), "").trim();
  if(!label || label === method) label = a.path || a.api_id || "—";
  return method + " " + label;
}

function liveStateBadge(state){
  if(state==="completed" || state==="done") return '<span class="badge done">done</span>';
  if(state==="calling") return '<span class="badge calling">calling…</span>';
  if(state==="in_progress") return '<span class="badge running">in progress</span>';
  if(state==="pending") return '<span class="badge pending">pending</span>';
  return '<span class="badge running">running</span>';
}

function resolveLiveApis(r){
  const live = r.live || {};
  const byApi = live.by_api || {};
  const total = live.total_iterations != null ? live.total_iterations : ((r.payloads_used||{}).bench_run||{}).iterations;
  let rows = r.api_summary || [];
  if(!rows.length){
    rows = (editPayloads.apis_tested||[]).map(a=>({
      api_id: a.id||a.api_id,
      name: a.name||a.id,
      method: a.method||"GET",
      path: a.path||"",
      live_state: "pending",
      status: "pending",
      request_count: 0
    }));
  }
  return rows.map(a=>{
    const aid = String(a.api_id||a.id||"");
    const tracked = byApi[aid] || {};
    const calls = a.request_count != null ? Number(a.request_count) : Number(tracked.calls||0);
    let state = a.live_state;
    if(!state){
      if(aid && aid === live.last_api_id) state = "calling";
      else if(total && calls >= total) state = "completed";
      else if(calls > 0) state = "in_progress";
      else state = "pending";
    }
    return {...a, api_id: aid, request_count: calls, live_state: state};
  });
}

function renderLiveApiRows(r){
  const apis = resolveLiveApis(r);
  const total = (r.live||{}).total_iterations != null ? (r.live||{}).total_iterations : ((r.payloads_used||{}).bench_run||{}).iterations;
  if(!apis.length){
    return '<tr><td colspan="5" class="sub">Waiting for API catalog…</td></tr>';
  }
  return apis.map(a=>{
    const target = total != null ? total : "—";
    const calls = a.request_count != null ? a.request_count : 0;
    return '<tr data-api-id="'+esc(a.api_id)+'" class="'+(a.live_state==="calling"?"active":"")+'">'+
      '<td>'+apiDisplayName(a)+'</td>'+
      '<td class="num">'+esc(a.path||"—")+'</td>'+
      '<td class="num">'+esc(calls)+(target!=="—"?(" / "+esc(target)):"")+'</td>'+
      '<td>'+liveStateBadge(a.live_state)+'</td>'+
      '<td class="sub">'+esc(a.live_state==="calling"?"now":(a.live_state==="completed"?"finished":(a.live_state==="in_progress"?"streaming":"queued")))+'</td></tr>';
  }).join("");
}

function renderRunningResults(r){
  const live = r.live || {};
  const rows = resolveLiveApis(r);
  const done = live.completed_iterations != null ? live.completed_iterations : 0;
  const total = live.total_iterations != null ? live.total_iterations : ((r.payloads_used||{}).bench_run||{}).iterations;
  const hits = live.api_hits != null ? live.api_hits : null;
  const apiCount = live.api_count || rows.length || 0;
  let pct = live.pct != null ? live.pct : 0;
  if(!pct && hits != null && total && apiCount){
    pct = Math.min(99, Math.round(100 * hits / (total * apiCount)));
  } else if(!pct && total && done){
    pct = Math.min(99, Math.round(100 * done / total));
  }
  const elapsed = live.elapsed_s != null ? live.elapsed_s : (r.started_at ? Math.max(0, Math.round((Date.now()-new Date(r.started_at).getTime())/1000)) : 0);
  const completedN = rows.filter(a=>a.live_state==="completed").length;
  const activeN = rows.filter(a=>a.live_state==="calling"||a.live_state==="in_progress").length;
  const pendingN = rows.filter(a=>a.live_state==="pending").length;
  return '<div class="live-progress" id="live-progress-panel">'+
      '<div class="live-bar"><span style="width:'+esc(Math.max(pct, elapsed>0?2:0))+'%"></span></div>'+
      '<div class="live-stats">'+
        '<span>Progress <strong id="live-pct">'+esc(pct)+'%</strong></span>'+
        '<span>Iterations <strong id="live-iters">'+esc(done)+(total!=null?(" / "+esc(total)):"")+'</strong></span>'+
        (hits!=null?'<span>API calls <strong id="live-hits">'+esc(hits)+'</strong></span>':'')+
        '<span>Elapsed <strong id="live-elapsed-stat">'+esc(elapsed)+'s</strong></span>'+
        (live.vus!=null?'<span>Target VUs <strong>'+esc(live.vus)+'</strong></span>':'')+
        '<span>APIs <strong>'+esc(rows.length||apiCount||"—")+'</strong></span>'+
      '</div>'+
      '<p class="sub" style="margin:.55rem 0 .25rem" id="live-msg">'+esc(live.message||"k6 running…")+'</p>'+
      '<p class="live-api-msg" id="live-api-summary">Streaming: <strong class="ok-cell">'+esc(completedN)+' done</strong> · <strong>'+esc(activeN)+' in progress</strong> · <strong>'+esc(pendingN)+' pending</strong>'+
        (live.last_api_id?' · now <strong>'+esc(live.last_api_id)+'</strong>':'')+'</p>'+
      '<div style="overflow:auto"><table class="results-table" id="live-api-table">'+
        '<thead><tr><th>API</th><th>Path</th><th class="num">Calls</th><th>State</th><th>Stream</th></tr></thead>'+
        '<tbody id="live-api-tbody">'+renderLiveApiRows(r)+'</tbody></table></div>'+
    '</div>';
}

function renderResultsTable(apis){
  const rows = apis || [];
  if(!rows.length) return '<p class="sub">No API results yet.</p>';
  let totalCalls = 0, totalFail = 0, totalPass = 0;
  rows.forEach(a=>{
    const calls = Number(a.request_count != null ? a.request_count : ((a.pass_count||a.check_passes||0)+(a.fail_count||a.check_fails||0))) || 0;
    const fail = Number(a.fail_count != null ? a.fail_count : (a.check_fails||0)) || 0;
    const pass = Number(a.pass_count != null ? a.pass_count : (a.check_passes!=null?a.check_passes:(calls-fail))) || 0;
    totalCalls += calls; totalFail += fail; totalPass += pass;
  });
  const failPctAll = totalCalls ? Math.round((totalFail/totalCalls)*1000)/10 : 0;
  const body = rows.map(a=>{
    const calls = Number(a.request_count != null ? a.request_count : ((a.pass_count||a.check_passes||0)+(a.fail_count||a.check_fails||0))) || (a.status!=null?1:0);
    const fail = Number(a.fail_count != null ? a.fail_count : (a.check_fails||0)) || (a.checks_passed===false?1:0);
    const pass = Number(a.pass_count != null ? a.pass_count : (a.check_passes!=null?a.check_passes:Math.max(0,calls-fail))) || 0;
    const failPct = calls ? Math.round((fail/calls)*1000)/10 : 0;
    const avg = a.duration_ms!=null && a.duration_ms!=="" ? Number(a.duration_ms).toFixed(1) : "—";
    const p90 = a.duration_p90_ms!=null && a.duration_p90_ms!=="" ? Number(a.duration_p90_ms).toFixed(1) : "—";
    const http = a.status!=null && a.status!=="" ? a.status : "—";
    return '<tr class="'+(a.api_id===selectedApiId?"active":"")+'" data-api-id="'+esc(a.api_id)+'">'+
      '<td>'+apiDisplayName(a)+'</td>'+
      '<td class="num">'+esc(http)+'</td>'+
      '<td class="num">'+esc(calls)+'</td>'+
      '<td class="num ok-cell">'+esc(pass)+'</td>'+
      '<td class="num '+(fail?'fail-cell':'')+'">'+esc(fail)+'</td>'+
      '<td class="num '+(failPct?'fail-cell':'')+'">'+esc(failPct)+'%</td>'+
      '<td class="num">'+esc(avg)+'</td>'+
      '<td class="num">'+esc(p90)+'</td>'+
      '<td>'+apiStatusBadge(a)+'</td></tr>';
  }).join("");
  return '<div class="results-sum">'+
      '<span>APIs <strong>'+rows.length+'</strong></span>'+
      '<span>Calls <strong>'+totalCalls+'</strong></span>'+
      '<span>Pass <strong class="ok-cell">'+totalPass+'</strong></span>'+
      '<span>Fail <strong class="'+(totalFail?'fail-cell':'')+'">'+totalFail+'</strong></span>'+
      '<span>Fail rate <strong class="'+(failPctAll?'fail-cell':'')+'">'+failPctAll+'%</strong></span>'+
    '</div>'+
    '<div style="overflow:auto"><table class="results-table" id="results-table">'+
      '<thead><tr><th>API</th><th class="num">HTTP</th><th class="num">Calls</th><th class="num">Pass</th><th class="num">Fail</th><th class="num">Fail%</th><th class="num">Avg ms</th><th class="num">p90 ms</th><th>Result</th></tr></thead>'+
      '<tbody>'+body+'</tbody></table></div>'+
    '<p class="sub" style="margin-top:.4rem">Click a row → inspector lists every call for that API (pass/fail + full request/response).</p>';
}

function bindResultsTable(){
  const table = document.getElementById("results-table");
  if(!table) return;
  table.querySelectorAll("tbody tr[data-api-id]").forEach(node=>{
    node.addEventListener("click", ()=> selectApi(node.getAttribute("data-api-id")));
  });
}

function showRunDetail(r, opts){
  opts = opts || {};
  if(!opts.preserveApi){
    selectedApiId = null;
    selectedTraceIndex = null;
    window._pmTab = "both";
    window._jsonPretty = true;
    window._lastTrace = null;
  }
  const gurl = r.grafana_url || grafanaRunUrl(r);
  const embed = r.grafana_embed_url || grafanaEmbedUrl(r) || (gurl ? gurl + "&kiosk=tv" : "");
  const metrics = r.metrics_summary || {};
  const hasMetrics = Object.keys(metrics).length > 0;
  let grafanaBlock;
  if(r.status === "running"){
    grafanaBlock = '<p class="sub grafana-empty">Grafana unlocks when the run finishes.</p>';
  } else if(!hasMetrics){
    // No Influx/summary data — keep section compact (don't mount a blank iframe)
    grafanaBlock = '<p class="sub grafana-empty">No chart data for this run.'+
      (gurl ? ' <a href="'+esc(gurl)+'" target="_blank" rel="noopener">Open Grafana ↗</a>' : '')+
      '</p>';
  } else if(embed){
    grafanaBlock =
      '<details class="grafana-panel">'+
        '<summary>Grafana charts <span class="sub">(click to expand)</span></summary>'+
        '<iframe class="grafana" src="'+esc(embed)+'" title="Grafana" loading="lazy"></iframe>'+
        (gurl ? '<p class="sub" style="margin:.35rem 0 0"><a href="'+esc(gurl)+'" target="_blank" rel="noopener">Open full dashboard ↗</a></p>' : '')+
      '</details>';
  } else {
    grafanaBlock = '<p class="sub grafana-empty">Grafana URL unavailable.</p>';
  }
  const steps = (r.steps||[]).map(s=>'<li><span class="'+(s.status==="pass"?"ok":"fail")+'">'+esc(s.status)+'</span> '+esc(s.step)+(s.error?' — '+esc(s.error):'')+'</li>').join("");
  const profile = r.run_profile || "load";
  const bench = editPayloads.bench_run || {};
  const auth = editPayloads.auth_env || ((r.config_snapshot||{}).payloads||{}).auth_env || {};
  const params = editPayloads.run_params || {};
  const apisTested = (editPayloads.apis_tested||[]);
  const vus = params.vus != null ? params.vus : bench.vus;
  const duration = params.duration || bench.duration;
  const iterations = params.iterations != null ? params.iterations : bench.iterations;
  const loadLabel = iterations != null
    ? (vus||"—")+" VU × "+iterations+" iter"
    : (vus||"—")+" VU for "+(duration||"—");
  const live = r.live || {};
  const elapsed = r.started_at ? Math.max(0, Math.round((Date.now()-new Date(r.started_at).getTime())/1000)) : 0;
  const apiRows = r.api_summary || [];
  const done = live.completed_iterations != null ? live.completed_iterations : 0;
  const total = live.total_iterations != null ? live.total_iterations : null;
  const pct = live.pct != null ? live.pct : (total ? Math.min(99, Math.round(100*done/total)) : 0);
  const liveBanner = r.status === "running"
    ? '<div id="live-banner" style="background:#0c4a6e;border:1px solid #38bdf8;border-radius:6px;padding:.55rem .7rem;margin-bottom:.65rem;font-size:.82rem">'+
        '<strong>Running…</strong> '+esc(live.message||"k6 in progress")+
        ' · <span id="live-elapsed">'+elapsed+'s</span>'+
        (live.phase?' · phase: '+esc(live.phase):'')+
        (pct!=null?' · <strong>'+esc(pct)+'%</strong>':'')+
        (done!=null && total!=null?' · '+esc(done)+'/'+esc(total)+' iters':'')+
        '<div class="live-progress" style="margin-top:.45rem"><div class="live-bar"><span id="live-bar-fill" style="width:'+esc(pct)+'%"></span></div></div>'+
        '<div class="sub" style="margin-top:.35rem">Live progress updates every ~1s. Final pass/fail &amp; latency appear when k6 completes.</div></div>'
    : (r.error ? '<div style="background:#450a0a;border:1px solid var(--fail);border-radius:6px;padding:.55rem .7rem;margin-bottom:.65rem;font-size:.82rem">'+esc(r.error)+'</div>' : '');
  document.getElementById("main").innerHTML =
    '<h2 style="margin:0 0 .5rem">'+esc(r.config_name)+' '+runOutcomeBadge(r)+'<span class="pill">'+esc(profile)+'</span></h2>'+
    (r.status!=="running" && (r.api_pass_count!=null||r.api_fail_count!=null)
      ? '<div class="sub" style="margin:-.25rem 0 .55rem">APIs <strong>'+esc(r.api_count!=null?r.api_count:((r.api_pass_count||0)+(r.api_fail_count||0)))+'</strong> · <span class="ok-cell">'+esc(r.api_pass_count||0)+' pass</span> · <span class="fail-cell">'+esc(r.api_fail_count||0)+' fail</span></div>'
      : '')+
    liveBanner+
    '<div class="toolbar">'+
      (r.status==="running"
        ? '<button type="button" onclick="stopSelectedRun(\''+r.id+'\')" style="background:#7f1d1d;border:1px solid var(--fail)">Stop run</button>'
        : '<button onclick="rerunRun(\''+r.id+'\')">Re-run</button>')+
      '<button class="secondary" onclick="runDebug(\''+r.id+'\')">Run debug (1 call)</button>'+
      '<button class="secondary" onclick="saveFromRun(\''+r.id+'\')">Save as config</button>'+
      '<button class="secondary" type="button" onclick="toggleSidebar()">Toggle list</button>'+
      '<a class="btn secondary" href="'+esc(gurl)+'" target="_blank">Open in Grafana ↗</a>'+
      '<a class="btn secondary" href="'+api("/api/runs/"+r.id+"/export")+'" target="_blank">Export JSON</a>'+
    '</div>'+
    '<details class="run-params" id="run-params-box"'+(localStorage.getItem("spt_params_open")!=="0"?" open":"")+'>'+
      '<summary>Run parameters <span class="sub">click to minimize</span></summary>'+
      '<div class="section-b"><div class="cards" style="margin:0">'+
        card("Service", r.service)+
        card("Env", r.environment)+
        card("API version", r.openapi_version||((r.payloads_used||{}).run_params||{}).openapi_version||"—")+
        card("Target", r.target_url)+
        card("Profile", profile)+
        card("Load", loadLabel)+
        card("VUs", vus!=null?vus:"—")+
        card("Duration", duration||"—")+
        card("Iterations / calls", iterations!=null?iterations:(profile==="debug"?"1":"—"))+
        card("APIs", r.api_count!=null?r.api_count:apiRows.length)+
        card("User", auth.username||"—")+
        card("User ID", auth.user_id||"—")+
        card("Identity", auth.identity_url||"—")+
        card("Auth", auth.authenticated===true?"JWT OK":(auth.authenticated===false?"missing":(auth.username?"configured":"—")))+
        card("Triggered by", r.triggered_by||params.triggered_by||"—")+
        card("Runner", r.runner||"k6")+
        cardHtml("Run ID", gurl
          ? '<a href="'+esc(gurl)+'" target="_blank" rel="noopener" title="Open this run in Grafana">'+esc(r.id)+' ↗</a>'
          : esc(r.id))+
        card("Started", fmtT(r.started_at))+
        card("Finished", fmtT(r.finished_at))+
        card("Max VU cap", params.max_vus_cap!=null?params.max_vus_cap:"—")+
      '</div></div></details>'+
    '<div class="section"><div class="section-h">API results <span class="sub">calls · pass/fail · latency per endpoint</span></div><div class="section-b" id="api-results-wrap">'+
      (r.status==="running"?renderRunningResults(r):renderResultsTable(apiRows))+
    '</div></div>'+
    '<div class="section"><div class="section-h">API inspector <span class="sub">One row per call · filter by API</span></div><div class="section-b">'+
      '<div class="toolbar">'+
        '<span id="api-filter-wrap"><label class="sub">API <select id="api-filter" onchange="onApiFilterChange()" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.35rem;border-radius:5px;min-width:220px;max-width:360px"></select></label></span>'+
        '<span class="sub" id="api-filter-hint" style="display:none"></span>'+
        '<label class="sub"><input type="checkbox" id="api-failed-only" onchange="refreshApiSection(\''+r.id+'\')"/> Failed only</label>'+
      '</div>'+
      '<div id="api-inspector-wrap">'+(r.status==="running"
        ? '<div class="empty compact">Inspector unlocks when the run finishes (per-call request/response).</div>'
        : '<div class="empty compact">Loading call traces…</div>')+'</div></div></div>'+
    '<div class="section"><div class="section-h">Metrics <span class="sub">Grafana locked to this run</span></div><div class="section-b">'+metricStrip(r.metrics_summary)+
      grafanaBlock+'</div></div>'+
    '<div class="section"><div class="section-h">Load settings (next run)</div><div class="section-b">'+
      '<label class="sub">bench (VUs / duration / iterations)</label><textarea class="code" id="payload-editor" oninput="syncPayloadEdit()" style="min-height:90px"></textarea>'+
      (apisTested.length?'<p class="sub" style="margin-top:.5rem">APIs in catalog for this run: '+apisTested.map(a=>esc((a.method||"GET")+" "+(a.path||a.id))).join(" · ")+'</p>':'')+
    '</div></div>'+
    '<details class="advanced"><summary>Advanced / steps</summary><ul class="steps">'+steps+'</ul></details>';
  window._payloadTab = "bench";
  syncPayloadEditor();
  bindResultsTable();
  const paramsBox = document.getElementById("run-params-box");
  if(paramsBox){
    paramsBox.addEventListener("toggle", ()=>{
      localStorage.setItem("spt_params_open", paramsBox.open ? "1" : "0");
    });
  }
  updateStopButton(r.status === "running");
  if(r.status !== "running"){
    refreshApiSection(r.id);
  }
}

function stopRunWatch(){
  if(runPollTimer){ clearInterval(runPollTimer); runPollTimer = null; }
}

function startRunWatch(runId){
  stopRunWatch();
  runPollTimer = setInterval(async ()=>{
    if(selectedRunId !== runId){ stopRunWatch(); return; }
    try {
      const r = await fetchJson("/api/runs/"+runId);
      editPayloads = JSON.parse(JSON.stringify(r.payloads_used||{}));
      const keepApi = selectedApiId;
      // Prefer light live-panel update to avoid full-page flicker
      const panel = document.getElementById("live-progress-panel");
      if(r.status === "running" && panel){
        const live = r.live || {};
        const done = live.completed_iterations != null ? live.completed_iterations : 0;
        const total = live.total_iterations != null ? live.total_iterations : null;
        const hits = live.api_hits;
        const apiCount = live.api_count || (r.api_summary||[]).length || 0;
        let pct = live.pct != null ? live.pct : 0;
        if(!pct && hits != null && total && apiCount) pct = Math.min(99, Math.round(100*hits/(total*apiCount)));
        else if(!pct && total && done) pct = Math.min(99, Math.round(100*done/total));
        const elapsed = live.elapsed_s != null ? live.elapsed_s : (r.started_at ? Math.max(0, Math.round((Date.now()-new Date(r.started_at).getTime())/1000)) : 0);
        const bar = panel.querySelector(".live-bar > span");
        if(bar) bar.style.width = Math.max(pct, elapsed>0?2:0) + "%";
        const set = (id, val)=>{ const el=document.getElementById(id); if(el) el.textContent = val; };
        set("live-pct", pct + "%");
        set("live-iters", done + (total!=null?(" / "+total):""));
        if(hits!=null) set("live-hits", String(hits));
        set("live-elapsed-stat", elapsed + "s");
        set("live-msg", live.message || "k6 running…");
        const tbody = document.getElementById("live-api-tbody");
        if(tbody){
          // Rebuild when catalog arrives or per-API stream changes
          if(!(r.api_summary||[]).length && !(editPayloads.apis_tested||[]).length){
            showRunDetail(r, {preserveApi: true});
          } else {
            tbody.innerHTML = renderLiveApiRows(r);
            const liveApis = resolveLiveApis(r);
            const completedN = liveApis.filter(a=>a.live_state==="completed").length;
            const activeN = liveApis.filter(a=>a.live_state==="calling"||a.live_state==="in_progress").length;
            const pendingN = liveApis.filter(a=>a.live_state==="pending").length;
            const sum = document.getElementById("live-api-summary");
            if(sum){
              sum.innerHTML = 'Streaming: <strong class="ok-cell">'+esc(completedN)+' done</strong> · <strong>'+esc(activeN)+' in progress</strong> · <strong>'+esc(pendingN)+' pending</strong>'+
                (live.last_api_id?' · now <strong>'+esc(live.last_api_id)+'</strong>':'');
            }
          }
        }
        const banner = document.getElementById("live-banner");
        if(banner){
          const fill = document.getElementById("live-bar-fill");
          if(fill) fill.style.width = Math.max(pct, elapsed>0?2:0) + "%";
          const elap = document.getElementById("live-elapsed");
          if(elap) elap.textContent = elapsed + "s";
        }
        runs = runs.map(x => x.id===runId ? {...x, status: r.status, payloads_used: r.payloads_used} : x);
        renderList();
      } else {
        showRunDetail(r, {preserveApi: true});
        if(keepApi) selectedApiId = keepApi;
      }
      if(r.status !== "running"){
        stopRunWatch();
        updateStopButton(false);
        await refreshRuns();
        await selectRun(runId);
      } else {
        updateStopButton(true);
      }
    } catch(e){ /* keep polling */ }
  }, 1000);
}
