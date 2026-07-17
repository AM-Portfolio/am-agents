"""DI — composition root via am_platform_adapters.factory."""

from __future__ import annotations

from dataclasses import dataclass

from am_platform_adapters import factory as af
from am_platform_ports.ports.directory import DirectoryPort
from am_platform_ports.ports.docs import DocStore
from am_platform_ports.ports.handoff import HandoffPort
from am_platform_ports.ports.infra import InfraOps
from am_platform_ports.ports.llm import LlmPort
from am_platform_ports.ports.notifier import Notifier
from am_platform_ports.ports.prompt import PromptRegistry
from am_platform_ports.ports.redact import Redactor
from am_platform_ports.ports.run import RunStore
from am_platform_ports.ports.spt import (
    DataPrep,
    LoadPolicy,
    LoadTestRunner,
    ObservabilityPort,
    TargetCatalog,
    TargetResolver,
)
from am_platform_ports.ports.ticket import TicketStore
from am_platform_ports.ports.triage import TriagePort


@dataclass
class Ports:
    triage: TriagePort
    directory: DirectoryPort
    tickets: TicketStore
    notifier: Notifier
    prompts: PromptRegistry
    runs: RunStore
    docs: DocStore
    observe: ObservabilityPort
    infra: InfraOps
    redactor: Redactor
    llm: LlmPort
    handoff: HandoffPort
    spt_catalog: TargetCatalog
    spt_resolver: TargetResolver
    spt_policy: LoadPolicy
    spt_prep: DataPrep
    spt_runner: LoadTestRunner


_PORTS: Ports | None = None


def get_ports() -> Ports:
    global _PORTS
    if _PORTS is None:
        runs = af.build_run_store()
        _PORTS = Ports(
            triage=af.build_triage(),
            directory=af.build_directory(),
            tickets=af.build_ticket_store(),
            notifier=af.build_notifier(),
            prompts=af.build_prompt_registry(),
            runs=runs,
            docs=af.build_doc_store(),
            observe=af.build_observability(),
            infra=af.build_infra_ops(),
            redactor=af.build_redactor(),
            llm=af.build_llm(),
            handoff=af.build_handoff(runs),
            spt_catalog=af.build_target_catalog(),
            spt_resolver=af.build_target_resolver(),
            spt_policy=af.build_load_policy(),
            spt_prep=af.build_data_prep(),
            spt_runner=af.build_load_test_runner(),
        )
    return _PORTS


def reset_ports_for_tests() -> None:
    global _PORTS
    _PORTS = None
