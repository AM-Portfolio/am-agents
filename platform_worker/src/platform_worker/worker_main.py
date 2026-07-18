"""Temporal worker entrypoint — connects to lab frontend (port-forward or in-cluster)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from platform_worker.activities import alert_incident as acts
from platform_worker.activities import analyze as aan
from platform_worker.activities import infra as iacts
from platform_worker.activities import spt as sacts
from platform_worker.activities import verify as vacts
from platform_worker.workflows.alert_incident import AlertIncidentWorkflow
from platform_worker.workflows.spt_run import SptRunWorkflow

LOG = logging.getLogger("platform_worker")


def _load_lab_env() -> None:
    try:
        from agent_common.dotenv import load_dotenv
    except ImportError:
        return
    explicit = os.getenv("AM_PLATFORM_ENV_FILE", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    here = Path(__file__).resolve()
    am_agents = here.parents[3]
    repos = am_agents.parent
    candidates.extend(
        [
            repos / "am-obs-platform" / ".env",
            am_agents / ".env",
        ]
    )
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_file():
            load_dotenv(resolved, override=False)
            LOG.info("loaded env from %s", resolved)
            return


async def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _load_lab_env()
    host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    ns = os.getenv("TEMPORAL_NAMESPACE", "default")
    queue = os.getenv("TEMPORAL_TASK_QUEUE", "agent-platform")
    notify = os.getenv("ALERT_NOTIFY_PROVIDER", "fake")
    LOG.info("connecting to Temporal %s ns=%s queue=%s notify=%s", host, ns, queue, notify)
    client = await Client.connect(host, namespace=ns)
    worker = Worker(
        client,
        task_queue=queue,
        workflows=[AlertIncidentWorkflow, SptRunWorkflow],
        activities=[
            acts.create_incident_run,
            acts.triage_alert,
            acts.create_and_assign_ticket,
            acts.notify_ticket_created,
            acts.post_cliq_update,
            acts.send_incident_mail,
            acts.post_incident_phase,
            acts.mark_run_status,
            aan.analyze_incident,
            aan.apply_ticket_decision,
            aan.create_infra_handoff,
            aan.execute_infra_action,
            aan.handoff_infra_agent,
            aan.escalate_unsolved,
            aan.write_resolution_note,
            aan.close_incident_ticket,
            iacts.plan_and_execute_fix,
            vacts.spawn_verify_run,
            vacts.claim_and_execute_verify,
            sacts.create_spt_run,
            sacts.resolve_spt_targets,
            sacts.ensure_spt_preps,
            sacts.run_spt_child,
            sacts.finalize_spt_run,
        ],
    )
    LOG.info("worker started")
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
