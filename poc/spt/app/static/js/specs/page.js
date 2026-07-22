/* Specs — page shell (detail views / view switch) */
async function renderSpecDetail(){
  const main = document.getElementById("main");
  if(!selectedSpecService){
    main.innerHTML = '<div class="empty">Select a registered service to view OpenAPI / SPT config.</div>';
    return;
  }
  main.innerHTML = '<div class="empty">Loading OpenAPI…</div>';
  let data;
  let versions = specsVersionsCache[selectedSpecService] || { environments: [] };
  try {
    // Warm Swagger SDK + token while OpenAPI fetches (do not block on /versions)
    const warm = [];
    if(specsView === "swagger"){
      warm.push(ensureSwaggerSdk().catch(()=>null));
      warm.push(loadTryToken(false));
    }
    const needVersions = specsView === "versions" && !specsVersionsCache[selectedSpecService];
    const payloadP = loadSpecPayload(selectedSpecService, specsEnv);
    const versionsP = needVersions ? loadSpecVersions(selectedSpecService) : Promise.resolve(versions);
    data = await payloadP;
    if(needVersions) versions = await versionsP;
    await Promise.all(warm);
  } catch(e){
    main.innerHTML = '<div class="empty">Failed to load OpenAPI: '+esc(e.message)+'</div>';
    return;
  }
  const reg = data.registration || {};
  const tr = reg.trace || {};
  const targets = reg.targets || {};
  const envOpts = Object.keys(targets).filter(k=>!String(k).startsWith("public_"));
  if(!envOpts.length) envOpts.push("dev","preprod","prod");
  const ops = data.ok ? openapiOps(data.document) : [];

  const cards =
    cardHtml("Status", data.ok?'<span class="ok">ok</span>':'<span class="bad">error</span>')+
    card("Ops", data.operation_count!=null?String(data.operation_count):"—")+
    card("OpenAPI", data.openapi||"—")+
    card("Upstream", tryUpstreamHint(data));

  const targetRows = Object.keys(targets).map(k=>
    '<tr><td>'+esc(k)+'</td><td><code>'+esc(targets[k])+'</code></td></tr>'
  ).join("") || '<tr><td colspan="2" class="sub">No targets in spt.yaml</td></tr>';

  const versionRows = ((versions&&versions.environments)||[]).map(v=>
    '<tr><td>'+esc(v.environment)+'</td><td>'+(v.ok?'<span class="ok">ok</span>':'<span class="bad">fail</span>')+'</td><td>'+esc(v.version||"—")+'</td><td>'+esc(v.openapi||"—")+'</td><td class="sub">'+esc(v.operation_count!=null?String(v.operation_count):"—")+'</td><td class="sub">'+esc(v.error||v.openapi_url||"")+'</td></tr>'
  ).join("");

  const clusterOas = data.openapi_url_cluster || data.openapi_url || "";
  const clusterTarget = data.target_url || targets[specsEnv] || "";
  const rawJson = data.ok ? JSON.stringify(data.document || {}, null, 2) : "";

  main.innerHTML =
    '<h2 style="margin:.2rem 0 .5rem">'+esc(data.service)+
      ' <span class="sub">'+esc(specsEnv)+(data.ok?'':' · <span class="bad">error</span>')+'</span></h2>'+
    '<div class="toolbar">'+
      '<select id="specs-env">'+(envOpts.map(e=>'<option value="'+esc(e)+'"'+(e===specsEnv?' selected':'')+'>'+esc(e)+'</option>').join(""))+'</select>'+
      '<button type="button" class="'+(specsView==="overview"||specsView==="ops"?'':'secondary')+'" onclick="setSpecsView(\'overview\')">Overview</button>'+
      '<button type="button" class="'+(specsView==="swagger"?'':'secondary')+'" onclick="setSpecsView(\'swagger\')">Try APIs</button>'+
      '<button type="button" class="secondary" onclick="setSpecsView(\'raw\')">JSON</button>'+
      '<button type="button" class="secondary" onclick="setSpecsView(\'config\')">Config</button>'+
    '</div>'+
    (data.error?'<div class="section"><div class="section-b"><span class="bad">'+esc(data.error)+'</span></div></div>':'')+
    '<div id="specs-body"></div>';

  const body = document.getElementById("specs-body");
  if(specsView === "swagger"){
    body.innerHTML =
      '<div class="section oas-swagger-wrap">'+
        '<div class="section-h">Swagger UI · '+esc(data.service)+' · '+esc(specsEnv)+
          '<span class="oas-doc-actions">'+
            '<button type="button" class="secondary" id="oas-refresh-swagger" title="Remount Swagger if the panel is blank">Refresh Swagger</button>'+
            '<button type="button" class="secondary" id="oas-refresh-token">Refresh try-token</button>'+
          '</span></div>'+
        renderPayloadSetBar("oas-set-bar-swagger", { showLoad: false, showNewVersion: false })+
        '<div class="oas-payload-bar">'+
          '<label class="sub">Edit</label>'+
          '<select id="oas-payload-select" title="Active set APIs — pick one to Apply into Try it out"><option value="">Loading…</option></select>'+
          '<button type="button" id="oas-payload-apply" title="Fill Try it out from selection">Apply</button>'+
          '<button type="button" id="oas-payload-save" title="Write Try it out values into the current set version">Update set</button>'+
          '<button type="button" class="secondary" id="oas-payload-save-new" title="Clone set to a new version, then save this API">New version</button>'+
          '<span class="sub" id="oas-payload-status">Edit Try it out → Update set</span>'+
        '</div>'+
        '<div class="section-b" id="swagger-ui-host"></div>'+
      '</div>';
    const remountSwagger = async ()=>{
      try {
        delete specsCache[specsCacheKey(selectedSpecService, specsEnv)];
      } catch(_){}
      let fresh = data;
      try {
        fresh = await loadSpecPayload(selectedSpecService, specsEnv);
      } catch(_){}
      await mountSwaggerUi(fresh || data);
    };
    const refreshSwaggerBtn = document.getElementById("oas-refresh-swagger");
    if(refreshSwaggerBtn) refreshSwaggerBtn.onclick = ()=> remountSwagger();
    const refreshBtn = document.getElementById("oas-refresh-token");
    if(refreshBtn){
      refreshBtn.onclick = async ()=>{
        await loadTryToken(true);
        await remountSwagger();
      };
    }
    loadServicePayloadSets(selectedSpecService, false).then(()=>{
      const barHost = document.querySelector(".oas-set-bar-swagger");
      if(barHost){
        const wrap = document.createElement("div");
        wrap.innerHTML = renderPayloadSetBar("oas-set-bar-swagger", { showLoad: false, showNewVersion: false });
        barHost.replaceWith(wrap.firstChild);
      }
      bindPayloadSetBar();
      mountSwaggerUi(data);
    });
  } else if(specsView === "raw"){
    body.innerHTML =
      '<div class="section"><div class="section-h">Raw OpenAPI JSON ('+esc(specsEnv)+')'+
        '<span class="oas-doc-actions">'+
          '<button type="button" class="secondary" id="oas-copy-btn">Copy JSON</button>'+
          '<button type="button" class="secondary" id="oas-dl-btn">Download</button>'+
        '</span></div>'+
        '<div class="section-b"><pre class="oas-pre" id="oas-doc-pre">'+esc(rawJson||"(unavailable)")+'</pre></div></div>';
    const copyBtn = document.getElementById("oas-copy-btn");
    const dlBtn = document.getElementById("oas-dl-btn");
    if(copyBtn && rawJson){
      copyBtn.onclick = async ()=>{
        try { await navigator.clipboard.writeText(rawJson); copyBtn.textContent = "Copied"; }
        catch(_){ copyBtn.textContent = "Copy failed"; }
        setTimeout(()=>{ copyBtn.textContent = "Copy JSON"; }, 1500);
      };
    }
    if(dlBtn && rawJson){
      dlBtn.onclick = ()=>{
        const blob = new Blob([rawJson], {type:"application/json"});
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = selectedSpecService+"-"+specsEnv+"-openapi.json";
        a.click();
        URL.revokeObjectURL(a.href);
      };
    }
  } else if(specsView === "trace"){
    body.innerHTML = renderTracePanel(reg, data);
  } else if(specsView === "config"){
    body.innerHTML =
      '<div class="section"><div class="section-h">Registration (spt.yaml)</div><div class="section-b">'+
        '<table class="api-table"><tbody>'+
          '<tr><td>apiVersion</td><td>'+esc(reg.apiVersion||"—")+'</td></tr>'+
          '<tr><td>kind</td><td>'+esc(reg.kind||"—")+'</td></tr>'+
          '<tr><td>runtime</td><td>'+esc(reg.runtime||"—")+'</td></tr>'+
          '<tr><td>owners</td><td>'+esc(ownersText(reg.owners))+'</td></tr>'+
          '<tr><td>createdBy / updatedBy</td><td>'+esc(reg.createdBy||tr.created_by||"—")+' / '+esc(reg.updatedBy||tr.updated_by||"—")+'</td></tr>'+
          '<tr><td>openapi.path</td><td><code>'+esc((reg.openapi&&reg.openapi.path)||"—")+'</code></td></tr>'+
          '<tr><td>SPT fetch</td><td><code>'+esc(clusterOas||"—")+'</code></td></tr>'+
        '</tbody></table>'+
        '<h4>Targets</h4><table class="api-table"><thead><tr><th>Env</th><th>URL</th></tr></thead><tbody>'+targetRows+'</tbody></table>'+
        '<h4>Full registration JSON</h4><pre class="oas-pre">'+esc(JSON.stringify(reg,null,2))+'</pre>'+
      '</div></div>';
  } else if(specsView === "versions"){
    body.innerHTML =
      '<div class="section"><div class="section-h">OpenAPI versions by environment</div><div class="section-b">'+
        '<table class="api-table"><thead><tr><th>Env</th><th>Reachable</th><th>info.version</th><th>OpenAPI</th><th>Ops</th><th>Detail</th></tr></thead><tbody>'+
        versionRows+
        '</tbody></table>'+
      '</div></div>';
  } else if(specsView === "overview"){
    // Lightweight overview + per-API working request editor
    await Promise.all([
      loadServicePayloadCatalog(selectedSpecService),
      loadServicePayloadSets(selectedSpecService, false)
    ]);
    // Contract dropdown options (env + OpenAPI info.version)
    try {
      const verData = await loadSpecVersions(selectedSpecService);
      window._oasContractOptions = (verData && verData.environments) || [];
    } catch(_){
      window._oasContractOptions = [];
    }
    // Restore pinned contract if stored
    try {
      const raw = localStorage.getItem("spt_specs_contract_"+selectedSpecService);
      if(raw){
        const saved = JSON.parse(raw);
        if(saved && saved.env && !specsContractVersion){
          // Only apply version pin; env is already specsEnv from toolbar/url
          if(saved.env === specsEnv && saved.version) specsContractVersion = saved.version;
        }
      }
    } catch(_){}
    if(!specsContractVersion){
      specsContractVersion = (data.document && data.document.info && data.document.info.version)
        || data.version
        || null;
    }
    body.innerHTML = renderSwaggerOverview(data, ops);
    const filterEl = document.getElementById("oas-sw-filter");
    if(filterEl){
      filterEl.oninput = ()=>{
        specsSwaggerFilter = filterEl.value || "";
        clearTimeout(window._oasFilterT);
        window._oasFilterT = setTimeout(()=> renderSpecDetail(), 180);
      };
    }
    document.querySelectorAll(".oas-sw-op[data-op-key]").forEach(node=>{
      const head = node.querySelector(".oas-sw-head");
      if(!head) return;
      head.onclick = ()=>{
        const key = node.getAttribute("data-op-key");
        if(window.specsOpenAll){
          window.specsOpenAll = false;
          specsOpenOp = key;
        } else {
          specsOpenOp = (specsOpenOp === key) ? null : key;
        }
        renderSpecDetail();
      };
    });
    document.querySelectorAll(".oas-bar-full[data-op-key]").forEach(btn=>{
      btn.onclick = (e)=>{
        e.preventDefault();
        e.stopPropagation();
        openOverviewFullView(btn.getAttribute("data-op-key"), data);
      };
    });
    document.querySelectorAll(".oas-bar-edit[data-op-key]").forEach(btn=>{
      btn.onclick = (e)=>{
        e.preventDefault();
        e.stopPropagation();
        // Prefer full scrollable view for editing
        openOverviewFullView(btn.getAttribute("data-op-key"), data);
      };
    });
    document.querySelectorAll(".oas-bar-test[data-op-key]").forEach(btn=>{
      btn.onclick = (e)=>{
        e.preventDefault();
        e.stopPropagation();
        openOverviewFullView(btn.getAttribute("data-op-key"), data).then(()=>{
          const panel = document.querySelector("#oas-full-body .oas-payload-panel");
          const testBtn = panel && panel.querySelector(".oas-pv-test");
          if(testBtn) setTimeout(()=> testBtn.click(), 80);
        });
      };
    });
    const exp = document.getElementById("oas-expand-all");
    const col = document.getElementById("oas-collapse-all");
    if(exp){
      exp.onclick = ()=>{
        window.specsOpenAll = true;
        renderSpecDetail();
      };
    }
    if(col){
      col.onclick = ()=>{
        window.specsOpenAll = false;
        specsOpenOp = null;
        renderSpecDetail();
      };
    }
    await bindOverviewPayloadPanels(data);
    bindOverviewLoadSelection(data, ops);
  } else {
    // Default fallback → Swagger UI
    specsView = "swagger";
    body.innerHTML = '<div id="swagger-ui-host"></div>';
    mountSwaggerUi(data);
  }

  const envSel = document.getElementById("specs-env");
  if(envSel){
    envSel.onchange = async ()=>{
      specsEnv = envSel.value;
      // Contract versions are per-env — reset pin when env filter changes
      specsContractVersion = null;
      try {
        localStorage.setItem(
          "spt_specs_contract_"+selectedSpecService,
          JSON.stringify({ env: specsEnv, version: null })
        );
      } catch(_){}
      delete specsCache[specsCacheKey(selectedSpecService, specsEnv)];
      await renderSpecDetail();
    };
  }
}

function setSpecsView(v){
  if(v === "ops" || v === "swagger") specsView = "swagger";
  else if(v === "document") specsView = "overview";
  else specsView = v;
  try { syncPortalUrl({ replace: true }); } catch(_){}
  renderSpecDetail();
}
