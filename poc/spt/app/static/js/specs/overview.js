/* Specs — Overview request builder + sidebar */
function ownersText(owners){
  if(Array.isArray(owners)) return owners.join(", ") || "—";
  return owners || "—";
}

function renderSpecsSidebar(){
  const el = document.getElementById("sidebar-list");
  const filterSvc = (document.getElementById("f-service") && document.getElementById("f-service").value) || "";
  const filterQ = ((document.getElementById("f-q") && document.getElementById("f-q").value) || "").trim().toLowerCase();
  let rows = filterSvc ? specsList.filter(s=>s.id===filterSvc) : specsList.slice();
  if(filterQ){
    rows = rows.filter(s=>{
      const hay = [s.id, s.label, s.runtime, s.source, ownersText(s.owners)].join(" ").toLowerCase();
      return hay.indexOf(filterQ) >= 0;
    });
  }
  if(!rows.length){
    el.innerHTML = '<div class="empty">No services match filters.<br/><span class="sub">Clear service/search or check catalog.</span></div>';
    return;
  }
  el.innerHTML = rows.map(s=>{
    const active = s.id === selectedSpecService ? " active" : "";
    const envs = Object.keys(s.targets||{}).filter(k=>!String(k).startsWith("public_"));
    const tr = s.trace || {};
    const who = tr.registered_by || ownersText(s.owners);
    const when = tr.updated_at ? String(tr.updated_at).slice(0,10) : "";
    return '<div class="item'+active+'" data-spec-id="'+esc(s.id)+'">'+
      '<div><strong>'+esc(s.label||s.id)+'</strong> <span class="badge '+(s.source==="registration"?"done":"pending")+'">'+esc(s.source||"")+'</span></div>'+
      '<div class="sub">'+esc(s.runtime||"?")+' · '+esc(who||"—")+(when?' · '+esc(when):'')+'</div>'+
      '<div class="sub">'+esc(envs.join("/")||"—")+'</div>'+
    '</div>';
  }).join("");
  el.querySelectorAll("[data-spec-id]").forEach(node=>{
    node.addEventListener("click", ()=> selectSpec(node.getAttribute("data-spec-id")));
  });
}

function openapiOps(doc){
  const paths = (doc && doc.paths) || {};
  const rows = [];
  const methods = ["get","post","put","patch","delete","head","options"];
  Object.keys(paths).sort().forEach(path=>{
    const item = paths[path] || {};
    methods.forEach(m=>{
      const op = item[m];
      if(!op || typeof op !== "object") return;
      rows.push({
        method: m.toUpperCase(),
        path: path,
        operationId: op.operationId || "",
        summary: op.summary || op.operationId || (m.toUpperCase()+" "+path),
        tags: op.tags || [],
        security: op.security,
        parameters: op.parameters || item.parameters || [],
        requestBody: op.requestBody || null,
        responses: op.responses || {}
      });
    });
  });
  return rows;
}

function methodClass(m){
  return String(m||"GET").toUpperCase();
}

function renderOpDetail(op){
  if(!op) return '<div class="empty">Select an operation.</div>';
  const params = (op.parameters||[]).map(p=>{
    return '<tr><td>'+esc(p.name||"")+'</td><td>'+esc(p.in||"")+'</td><td>'+esc(p.required?"yes":"no")+'</td><td class="sub">'+esc(((p.schema||{}).type)||"")+'</td></tr>';
  }).join("") || '<tr><td colspan="4" class="sub">None</td></tr>';
  const responses = Object.keys(op.responses||{}).map(code=>{
    const r = op.responses[code] || {};
    return '<tr><td>'+esc(code)+'</td><td>'+esc(r.description||"")+'</td></tr>';
  }).join("") || '<tr><td colspan="2" class="sub">None</td></tr>';
  return '<div class="oas-op-detail">'+
    '<div class="oas-op-title"><span class="pm-method '+methodClass(op.method)+'">'+esc(op.method)+'</span> <code>'+esc(op.path)+'</code></div>'+
    '<p class="sub">'+esc(op.summary||"")+(op.operationId?' · <code>'+esc(op.operationId)+'</code>':'')+'</p>'+
    (op.tags&&op.tags.length?'<p class="sub">tags: '+op.tags.map(t=>esc(t)).join(", ")+'</p>':'')+
    '<h4>Parameters</h4><table class="api-table"><thead><tr><th>Name</th><th>In</th><th>Req</th><th>Type</th></tr></thead><tbody>'+params+'</tbody></table>'+
    (op.requestBody?'<h4>Request body</h4><pre class="oas-pre">'+esc(JSON.stringify(op.requestBody,null,2))+'</pre>':'')+
    '<h4>Responses</h4><table class="api-table"><thead><tr><th>Code</th><th>Description</th></tr></thead><tbody>'+responses+'</tbody></table>'+
  '</div>';
}

function opKey(op){ return (op.method||"")+" "+(op.path||""); }

function groupOpsByTag(ops){
  const groups = {};
  const order = [];
  (ops||[]).forEach(op=>{
    const tags = (op.tags && op.tags.length) ? op.tags : ["default"];
    tags.forEach(tag=>{
      if(!groups[tag]){ groups[tag] = []; order.push(tag); }
      // avoid dup if multi-tagged into same list once per tag is correct for swagger
      if(!groups[tag].some(x=>opKey(x)===opKey(op))) groups[tag].push(op);
    });
  });
  return order.filter((t,i)=>order.indexOf(t)===i).map(tag=>({ tag, ops: groups[tag]||[] }));
}

function schemaPreview(schema, depth){
  depth = depth || 0;
  if(!schema || typeof schema !== "object" || depth > 3) return "";
  if(schema.$ref) return '<code>'+esc(String(schema.$ref).split("/").pop())+'</code>';
  const t = schema.type || (schema.properties ? "object" : (schema.items ? "array" : ""));
  if(schema.enum) return esc(t||"enum")+' ['+schema.enum.map(v=>esc(String(v))).join(", ")+']';
  if(t === "array") return "array&lt;"+schemaPreview(schema.items||{}, depth+1)+"&gt;";
  if(schema.properties){
    const keys = Object.keys(schema.properties).slice(0,12);
    return "object { "+keys.map(k=>{
      const req = (schema.required||[]).indexOf(k)>=0 ? "*" : "";
      return esc(k)+req+": "+schemaPreview(schema.properties[k], depth+1);
    }).join(", ")+(Object.keys(schema.properties).length>12?" …":"")+" }";
  }
  return esc(t || "any");
}

function prettyJson(v){
  if(v == null) return "";
  try { return JSON.stringify(v, null, 2); } catch(_){ return String(v); }
}

function renderParamFieldRow(p, wr){
  const name = p.name || "";
  const hints = paramValueHints(p);
  const val = resolveParamValue(p, wr);
  const req = !!p.required;
  const schema = p.schema || {};
  const typeLabel = schema.type || (Array.isArray(schema.enum) ? "enum" : "string");
  let input;
  if(hints.length && hints.length <= 12){
    const opts = ['<option value="">— select —</option>'].concat(hints.map(h=>{
      const sel = String(val)===String(h) ? " selected" : "";
      return '<option value="'+esc(String(h))+'"'+sel+'>'+esc(String(h))+'</option>';
    })).join("");
    // Also allow free text via datalist+input when not strict enum-only from schema
    if(Array.isArray(schema.enum) && schema.enum.length){
      input = '<select class="oas-pv-field" data-param-name="'+esc(name)+'" data-param-in="'+esc(p.in||"query")+'">'+opts+'</select>';
    } else {
      const listId = "dl-"+sptApiSlug(name+"-"+p.in);
      input = '<input class="oas-pv-field" list="'+esc(listId)+'" data-param-name="'+esc(name)+'" data-param-in="'+esc(p.in||"query")+'" value="'+esc(val)+'" placeholder="paste or pick…"/>'+
        '<datalist id="'+esc(listId)+'">'+hints.map(h=>'<option value="'+esc(String(h))+'"></option>').join("")+'</datalist>';
    }
  } else {
    input = '<input class="oas-pv-field" type="text" data-param-name="'+esc(name)+'" data-param-in="'+esc(p.in||"query")+'" value="'+esc(val)+'" placeholder="'+(req?"required — paste value":"optional")+'"/>';
  }
  const chips = hints.length
    ? '<div class="oas-pv-chips">'+hints.slice(0,8).map(h=>
        '<button type="button" class="oas-pv-chip" data-chip-for="'+esc(name)+'" data-chip-value="'+esc(String(h))+'">'+esc(String(h))+'</button>'
      ).join("")+'</div>'
    : "";
  return '<tr class="'+(req?"oas-pv-req":"")+'">'+
    '<td><code>'+esc(name)+'</code>'+(req?' <span class="bad">*</span>':'')+'</td>'+
    '<td class="sub">'+esc(p.in||"")+'</td>'+
    '<td class="sub">'+esc(typeLabel)+'</td>'+
    '<td class="oas-pv-val">'+input+chips+'</td>'+
    '<td class="sub">'+esc(p.description||"")+'</td>'+
  '</tr>';
}

function renderOverviewPayloadPanel(op, doc){
  const apiId = primaryApiId(op);
  const registeredId = opRegisteredInSet(op);
  const wr = workingRequestForOp(op, doc);
  const inSet = !!registeredId || apiRegisteredInSet(apiId);
  const setVer = specsPayloadSetVersion;
  const params = (op.parameters||[]).filter(p=>p && p.name && (p.in==="path" || p.in==="query"));
  const method = String(op.method||"GET").toUpperCase();
  const canHaveBody = !/^(GET|HEAD)$/.test(method);
  const setBadge = inSet
    ? '<span class="pill oas-pv-active">v'+esc(String(setVer))+'</span>'
    : '<span class="pill oas-pv-missing">v'+esc(String(setVer!=null?setVer:"?"))+'</span>';

  const initialForm = (wr.body && typeof wr.body === "object" && !Array.isArray(wr.body))
    ? Object.keys(wr.body).map(k=>'<tr><td><input class="oas-pv-form-key" value="'+esc(k)+'"/></td><td><input class="oas-pv-form-val" value="'+esc(String(wr.body[k]))+'"/></td><td><button type="button" class="secondary oas-pv-form-del">×</button></td></tr>').join("")
    : '<tr><td><input class="oas-pv-form-key" placeholder="Key"/></td><td><input class="oas-pv-form-val" placeholder="Value"/></td><td><button type="button" class="secondary oas-pv-form-del">×</button></td></tr>';

  const bodyHtml = canHaveBody
    ? '<div class="oas-block oas-pm-body">'+
        '<div class="oas-block-h">Body</div>'+
        '<div class="oas-pv-body-modes">'+
          '<label><input type="radio" name="body-mode-'+esc(apiId)+'" class="oas-pv-body-mode" value="none"/> none</label>'+
          '<label><input type="radio" name="body-mode-'+esc(apiId)+'" class="oas-pv-body-mode" value="raw" checked/> raw JSON</label>'+
          '<label><input type="radio" name="body-mode-'+esc(apiId)+'" class="oas-pv-body-mode" value="urlencoded"/> x-www-form-urlencoded</label>'+
          '<label><input type="radio" name="body-mode-'+esc(apiId)+'" class="oas-pv-body-mode" value="formdata"/> form-data</label>'+
          '<label><input type="radio" name="body-mode-'+esc(apiId)+'" class="oas-pv-body-mode" value="binary"/> binary / file</label>'+
        '</div>'+
        '<div class="oas-pv-body-pane" data-mode="raw">'+
          '<div class="toolbar" style="margin:.25rem 0">'+
            '<button type="button" class="secondary oas-pv-copy-body">Copy</button>'+
            '<button type="button" class="secondary oas-pv-format-body">Format</button>'+
          '</div>'+
          '<textarea class="oas-pv-body" rows="6" placeholder="{ }">'+esc(prettyJson(wr.body))+'</textarea>'+
        '</div>'+
        '<div class="oas-pv-body-pane" data-mode="urlencoded" hidden>'+
          '<table class="api-table oas-pv-form-table"><thead><tr><th>Key</th><th>Value</th><th></th></tr></thead><tbody class="oas-pv-form-body">'+
            initialForm+
          '</tbody></table>'+
          '<button type="button" class="secondary oas-pv-form-add">Add row</button>'+
        '</div>'+
        '<div class="oas-pv-body-pane" data-mode="formdata" hidden>'+
          '<table class="api-table oas-pv-form-table"><thead><tr><th>Key</th><th>Type</th><th>Value</th><th></th></tr></thead>'+
          '<tbody class="oas-pv-fd-body">'+
            '<tr>'+
              '<td><input class="oas-pv-fd-key" placeholder="Key" value="file"/></td>'+
              '<td><select class="oas-pv-fd-type"><option value="file" selected>File</option><option value="text">Text</option></select></td>'+
              '<td class="oas-pv-fd-valcell"><input type="file" class="oas-pv-fd-file"/></td>'+
              '<td><button type="button" class="secondary oas-pv-fd-del">×</button></td>'+
            '</tr>'+
          '</tbody></table>'+
          '<button type="button" class="secondary oas-pv-fd-add">Add row</button>'+
        '</div>'+
        '<div class="oas-pv-body-pane" data-mode="binary" hidden>'+
          '<input type="file" class="oas-pv-binary-file"/>'+
          '<span class="sub oas-pv-binary-meta"></span>'+
        '</div>'+
        '<div class="oas-pv-body-pane" data-mode="none" hidden><p class="sub">No body will be sent.</p></div>'+
      '</div>'
    : '<input type="hidden" class="oas-pv-body" value=""/><input type="hidden" class="oas-pv-body-mode-fixed" value="none"/>';

  return '<div class="oas-block oas-payload-panel oas-pm" data-api-id="'+esc(apiId)+'" data-op-method="'+esc(op.method)+'" data-op-path="'+esc(op.path)+'" data-tested="0">'+
    '<div class="toolbar oas-pv-toolbar">'+
      '<span class="pm-method '+methodClass(op.method)+'">'+esc(op.method)+'</span>'+
      '<code class="oas-pm-path-preview">'+esc(op.path)+'</code> '+setBadge+
      '<input class="oas-pv-name" type="text" value="'+esc(wr.name||"working")+'" placeholder="name" title="Payload name"/>'+
      '<label class="sub" title="Clone set to next version"><input type="checkbox" class="oas-pv-bump-set"/> new set ver</label>'+
      '<button type="button" class="oas-pv-test">Test</button>'+
      '<button type="button" class="oas-pv-save">Save</button>'+
      '<button type="button" class="secondary oas-pv-copy-curl">curl</button>'+
      '<button type="button" class="secondary oas-pv-full">Full</button>'+
      '<span class="sub oas-pv-status"></span>'+
    '</div>'+
    (params.length
      ? '<div class="oas-block"><table class="api-table oas-pm-params"><thead><tr><th>Name</th><th>In</th><th>Type</th><th>Value</th></tr></thead><tbody>'+
          params.map(p=>{
            // reuse row but drop description col for compactness
            const row = renderParamFieldRow(p, wr);
            return row.replace(/<td class="sub">[^<]*<\/td><\/tr>/, '</tr>');
          }).join("")+
        '</tbody></table></div>'
      : '')+
    bodyHtml+
    '<div class="oas-block oas-pm-response" hidden>'+
      '<div class="oas-block-h">Response <span class="oas-pm-status-code"></span> <button type="button" class="secondary oas-pv-copy-resp">Copy</button></div>'+
      '<pre class="oas-pre oas-pm-resp-body"></pre>'+
    '</div>'+
  '</div>';
}

function parsePanelJson(ta, fallback){
  const raw = (ta && ta.value != null) ? String(ta.value).trim() : "";
  if(!raw) return fallback;
  try { return JSON.parse(raw); } catch(e){ throw new Error("Invalid JSON: "+e.message); }
}

function readOverviewPanel(panel){
  const apiId = panel.getAttribute("data-api-id");
  const method = panel.getAttribute("data-op-method") || "GET";
  const pathTemplate = panel.getAttribute("data-op-path") || "/";
  const nameEl = panel.querySelector(".oas-pv-name");
  const name = ((nameEl && nameEl.value) || "working").trim() || "working";
  const query = {};
  const pathParams = {};
  panel.querySelectorAll(".oas-pv-field").forEach(el=>{
    const pname = el.getAttribute("data-param-name");
    const pin = el.getAttribute("data-param-in");
    const v = el.value;
    if(!pname || v == null || String(v).trim() === "") return;
    if(pin === "path") pathParams[pname] = v;
    else query[pname] = v;
  });
  const modeEl = panel.querySelector(".oas-pv-body-mode:checked") || panel.querySelector(".oas-pv-body-mode-fixed");
  const bodyMode = modeEl ? (modeEl.value || modeEl.getAttribute("value") || "raw") : "raw";
  let body = null;
  let contentType = null;
  if(bodyMode === "none"){
    body = null;
  } else if(bodyMode === "urlencoded"){
    body = {};
    panel.querySelectorAll(".oas-pv-form-body tr").forEach(tr=>{
      const k = tr.querySelector(".oas-pv-form-key");
      const v = tr.querySelector(".oas-pv-form-val");
      const key = k && String(k.value||"").trim();
      if(!key) return;
      body[key] = v ? v.value : "";
    });
    contentType = "application/x-www-form-urlencoded";
  } else {
    const bodyEl = panel.querySelector("textarea.oas-pv-body");
    if(bodyEl && String(bodyEl.value||"").trim()){
      body = parsePanelJson(bodyEl, null);
    }
    contentType = "application/json";
  }
  return {
    apiId: apiId,
    name: name,
    method: method,
    path: pathTemplate,
    pathTemplate: pathTemplate,
    resolvedPath: buildResolvedPath(pathTemplate, pathParams),
    query: query,
    pathParams: pathParams,
    body: body,
    bodyMode: bodyMode,
    contentType: contentType
  };
}

function setPanelTested(panel, ok){
  panel.setAttribute("data-tested", ok ? "1" : "0");
  // Save stays always enabled; only mark status
}

function fillPanelFields(panel, query, pathParams, body){
  panel.querySelectorAll(".oas-pv-field").forEach(el=>{
    const pname = el.getAttribute("data-param-name");
    const pin = el.getAttribute("data-param-in");
    let v = "";
    if(pin === "path" && pathParams && pathParams[pname] != null) v = String(pathParams[pname]);
    else if(pin !== "path" && query && query[pname] != null) v = String(query[pname]);
    el.value = v;
  });
  const bodyEl = panel.querySelector("textarea.oas-pv-body");
  if(bodyEl) bodyEl.value = prettyJson(body);
  setPanelTested(panel, false);
  updatePathPreview(panel);
}

function updatePathPreview(panel){
  const preview = panel.querySelector(".oas-pm-path-preview");
  if(!preview) return;
  try {
    const draft = readOverviewPanel(panel);
    const qs = Object.keys(draft.query||{}).map(k=>encodeURIComponent(k)+"="+encodeURIComponent(draft.query[k])).join("&");
    preview.textContent = draft.resolvedPath + (qs ? "?"+qs : "");
  } catch(_){
    preview.textContent = panel.getAttribute("data-op-path") || "/";
  }
}

function panelToCurl(draft, service, env, token){
  const base = tryProxyServerUrl(service, env).replace(/\/$/,"");
  const qs = Object.keys(draft.query||{}).map(k=>encodeURIComponent(k)+"="+encodeURIComponent(draft.query[k])).join("&");
  const url = base + draft.resolvedPath + (qs ? "?"+qs : "");
  const parts = ["curl -sS -X "+String(draft.method||"GET").toUpperCase()+" "+JSON.stringify(url)];
  if(token) parts.push("-H "+JSON.stringify("Authorization: Bearer "+token));
  if(draft.bodyMode === "binary" && draft.fileMeta){
    parts.push("-H "+JSON.stringify("Content-Type: "+(draft.contentType||"application/octet-stream")));
    parts.push("--data-binary @"+JSON.stringify(draft.fileMeta.name||"file"));
  } else if(draft.bodyMode === "formdata"){
    const fields = (draft.body && draft.body.fields) || [];
    fields.forEach(f=>{
      if(f.type === "file") parts.push("-F "+JSON.stringify(f.key+"=@"+(f.name||"file")));
      else parts.push("-F "+JSON.stringify(f.key+"="+(f.value||"")));
    });
  } else if(draft.bodyMode !== "none" && draft.body != null && !/^(get|head)$/i.test(draft.method||"")){
    if(draft.bodyMode === "urlencoded"){
      parts.push("-H "+JSON.stringify("Content-Type: application/x-www-form-urlencoded"));
      const form = Object.keys(draft.body||{}).map(k=>encodeURIComponent(k)+"="+encodeURIComponent(draft.body[k])).join("&");
      parts.push("-d "+JSON.stringify(form));
    } else {
      parts.push("-H "+JSON.stringify("Content-Type: application/json"));
      parts.push("-d "+JSON.stringify(JSON.stringify(draft.body)));
    }
  }
  return parts.join(" \\\n  ");
}

function buildOverviewRequestInit(draft, headers){
  const init = { method: String(draft.method||"GET").toUpperCase(), headers: headers };
  if(/^(get|head)$/i.test(draft.method||"") || draft.bodyMode === "none"){
    return init;
  }
  if(draft.bodyMode === "binary"){
    if(!draft.body) throw new Error("Choose a file to upload");
    headers["Content-Type"] = draft.contentType || "application/octet-stream";
    init.body = draft.body;
    return init;
  }
  if(draft.bodyMode === "formdata"){
    const fd = new FormData();
    const fields = (draft.body && draft.body.fields) || [];
    let hasFile = false;
    fields.forEach(f=>{
      if(f.type === "file"){
        if(f.file){ fd.append(f.key, f.file, f.name || f.file.name); hasFile = true; }
      } else {
        fd.append(f.key, f.value != null ? f.value : "");
      }
    });
    if(!fields.length) throw new Error("Add form-data fields");
    if(!hasFile && fields.every(f=>f.type==="file")) throw new Error("Choose a file");
    // Let browser set multipart boundary
    delete headers["Content-Type"];
    init.body = fd;
    return init;
  }
  if(draft.bodyMode === "urlencoded" || draft.contentType === "application/x-www-form-urlencoded"){
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    init.body = Object.keys(draft.body||{}).map(k=>encodeURIComponent(k)+"="+encodeURIComponent(draft.body[k])).join("&");
    return init;
  }
  if(draft.body != null){
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(draft.body);
  }
  return init;
}

function serializeDraftForSave(draft){
  // Do not persist File blobs into payload sets — store metadata only
  if(draft.bodyMode === "binary"){
    return {
      method: String(draft.method||"GET").toUpperCase(),
      path: draft.path,
      query: draft.query,
      path_params: draft.pathParams,
      body: null,
      content_type: draft.contentType || null,
      body_mode: "binary",
      file: draft.fileMeta || null
    };
  }
  if(draft.bodyMode === "formdata"){
    const fields = ((draft.body && draft.body.fields) || []).map(f=>{
      if(f.type === "file") return { key: f.key, type: "file", name: f.name, size: f.size };
      return { key: f.key, type: "text", value: f.value };
    });
    return {
      method: String(draft.method||"GET").toUpperCase(),
      path: draft.path,
      query: draft.query,
      path_params: draft.pathParams,
      body: { fields: fields },
      content_type: "multipart/form-data",
      body_mode: "formdata"
    };
  }
  return {
    method: String(draft.method||"GET").toUpperCase(),
    path: draft.path,
    query: draft.query,
    path_params: draft.pathParams,
    body: draft.body,
    content_type: draft.contentType || null,
    body_mode: draft.bodyMode || null
  };
}

async function runOverviewPanelTest(panel, setStatus){
  const service = selectedSpecService;
  if(!service) throw new Error("No service selected");
  const draft = readOverviewPanel(panel);
  // Validate required empty fields
  const missing = [];
  panel.querySelectorAll("tr.oas-pv-req .oas-pv-field").forEach(el=>{
    if(!String(el.value||"").trim()) missing.push(el.getAttribute("data-param-name"));
  });
  if(missing.length) throw new Error("Required: "+missing.join(", "));
  if(/\{[^}]+\}/.test(draft.resolvedPath)) throw new Error("Fill all path params: "+draft.resolvedPath);

  setStatus("Testing…");
  setPanelTested(panel, false);
  const token = await loadTryToken(false);
  const base = tryProxyServerUrl(service, specsEnv).replace(/\/$/,"");
  const qs = Object.keys(draft.query||{}).map(k=>encodeURIComponent(k)+"="+encodeURIComponent(draft.query[k])).join("&");
  const url = base + draft.resolvedPath + (qs ? "?"+qs : "");
  const headers = { "Accept": "application/json", "Accept-Encoding": "identity" };
  if(token) headers.Authorization = "Bearer "+token;
  const init = buildOverviewRequestInit(draft, headers);
  const t0 = Date.now();
  const resp = await fetch(url, init);
  const ms = Date.now() - t0;
  const buf = new Uint8Array(await resp.arrayBuffer());
  let text = "";
  // If proxy still returned gzip (1f 8b), inflate in the browser
  if(buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b && typeof DecompressionStream === "function"){
    try {
      const ds = new DecompressionStream("gzip");
      const stream = new Blob([buf]).stream().pipeThrough(ds);
      text = await new Response(stream).text();
    } catch(_){
      text = new TextDecoder("utf-8", { fatal: false }).decode(buf);
    }
  } else {
    text = new TextDecoder("utf-8", { fatal: false }).decode(buf);
  }
  let pretty = text;
  try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch(_){
    if(/[\uFFFD]/.test(text) || /[\x00-\x08\x0e-\x1f]/.test(text.slice(0,80))){
      pretty = "(binary/compressed response — restart SPT so try-proxy can decode gzip)\n"+
        "bytes="+buf.length+" content-type="+(resp.headers.get("content-type")||"?");
    }
  }
  const respBox = panel.querySelector(".oas-pm-response");
  const codeEl = panel.querySelector(".oas-pm-status-code");
  const bodyEl = panel.querySelector(".oas-pm-resp-body");
  if(respBox) respBox.hidden = false;
  if(codeEl){
    codeEl.textContent = resp.status+" · "+ms+"ms";
    codeEl.className = "oas-pm-status-code "+(resp.ok?"ok":"bad");
  }
  if(bodyEl) bodyEl.textContent = pretty || "(empty)";
  panel._lastTest = { ok: resp.ok, status: resp.status, body: pretty, draft: draft, ms: ms };
  if(resp.ok){
    setPanelTested(panel, true);
    setActivePayload(draft.apiId, draft);
    setStatus("OK "+resp.status);
  } else {
    setStatus("Failed "+resp.status+" — fix values and Test again");
  }
  return resp.ok;
}

async function bindOverviewPayloadPanels(data, rootEl){
  const service = selectedSpecService;
  if(!service) return;
  await Promise.all([
    loadServicePayloadCatalog(service),
    loadServicePayloadSets(service, false)
  ]);
  if(!rootEl) await bindPayloadSetBar();

  const root = rootEl || document;
  root.querySelectorAll(".oas-payload-panel").forEach(panel=>{
    if(panel._sptBound) return;
    panel._sptBound = true;
    const status = panel.querySelector(".oas-pv-status");
    const setStatus = (t)=>{ if(status) status.textContent = t||""; };

    panel.querySelectorAll(".oas-pv-field").forEach(el=>{
      el.addEventListener("input", ()=>{ setPanelTested(panel, false); updatePathPreview(panel); });
      el.addEventListener("change", ()=>{ setPanelTested(panel, false); updatePathPreview(panel); });
    });
    const bodyTa = panel.querySelector("textarea.oas-pv-body");
    if(bodyTa){
      bodyTa.addEventListener("input", ()=> setPanelTested(panel, false));
    }
    panel.querySelectorAll(".oas-pv-chip").forEach(chip=>{
      chip.onclick = ()=>{
        const name = chip.getAttribute("data-chip-for");
        const val = chip.getAttribute("data-chip-value");
        const field = panel.querySelector('.oas-pv-field[data-param-name="'+String(name).replace(/"/g,'')+'"]');
        if(field){ field.value = val; field.dispatchEvent(new Event("input", { bubbles: true })); }
      };
    });
    updatePathPreview(panel);

    const testBtn = panel.querySelector(".oas-pv-test");
    if(testBtn){
      testBtn.onclick = async ()=>{
        try {
          testBtn.disabled = true;
          await runOverviewPanelTest(panel, setStatus);
        } catch(e){
          setStatus(e.message);
          setPanelTested(panel, false);
        } finally {
          testBtn.disabled = false;
        }
      };
    }

    const saveBtn = panel.querySelector(".oas-pv-save");
    if(saveBtn){
      saveBtn.onclick = async ()=>{
        try {
          const draft = readOverviewPanel(panel);
          const last = panel._lastTest || {};
          const bumpSet = !!(panel.querySelector(".oas-pv-bump-set") && panel.querySelector(".oas-pv-bump-set").checked);
          const savedWrap = await fetchJson("/api/payloads", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              service: service,
              api_id: draft.apiId,
              name: draft.name,
              request: {
                method: String(draft.method||"GET").toUpperCase(),
                path: draft.path,
                query: draft.query,
                path_params: draft.pathParams,
                body: draft.body,
                content_type: draft.contentType || null,
                body_mode: draft.bodyMode || null
              },
              response: { status: last.status, body: last.body },
              meta: { source: "overview-editor", checks_passed: !!last.ok, latency_ms: last.ms },
              bump: true,
              into_set: true,
              set_version: bumpSet ? null : specsPayloadSetVersion,
              bump_set: bumpSet
            })
          });
          const saved = savedWrap.payload || savedWrap;
          const pset = savedWrap.payload_set || null;
          if(pset && pset.version != null){
            specsPayloadSetVersion = pset.version;
            persistPayloadSetVersion(service, pset.version);
          }
          specsPayloadService = null;
          specsPayloadSetService = null;
          await Promise.all([
            loadServicePayloadCatalog(service),
            loadServicePayloadSets(service, true)
          ]);
          setActivePayload(draft.apiId, {
            name: (saved && saved.name) || draft.name,
            version: saved && saved.version,
            set_version: specsPayloadSetVersion,
            method: draft.method,
            path: draft.path,
            body: draft.body,
            query: draft.query,
            pathParams: draft.pathParams
          });
          setStatus("Saved into service set v"+specsPayloadSetVersion+
            (bumpSet ? " (new version)" : ""));
          const setStatusEl = document.getElementById("oas-set-status");
          if(setStatusEl){
            const n = specsPayloadSetDetail && specsPayloadSetDetail.apis
              ? Object.keys(specsPayloadSetDetail.apis).length : 0;
            setStatusEl.innerHTML = 'Active set <strong>v'+esc(String(specsPayloadSetVersion))+'</strong> · '+n+' API payload(s) registered';
          }
          const setSel = document.getElementById("oas-set-select");
          if(setSel && specsPayloadSets.length){
            setSel.innerHTML = specsPayloadSets.map(s=>{
              const selAttr = Number(s.version)===Number(specsPayloadSetVersion) ? " selected" : "";
              return '<option value="'+esc(String(s.version))+'"'+selAttr+'>'+
                esc("Set v"+s.version+(s.label?" · "+s.label:"")+" ("+(s.api_count||0)+" APIs)")+
              '</option>';
            }).join("");
          }
          // refresh bar badge without full page reload
          const row = panel.closest(".oas-sw-op");
          const pill = row && row.querySelector(".oas-bar-ver");
          if(pill){
            pill.className = "pill oas-bar-ver oas-pv-active";
            pill.textContent = "v"+specsPayloadSetVersion+" · saved";
          }
        } catch(e){
          setStatus("Save failed: "+e.message);
          alert("Save failed: "+e.message);
        }
      };
    }

    const setBtn = panel.querySelector(".oas-pv-set");
    if(setBtn){
      setBtn.onclick = ()=>{
        try {
          const draft = readOverviewPanel(panel);
          setActivePayload(draft.apiId, Object.assign({}, draft, { set_version: specsPayloadSetVersion }));
          setStatus("Set for Swagger — opening Try APIs…");
          setSpecsView("swagger");
        } catch(e){
          setStatus(e.message);
        }
      };
    }

    const ltBtn = panel.querySelector(".oas-pv-loadtest");
    if(ltBtn){
      ltBtn.onclick = ()=>{
        try {
          const draft = readOverviewPanel(panel);
          setActivePayload(draft.apiId, Object.assign({}, draft, { name: draft.name || "working", set_version: specsPayloadSetVersion }));
          setStatus("Marked for load test (service set v"+specsPayloadSetVersion+")");
          if(typeof setMode === "function") setMode("runs");
        } catch(e){
          setStatus(e.message);
        }
      };
    }

    // Body mode tabs (Postman-like)
    panel.querySelectorAll(".oas-pv-body-mode").forEach(radio=>{
      radio.onchange = ()=>{
        const mode = radio.value;
        panel.querySelectorAll(".oas-pv-body-pane").forEach(pane=>{
          pane.hidden = pane.getAttribute("data-mode") !== mode;
        });
      };
    });
    const addForm = panel.querySelector(".oas-pv-form-add");
    if(addForm){
      addForm.onclick = ()=>{
        const tb = panel.querySelector(".oas-pv-form-body");
        if(!tb) return;
        const tr = document.createElement("tr");
        tr.innerHTML = '<td><input class="oas-pv-form-key" placeholder="Key"/></td><td><input class="oas-pv-form-val" placeholder="Value"/></td><td><button type="button" class="secondary oas-pv-form-del">×</button></td>';
        tb.appendChild(tr);
        const del = tr.querySelector(".oas-pv-form-del");
        if(del) del.onclick = ()=> tr.remove();
      };
    }
    panel.querySelectorAll(".oas-pv-form-del").forEach(btn=>{
      btn.onclick = ()=>{
        const tr = btn.closest("tr");
        if(tr) tr.remove();
      };
    });

    const copyCurl = panel.querySelector(".oas-pv-copy-curl");
    if(copyCurl){
      copyCurl.onclick = async ()=>{
        try {
          const draft = readOverviewPanel(panel);
          const token = await loadTryToken(false);
          const text = panelToCurl(draft, service, specsEnv, token);
          await navigator.clipboard.writeText(text);
          setStatus("Copied curl");
        } catch(e){ setStatus("Copy failed: "+e.message); }
      };
    }
    const fullBtn = panel.querySelector(".oas-pv-full");
    if(fullBtn){
      fullBtn.onclick = ()=>{
        const method = panel.getAttribute("data-op-method") || "";
        const path = panel.getAttribute("data-op-path") || "";
        openOverviewFullView(method+" "+path, data);
      };
    }
    const copyBody = panel.querySelector(".oas-pv-copy-body");
    if(copyBody){
      copyBody.onclick = async ()=>{
        const ta = panel.querySelector("textarea.oas-pv-body");
        try { await navigator.clipboard.writeText(ta ? ta.value : ""); setStatus("Body copied"); }
        catch(e){ setStatus("Copy failed"); }
      };
    }
    const fmtBody = panel.querySelector(".oas-pv-format-body");
    if(fmtBody){
      fmtBody.onclick = ()=>{
        const ta = panel.querySelector("textarea.oas-pv-body");
        if(!ta) return;
        try { ta.value = prettyJson(JSON.parse(ta.value)); setStatus("Formatted"); }
        catch(e){ setStatus("Invalid JSON"); }
      };
    }
    const copyResp = panel.querySelector(".oas-pv-copy-resp");
    if(copyResp){
      copyResp.onclick = async ()=>{
        const pre = panel.querySelector(".oas-pm-resp-body");
        try { await navigator.clipboard.writeText(pre ? pre.textContent : ""); setStatus("Response copied"); }
        catch(_){ setStatus("Copy failed"); }
      };
    }
  });
}

function renderSwaggerOverview(data, ops){
  if(!data.ok || !data.document){
    return '<div class="empty">OpenAPI unavailable'+(data.error?': '+esc(data.error):'.')+'</div>';
  }
  const doc = data.document;
  const filter = (specsSwaggerFilter||"").trim().toLowerCase();
  const filtered = !filter ? ops : ops.filter(op=>{
    const hay = [op.method, op.path, op.summary, op.operationId, (op.tags||[]).join(" ")].join(" ").toLowerCase();
    return hay.indexOf(filter) >= 0;
  });
  const groups = groupOpsByTag(filtered);
  const contractVer = specsContractVersion
    || (doc.info && doc.info.version)
    || data.version
    || data.openapi
    || "—";
  const setVer = specsPayloadSetVersion;
  const selectedN = (specsLoadApiIds||[]).length;
  const totalN = ops.length;
  // Env is chosen in the toolbar above — Contract lists versions for that env only (no env duplicate)
  const envContracts = (window._oasContractOptions||[]).filter(v=>
    String(v.environment||"").toLowerCase() === String(specsEnv||"").toLowerCase()
  );
  const wantVer = String(specsContractVersion || contractVer || "");
  let contractOpts = envContracts.map(v=>{
    const ver = v.version || "unknown";
    const label = v.ok
      ? ("API "+ver+(v.operation_count!=null ? (" · "+v.operation_count+" ops") : ""))
      : ("API "+ver+" · unreachable");
    const sel = String(ver)===wantVer ? " selected" : "";
    const disabled = v.ok ? "" : " disabled";
    return '<option value="'+esc(String(ver))+'"'+disabled+sel+'>'+esc(label)+'</option>';
  }).join("");
  if(!contractOpts){
    contractOpts = '<option value="'+esc(wantVer||"unknown")+'" selected>API '+esc(wantVer||"—")+
      (totalN ? (" · "+totalN+" ops") : "")+'</option>';
  } else if(!envContracts.some(v=>String(v.version||"")===wantVer)){
    contractOpts = '<option value="'+esc(wantVer)+'" selected>API '+esc(wantVer)+'</option>'+contractOpts;
  }
  const contractSelect = '<label class="oas-contract-label">Contract '+
    '<select id="oas-contract-select" title="OpenAPI API version for '+esc(specsEnv)+'">'+
      contractOpts+
    '</select></label>';

  const bodyBlocks = groups.map(g=>{
    const tagIds = g.ops.map(op=>primaryApiId(op));
    const tagSelected = tagIds.filter(id=>isSpecsLoadApiChecked(id)).length;
    const tagAll = tagIds.length > 0 && tagSelected === tagIds.length;
    const rows = g.ops.map(op=>{
      const key = opKey(op);
      const open = window.specsOpenAll === true || specsOpenOp === key;
      const apiId = primaryApiId(op);
      const registeredId = opRegisteredInSet(op);
      const inSet = !!registeredId;
      const checked = isSpecsLoadApiChecked(apiId);
      const verPill = inSet
        ? '<span class="pill oas-bar-ver oas-pv-active" title="In payload set">set v'+esc(String(setVer))+'</span>'
        : '<span class="pill oas-bar-ver oas-pv-missing" title="Not in payload set yet">no set</span>';

      return '<div class="oas-sw-op'+(open?' open':'')+(checked?' oas-sw-picked':'')+'" data-op-key="'+esc(key)+'" data-api-id="'+esc(apiId)+'">'+
        '<div class="oas-sw-row">'+
          '<label class="oas-sw-pick" title="Include in load test" onclick="event.stopPropagation()">'+
            '<input type="checkbox" class="oas-load-api" data-api-id="'+esc(apiId)+'"'+(checked?" checked":"")+'>'+
          '</label>'+
          '<button type="button" class="oas-sw-head">'+
            '<span class="pm-method '+methodClass(op.method)+'">'+esc(op.method)+'</span>'+
            '<code class="oas-sw-path">'+esc(op.path)+'</code>'+
            '<span class="oas-sw-sum">'+esc(op.summary||op.operationId||"")+'</span>'+
            '<span class="oas-sw-chev">'+(open?"▾":"▸")+'</span>'+
          '</button>'+
          '<div class="oas-sw-actions" onclick="event.stopPropagation()">'+
            verPill+
            '<button type="button" class="secondary oas-bar-edit" data-op-key="'+esc(key)+'">Edit</button>'+
            '<button type="button" class="secondary oas-bar-full" data-op-key="'+esc(key)+'">Full</button>'+
            '<button type="button" class="oas-bar-test" data-op-key="'+esc(key)+'">Test</button>'+
          '</div>'+
        '</div>'+
        (open ? '<div class="oas-sw-body">'+renderOverviewPayloadPanel(op, doc)+'</div>' : '')+
      '</div>';
    }).join("");
    return '<div class="oas-sw-tag" data-tag="'+esc(g.tag)+'">'+
      '<div class="oas-sw-tag-h">'+
        '<label class="oas-sw-tag-pick" title="Select all APIs in this controller" onclick="event.stopPropagation()">'+
          '<input type="checkbox" class="oas-load-tag" data-tag="'+esc(g.tag)+'"'+(tagAll?" checked":"")+
            (tagSelected && !tagAll ? ' data-indeterminate="1"' : '')+'>'+
        '</label>'+
        '<span>'+esc(g.tag)+'</span> <span class="pill">'+g.ops.length+'</span>'+
        '<span class="sub oas-sw-tag-sel">'+(tagSelected?tagSelected+' selected':'')+'</span>'+
      '</div>'+
      '<div class="oas-sw-tag-b">'+rows+'</div>'+
    '</div>';
  }).join("") || '<div class="empty">No operations match filter.</div>';

  return '<div class="oas-swagger">'+
    renderPayloadSetBar("oas-set-bar-overview", { showLoad: true, showNewVersion: true })+
    '<div class="oas-load-bar">'+
      '<div class="oas-load-meta">'+
        contractSelect+
        '<span class="pill">Payload set <strong>v'+esc(String(setVer!=null?setVer:"?"))+'</strong></span>'+
        '<span class="sub" id="oas-load-count"><strong>'+selectedN+'</strong> / '+totalN+' APIs for load</span>'+
      '</div>'+
      '<div class="oas-load-actions">'+
        '<button type="button" class="secondary" id="oas-load-all">Select all</button>'+
        '<button type="button" class="secondary" id="oas-load-clear">Clear</button>'+
        '<button type="button" class="secondary" id="oas-load-inset" title="Select only APIs already in the payload set">In set</button>'+
        '<button type="button" id="oas-run-load" title="Run load test with checked APIs + current payload set">Run load</button>'+
      '</div>'+
    '</div>'+
    '<div class="toolbar oas-sw-toolbar">'+
      '<input id="oas-sw-filter" type="search" placeholder="Filter…" value="'+esc(specsSwaggerFilter)+'"/>'+
      '<span class="sub">'+filtered.length+'/'+ops.length+'</span>'+
    '</div>'+
    '<div class="oas-sw-list">'+bodyBlocks+'</div>'+
  '</div>';
}

/** Run load test from OpenAPI overview — uses checked APIs + current contract + payload set. */
async function runLoadFromOpenApi(data){
  const service = selectedSpecService;
  if(!service) return alert("No service selected");
  const ids = (specsLoadApiIds||[]).slice();
  if(!ids.length) return alert("Check at least one API on the controller list (left checkbox).");
  if(specsPayloadSetVersion == null){
    return alert("Pick a payload set version first (Set bar above).");
  }
  const doc = data && data.document;
  const openapiVersion = specsContractVersion
    || (doc && doc.info && doc.info.version)
    || data.openapi
    || null;
  const env = specsEnv || "dev";
  const overrides = (typeof readLoadOverrides === "function") ? readLoadOverrides() : {};
  let preset = document.getElementById("run-preset")?.value || "20u-50";
  let profile = document.getElementById("run-profile")?.value || "load";
  if(preset === "20u-50" || (overrides.vus && overrides.vus > 1) || (overrides.iterations && overrides.iterations > 1)){
    profile = "load";
  }

  // Prefer an existing config for this service; otherwise send inline config
  let cfgMatch = null;
  try {
    if(typeof configs !== "undefined" && configs && configs.length){
      cfgMatch = configs.find(c=>c.service===service && (!c.environment || c.environment===env))
        || configs.find(c=>c.service===service);
    }
  } catch(_){}

  const body = {
    triggered_by: "openapi-overview",
    wait: false,
    preset: preset,
    profile: profile,
    environment: env,
    openapi_version: openapiVersion,
    payload_set_version: Number(specsPayloadSetVersion),
    api_ids: ids,
    ...overrides
  };
  if(body.iterations) delete body.duration;
  if(cfgMatch && cfgMatch.id){
    body.config_id = cfgMatch.id;
  } else {
    body.config = {
      name: service+"-openapi-load",
      service: service,
      environment: env,
      openapi_version: openapiVersion,
      test_type: "k6",
      run_profile: "load"
    };
  }

  syncSpecsLoadApiIdsToRunPicker();
  const status = document.getElementById("oas-load-count");
  if(status) status.innerHTML = 'Starting load · <strong>'+ids.length+'</strong> APIs · set v'+esc(String(specsPayloadSetVersion))+'…';
  try {
    const res = await fetchJson("/api/runs/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if(typeof updateStopButton === "function") updateStopButton(true);
    if(typeof refreshRuns === "function") await refreshRuns({resetPage: true});
    if(typeof setMode === "function") setMode("runs");
    if(typeof selectRun === "function") await selectRun(res.id);
  } catch(e){
    alert("Run load failed: "+e.message);
  }
}

function bindOverviewLoadSelection(data, ops){
  const contractSel = document.getElementById("oas-contract-select");
  if(contractSel && !contractSel._sptBound){
    contractSel._sptBound = true;
    contractSel.onchange = async ()=>{
      // Value is API version only — env comes from toolbar filter above
      const ver = contractSel.value && contractSel.value !== "unknown" ? contractSel.value : null;
      specsContractVersion = ver;
      try {
        localStorage.setItem(
          "spt_specs_contract_"+selectedSpecService,
          JSON.stringify({ env: specsEnv, version: ver })
        );
      } catch(_){}
      if(typeof selectedRunOpenApiEnv !== "undefined") selectedRunOpenApiEnv = specsEnv;
      if(typeof selectedRunOpenApiVersion !== "undefined") selectedRunOpenApiVersion = ver;
      try {
        const head = document.getElementById("run-openapi-version");
        const composed = specsEnv+"|"+(ver||"unknown");
        if(head && [].some.call(head.options||[], o=>o.value===composed)) head.value = composed;
      } catch(_){}
      try { syncPortalUrl({ replace: true }); } catch(_){}
      // Reload ops for the pinned contract (same env; refresh catalog pin)
      delete specsCache[specsCacheKey(selectedSpecService, specsEnv)];
      await renderSpecDetail();
    };
  }
  document.querySelectorAll(".oas-load-api").forEach(box=>{
    box.onchange = ()=>{
      setSpecsLoadApiChecked(box.getAttribute("data-api-id"), box.checked);
      // Light UI update without full remount
      const op = box.closest(".oas-sw-op");
      if(op) op.classList.toggle("oas-sw-picked", box.checked);
      const count = document.getElementById("oas-load-count");
      if(count) count.innerHTML = '<strong>'+(specsLoadApiIds||[]).length+'</strong> / '+(ops||[]).length+' APIs for load';
      // Refresh tag checkbox state
      document.querySelectorAll(".oas-sw-tag").forEach(tagEl=>{
        const tagBox = tagEl.querySelector(".oas-load-tag");
        if(!tagBox) return;
        const boxes = tagEl.querySelectorAll(".oas-load-api");
        const n = Array.from(boxes).filter(b=>b.checked).length;
        tagBox.checked = boxes.length > 0 && n === boxes.length;
        tagBox.indeterminate = n > 0 && n < boxes.length;
        const label = tagEl.querySelector(".oas-sw-tag-sel");
        if(label) label.textContent = n ? (n+" selected") : "";
      });
    };
  });
  document.querySelectorAll(".oas-load-tag").forEach(tagBox=>{
    if(tagBox.getAttribute("data-indeterminate")==="1") tagBox.indeterminate = true;
    tagBox.onchange = ()=>{
      const tagEl = tagBox.closest(".oas-sw-tag");
      if(!tagEl) return;
      const boxes = tagEl.querySelectorAll(".oas-load-api");
      const on = tagBox.checked;
      boxes.forEach(b=>{
        b.checked = on;
        setSpecsLoadApiChecked(b.getAttribute("data-api-id"), on);
        const op = b.closest(".oas-sw-op");
        if(op) op.classList.toggle("oas-sw-picked", on);
      });
      tagBox.indeterminate = false;
      const count = document.getElementById("oas-load-count");
      if(count) count.innerHTML = '<strong>'+(specsLoadApiIds||[]).length+'</strong> / '+(ops||[]).length+' APIs for load';
      const label = tagEl.querySelector(".oas-sw-tag-sel");
      if(label){
        const n = Array.from(boxes).filter(b=>b.checked).length;
        label.textContent = n ? (n+" selected") : "";
      }
    };
  });
  const allBtn = document.getElementById("oas-load-all");
  if(allBtn){
    allBtn.onclick = ()=>{
      setSpecsLoadApiIds((ops||[]).map(op=>primaryApiId(op)));
      renderSpecDetail();
    };
  }
  const clearBtn = document.getElementById("oas-load-clear");
  if(clearBtn){
    clearBtn.onclick = ()=>{
      setSpecsLoadApiIds([]);
      renderSpecDetail();
    };
  }
  const inSetBtn = document.getElementById("oas-load-inset");
  if(inSetBtn){
    inSetBtn.onclick = ()=>{
      const picked = [];
      (ops||[]).forEach(op=>{
        if(opRegisteredInSet(op)) picked.push(primaryApiId(op));
      });
      setSpecsLoadApiIds(picked);
      renderSpecDetail();
    };
  }
  const runBtn = document.getElementById("oas-run-load");
  if(runBtn){
    runBtn.onclick = ()=> runLoadFromOpenApi(data);
  }
}

function closeOverviewFullView(){
  const modal = document.getElementById("oas-full-modal");
  if(modal) modal.hidden = true;
  document.body.classList.remove("oas-full-open");
}

async function openOverviewFullView(opKeyStr, data){
  const ops = (data && data.ok) ? openapiOps(data.document) : [];
  const hit = ops.find(o=>opKey(o) === opKeyStr);
  if(!hit) return;
  const modal = ensureOverviewFullModal();
  const title = document.getElementById("oas-full-title");
  const body = document.getElementById("oas-full-body");
  if(title) title.textContent = (hit.method||"")+" "+(hit.path||"");
  if(body){
    body.innerHTML = renderOverviewPayloadPanel(hit, data.document);
    const ta = body.querySelector("textarea.oas-pv-body");
    if(ta) ta.rows = 16;
    const nestedFull = body.querySelector(".oas-pv-full");
    if(nestedFull) nestedFull.hidden = true;
  }
  modal.hidden = false;
  document.body.classList.add("oas-full-open");
  await bindOverviewPayloadPanels(data, body);
  const first = body && body.querySelector(".oas-pv-field, textarea.oas-pv-body");
  if(first) setTimeout(()=> first.focus(), 40);
}

function ensureOverviewFullModal(){
  let modal = document.getElementById("oas-full-modal");
  if(modal) return modal;
  modal = document.createElement("div");
  modal.id = "oas-full-modal";
  modal.className = "oas-full-modal";
  modal.hidden = true;
  modal.innerHTML =
    '<div class="oas-full-backdrop" data-close="1"></div>'+
    '<div class="oas-full-panel" role="dialog" aria-modal="true">'+
      '<div class="oas-full-head">'+
        '<div class="oas-full-title" id="oas-full-title">Request</div>'+
        '<button type="button" class="secondary" id="oas-full-close">Close</button>'+
      '</div>'+
      '<div class="oas-full-scroll" id="oas-full-body"></div>'+
    '</div>';
  document.body.appendChild(modal);
  modal.querySelector(".oas-full-backdrop").onclick = ()=> closeOverviewFullView();
  modal.querySelector("#oas-full-close").onclick = ()=> closeOverviewFullView();
  if(!window._oasFullEscBound){
    window._oasFullEscBound = true;
    document.addEventListener("keydown", (e)=>{
      if(e.key === "Escape") closeOverviewFullView();
    });
  }
  return modal;
}

function renderTracePanel(reg, data){
  const tr = (reg && reg.trace) || {};
  const src = tr.source || {};
  const git = tr.git || {};
  const traces = (tr.traces || []).map(t=>{
    if(!t || typeof t !== "object") return "";
    return '<tr><td>'+esc(t.name||"")+'</td><td><code>'+esc(t.ref||"")+'</code></td></tr>';
  }).join("") || '<tr><td colspan="2" class="sub">None</td></tr>';
  const tags = (reg.tags || tr.tags || []).map(t=>esc(t)).join(", ") || "—";
  return '<div class="section"><div class="section-h">Registration traceability</div><div class="section-b">'+
    '<table class="api-table"><tbody>'+
      '<tr><td>Registered by</td><td>'+esc(tr.registered_by||"—")+'</td></tr>'+
      '<tr><td>Owners</td><td>'+esc(ownersText(tr.owners||reg.owners))+'</td></tr>'+
      '<tr><td>Created by</td><td>'+esc(tr.created_by||"—")+'</td></tr>'+
      '<tr><td>Created at</td><td>'+esc(tr.created_at||"—")+'</td></tr>'+
      '<tr><td>Updated by</td><td>'+esc(tr.updated_by||"—")+'</td></tr>'+
      '<tr><td>Updated at</td><td>'+esc(tr.updated_at||"—")+'</td></tr>'+
      '<tr><td>File mtime</td><td>'+esc(tr.file_mtime||"—")+'</td></tr>'+
      '<tr><td>Source kind</td><td>'+esc(tr.registration_source||data.source||"—")+'</td></tr>'+
      '<tr><td>Repo</td><td>'+esc(src.repo||"—")+'</td></tr>'+
      '<tr><td>Path</td><td><code>'+esc(src.path||tr.file_path||"—")+'</code></td></tr>'+
      '<tr><td>ConfigMap</td><td><code>'+esc(src.configmap||"—")+'</code></td></tr>'+
      '<tr><td>apiVersion / kind</td><td>'+esc(src.apiVersion||reg.apiVersion||"—")+' / '+esc(src.kind||reg.kind||"—")+'</td></tr>'+
      '<tr><td>Tags</td><td>'+tags+'</td></tr>'+
      '<tr><td>Description</td><td class="sub">'+esc(tr.description||reg.description||"—")+'</td></tr>'+
    '</tbody></table>'+
    '<h4>Traces</h4><table class="api-table"><thead><tr><th>Name</th><th>Ref</th></tr></thead><tbody>'+traces+'</tbody></table>'+
    (git.git_updated_commit?
      '<h4>Git</h4><table class="api-table"><tbody>'+
        '<tr><td>Last commit</td><td><code>'+esc(git.git_updated_commit)+'</code> '+esc(git.git_updated_subject||"")+'</td></tr>'+
        '<tr><td>Last author</td><td>'+esc(git.git_updated_by||"—")+' · '+esc(git.git_updated_at||"")+'</td></tr>'+
        '<tr><td>First commit</td><td><code>'+esc(git.git_created_commit||"—")+'</code> '+esc(git.git_created_subject||"")+'</td></tr>'+
        '<tr><td>First author</td><td>'+esc(git.git_created_by||"—")+' · '+esc(git.git_created_at||"")+'</td></tr>'+
      '</tbody></table>':'')+
    '<h4>Full trace JSON</h4><pre class="oas-pre">'+esc(JSON.stringify(tr,null,2))+'</pre>'+
  '</div></div>';
}
