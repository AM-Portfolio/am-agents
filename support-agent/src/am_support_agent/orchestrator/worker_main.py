"""Temporal worker for support-agent — queue support-agent-v2 (never agent-platform)."""

from __future__ import annotations

import asyncio
import logging
import os

LOG = logging.getLogger("support_agent.worker")


async def run_worker() -> None:
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError as exc:
        raise SystemExit(
            "temporalio not installed. pip install 'am-support-agent[temporal]'"
        ) from exc

    from am_support_agent.orchestrator.activities.a2a import execute_plan
    from am_support_agent.orchestrator.activities.incident import INCIDENT_ACTIVITIES
    from am_support_agent.orchestrator.activities.spt import (
        bootstrap_spt,
        resolve_spt_catalog,
    )
    from am_support_agent.orchestrator.queue import assert_safe_task_queue, resolve_task_queue
    from am_support_agent.orchestrator.workflows.a2a_run import SupportA2AWorkflow
    from am_support_agent.orchestrator.workflows.alert_incident import (
        AlertIncidentWorkflow,
    )
    from am_support_agent.orchestrator.workflows.spt_run import SptRunWorkflow
    from am_support_agent.observability import configure_tracing, temporal_interceptors

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    ns = os.getenv("TEMPORAL_NAMESPACE", "default")
    queue = resolve_task_queue()
    assert_safe_task_queue(queue)
    LOG.info(
        "support-agent worker connecting Temporal %s ns=%s queue=%s",
        host,
        ns,
        queue,
    )
    configure_tracing(service_name="support-agent")
    client = await Client.connect(
        host,
        namespace=ns,
        interceptors=temporal_interceptors(),
    )
    worker = Worker(
        client,
        task_queue=queue,
        workflows=[SupportA2AWorkflow, AlertIncidentWorkflow, SptRunWorkflow],
        activities=[
            execute_plan,
            *INCIDENT_ACTIVITIES,
            bootstrap_spt,
            resolve_spt_catalog,
        ],
    )
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
