from __future__ import annotations

import json
from typing import Any


def generate_k6_script(
    apis: list[dict[str, Any]],
    *,
    service: str,
    vus: int,
    duration: str,
    iterations: int | None = None,
    capture_traces: bool = False,
    capture_failures: bool = True,
    capture_all_calls: bool = False,
    max_samples: int = 500,
    trace_body_max: int = 8000,
    progress_url: str | None = None,
) -> str:
    apis_literal = json.dumps(apis)
    opts_lines = [f"  vus: {vus},"]
    if iterations is not None:
        opts_lines.append(f"  iterations: {iterations},")
    else:
        opts_lines.append(f"  duration: '{duration}',")
    opts_block = "\n".join(opts_lines)

    return f"""import http from 'k6/http';
import {{ check, group }} from 'k6';
import {{ Trend, Counter, Gauge }} from 'k6/metrics';

const apis = {apis_literal};
const CAPTURE_TRACES = {'true' if capture_traces else 'false'};
const CAPTURE_FAILURES = {'true' if capture_failures else 'false'};
const CAPTURE_ALL = {'true' if capture_all_calls else 'false'};
const MAX_SAMPLES = {int(max_samples)};
const TRACE_BODY_MAX = {trace_body_max};
const BASE_URL = (__ENV.POC_BASE_URL || __ENV.POC_TARGET_URL || '').replace(/\\/$/, '');
const PROGRESS_URL = __ENV.SPT_PROGRESS_URL || {json.dumps(progress_url or "")};
const SAMPLE_URL = __ENV.SPT_SAMPLE_URL || '';
const TOTAL_ITERS = {iterations if iterations is not None else "null"};

function safeId(id) {{
  return String(id || 'api').replace(/[^a-zA-Z0-9_]/g, '_');
}}

// Per-API metrics (unique names) — k6 summary does not expand tagged custom metrics
const sptDur = {{}};
const sptHttp = {{}};
const sptReqs = {{}};
const sptFails = {{}};
for (const api of apis) {{
  const s = safeId(api.id);
  sptDur[api.id] = new Trend('spt_dur_' + s, true);
  sptHttp[api.id] = new Gauge('spt_http_' + s);
  sptReqs[api.id] = new Counter('spt_reqs_' + s);
  sptFails[api.id] = new Counter('spt_fails_' + s);
}}

export const options = {{
{opts_block}
  tags: {{ service: '{service}' }},
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
}};

function runCheck(res, checks) {{
  const rules = checks && checks.length ? checks : ['status_2xx'];
  let ok = true;
  for (const rule of rules) {{
    if (rule === 'status_2xx') {{
      ok = check(res, {{ 'status 2xx': (r) => r.status >= 200 && r.status < 300 }}) && ok;
    }} else if (rule === 'status_3xx') {{
      ok = check(res, {{ 'status 3xx': (r) => r.status >= 300 && r.status < 400 }}) && ok;
    }} else if (rule.startsWith('status_')) {{
      const code = parseInt(rule.replace('status_', ''), 10);
      ok = check(res, {{ [`status ${{code}}`]: (r) => r.status === code }}) && ok;
    }}
  }}
  return ok;
}}

function truncateBody(body) {{
  if (body == null) return null;
  const s = String(body);
  return s.length > TRACE_BODY_MAX ? s.slice(0, TRACE_BODY_MAX) + '…[truncated]' : s;
}}

function postSample(api, url, reqHeaders, reqBody, res, durationMs, passed) {{
  if (!SAMPLE_URL) return;
  const wantFail = CAPTURE_FAILURES && !passed;
  const wantOk = CAPTURE_TRACES && passed;
  if (!CAPTURE_ALL && !wantFail && !wantOk) return;
  if (!globalThis.__sptSampleCount) globalThis.__sptSampleCount = 0;
  if (globalThis.__sptSampleCount >= MAX_SAMPLES) return;
  // Legacy one-sample-per-API when not capturing every call
  if (!CAPTURE_ALL) {{
    if (!globalThis.__sptPosted) globalThis.__sptPosted = {{}};
    const prev = globalThis.__sptPosted[api.id];
    if (prev === 'fail') return;
    if (passed && prev === 'ok') return;
    if (passed && prev) return;
  }}
  const callIndex = globalThis.__sptSampleCount + 1;
  try {{
    http.post(
      SAMPLE_URL,
      JSON.stringify({{
        api_id: api.id,
        name: api.name,
        method: api.method,
        path: api.path,
        url,
        call_index: callIndex,
        vu: __VU,
        iter: __ITER,
        request: {{ headers: reqHeaders, body: reqBody }},
        response: {{
          status: res.status,
          headers: res.headers,
          body: truncateBody(res.body),
        }},
        timings: {{ duration_ms: durationMs }},
        checks_passed: passed,
      }}),
      {{
        headers: {{ 'Content-Type': 'application/json' }},
        timeout: '2s',
        tags: {{ name: 'spt_sample', api_id: 'spt.sample' }},
      }}
    );
    globalThis.__sptSampleCount = callIndex;
    if (!CAPTURE_ALL) {{
      if (!globalThis.__sptPosted) globalThis.__sptPosted = {{}};
      globalThis.__sptPosted[api.id] = passed ? 'ok' : 'fail';
    }}
  }} catch (e) {{ /* ignore */ }}
}}

function reportProgress(payload) {{
  if (!PROGRESS_URL) return;
  const body = Object.assign(
    {{
      vu: __VU,
      iter: __ITER,
      total: TOTAL_ITERS,
      api_count: apis.length,
    }},
    payload || {{ event: 'tick' }}
  );
  try {{
    http.post(PROGRESS_URL, JSON.stringify(body), {{
      headers: {{ 'Content-Type': 'application/json' }},
      timeout: '800ms',
      tags: {{ name: 'spt_progress', api_id: 'spt.progress' }},
    }});
  }} catch (e) {{ /* ignore progress errors */ }}
}}

function buildUrl(api) {{
  let url = BASE_URL + api.path;
  const q = api.query || {{}};
  const keys = Object.keys(q);
  if (keys.length) {{
    url += '?' + keys.map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(q[k])).join('&');
  }}
  return url;
}}

function doRequest(api) {{
  const url = buildUrl(api);
  const tags = {{ api_id: api.id, name: api.name }};
  const params = {{
    headers: api.headers || {{}},
    tags,
  }};
  const start = Date.now();
  let res;
  const body = api.body != null ? api.body : undefined;
  switch (api.method) {{
    case 'POST':
      res = http.post(url, body, params);
      break;
    case 'PUT':
      res = http.put(url, body, params);
      break;
    case 'PATCH':
      res = http.patch(url, body, params);
      break;
    case 'DELETE':
      res = http.del(url, body, params);
      break;
    default:
      res = http.get(url, params);
  }}
  const durationMs = Date.now() - start;
  const passed = runCheck(res, api.checks);
  if (sptDur[api.id]) sptDur[api.id].add(durationMs);
  if (sptHttp[api.id]) sptHttp[api.id].add(res.status);
  if (sptReqs[api.id]) sptReqs[api.id].add(1);
  if (!passed && sptFails[api.id]) sptFails[api.id].add(1);
  postSample(api, url, params.headers, api.body, res, durationMs, passed);
  // Fine-grained progress so UI moves during slow multi-API iterations
  reportProgress({{ event: 'api', api_id: api.id }});
}}

export default function () {{
  reportProgress({{ event: 'tick_start' }});
  for (const api of apis) {{
    group(api.id, () => doRequest(api));
  }}
  reportProgress({{ event: 'tick' }});
}}

export function handleSummary(data) {{
  return {{ 'summary.json': JSON.stringify(data, null, 2) }};
}}
"""
