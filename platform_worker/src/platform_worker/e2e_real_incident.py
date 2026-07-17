"""Real incident E2E — Start AlertIncident with Grafana-like payload (no ALERT_FORCE_*).

Requires worker running with:
  TICKET_PROVIDER=openproject, ALERT_NOTIFY_PROVIDER=cliq,
  RUN_STORE_PROVIDER=postgres, LLM_PROVIDER=openai_compat (or fake),
  no ALERT_FORCE_DECISION.

Usage:
  python -m platform_worker.e2e_real_incident
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from temporalio.client import Client

TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "agent-platform")
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")


def _payload(tracking_seed: str) -> dict:
    """Grafana/AM-shaped alert — simple infra service-down (not app/API)."""
    return {
        "summary": "KubeServiceDown: redis in infra has 0 ready endpoints",
        "priority": "P2",
        "category": "infra",
        "status": "firing",
        "fingerprint": f"fp-{tracking_seed}",
        "starts_at": datetime.now(timezone.utc).isoformat(),
        "generator_url": "https://grafana.asrax.in/alerting/grafana/kube-service-down/view",
        "value_string": "ready_endpoints=0",
        "group_size": 1,
        "sibling_alertnames": [],
        "trace_id": "",
        "span_id": "",
        "annotations": {
            "summary": "KubeServiceDown: redis in infra has 0 ready endpoints",
            "description": (
                "Platform infra service redis (namespace infra) reports 0 ready endpoints "
                "for >3m. Likely pod restart / CrashLoop. Safe infra remediation: "
                "check pod status/describe then rollout restart deployment/redis. "
                "No app code change required."
            ),
            "runbook": "https://wiki.asrax.in/runbooks/infra-redis-down",
        },
        "labels": {
            "alertname": "KubeServiceDown",
            "severity": "warning",
            "team": "platform",
            "namespace": "infra",
            "service": "redis",
            "deployment": "redis",
            "pod": "redis-7c9f4b8d6-abc12",
            "env": "lab",
            "component": "infra",
        },
    }


async def main() -> int:
    # Refuse silent mock steering
    for banned in ("ALERT_FORCE_DECISION", "INFRA_FORCE_FAIL", "VERIFY_FORCE_RESULT"):
        if os.getenv(banned, "").strip():
            print(f"REFUSE: unset {banned} for real E2E (currently set)")
            return 2

    observe = os.getenv("OBSERVE_PROVIDER", "fake").strip().lower()
    print(f"OBSERVE_PROVIDER={observe}")
    if observe not in {"prometheus", "prom", "grafana", "tool_agent", "tool-agent"}:
        print("REFUSE: set OBSERVE_PROVIDER=prometheus (or tool_agent) for real verify")
        return 2
    if observe in {"prometheus", "prom", "grafana"} and not (
        os.getenv("TOOL_AGENT_URL") or os.getenv("TOOL_AGENT_BASE_URL") or ""
    ).strip():
        print("NOTE: TOOL_AGENT_URL unset — redis verify uses Prometheus only")
    elif (os.getenv("TOOL_AGENT_URL") or "").strip():
        print(f"TOOL_AGENT_URL={os.getenv('TOOL_AGENT_URL')} (redis verify via tool-agent)")

    llm = os.getenv("LLM_PROVIDER", "fake").strip().lower()
    print(f"LLM_PROVIDER={llm}")
    if llm == "fake":
        print("WARNING: LLM_PROVIDER=fake — decisions are canned, not model-generated")

    seed = uuid.uuid4().hex[:8]
    tracking_id = f"AM-REAL-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{seed.upper()}"
    alert = _payload(seed)
    print(f"alert_summary={alert.get('summary')}")
    print(f"alert_labels={alert.get('labels')}")
    wid = f"alert-incident-{tracking_id}"

    client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)
    handle = await client.start_workflow(
        "AlertIncidentWorkflow",
        {"tracking_id": tracking_id, "alert": alert, "alert_analysis_llm": True},
        id=wid,
        task_queue=TASK_QUEUE,
    )
    print(f"started workflow_id={handle.id}")
    print(f"tracking_id={tracking_id}")

    # Poll status while analyze/ticket/route/verify run
    for i in range(60):
        await asyncio.sleep(2)
        try:
            status = await handle.query("status")
        except Exception as exc:  # noqa: BLE001
            print(f"query_err={exc}")
            continue
        print(f"t+{(i+1)*2}s status={status}")
        if status.get("closed") or status.get("decision") in {"ignore"}:
            break
        # needs_human / auto waiting — still print for review
        if status.get("decision") == "needs_human" and not status.get("closed"):
            print("Agent escalated to needs_human — waiting for approve/resolve signal…")
            print("Send: approve  OR  alert.resolved  via Temporal UI / gateway")
            # leave running for human review; do not auto-approve
            break
        if status.get("decision") == "auto_infra" and (
            status.get("verify_status") or status.get("closed")
        ):
            break

    try:
        desc = await handle.describe()
        print(f"temporal_status={desc.status}")
    except Exception as exc:  # noqa: BLE001
        print(f"describe_err={exc}")

    final_q = await handle.query("status")
    print(f"final_query={final_q}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
