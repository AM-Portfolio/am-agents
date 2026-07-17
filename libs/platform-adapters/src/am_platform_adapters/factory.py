"""Composition root — env-selected providers (fake / cliq / openproject / …)."""

from __future__ import annotations

import os

from am_platform_ports.fakes import (
    FakeCalendar,
    FakeDirectory,
    FakeDocStore,
    FakeInfraOps,
    FakeLlm,
    FakeMail,
    FakeNotifier,
    FakeObservability,
    FakePromptRegistry,
    FakeRedactor,
    FakeRunStore,
    FakeSecretBroker,
    FakeTicketStore,
    FakeToolSandbox,
    FakeTriage,
)


def build_ticket_store():
    provider = os.getenv("TICKET_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeTicketStore()
    if provider == "openproject":
        from am_platform_adapters.providers.openproject import OpenProjectTicketStore

        return OpenProjectTicketStore()
    if provider == "jira":
        from am_platform_adapters.providers.jira import JiraTicketStore

        return JiraTicketStore()
    raise NotImplementedError(f"TICKET_PROVIDER={provider} not wired yet")


def build_notifier():
    provider = os.getenv("ALERT_NOTIFY_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeNotifier()
    if provider == "cliq":
        from am_platform_adapters.providers.cliq import CliqNotifier

        return CliqNotifier()
    raise NotImplementedError(f"ALERT_NOTIFY_PROVIDER={provider} not wired yet")


def build_directory():
    provider = os.getenv("DIRECTORY_PROVIDER", os.getenv("TICKET_PROVIDER", "fake")).strip().lower()
    if provider == "fake":
        return FakeDirectory()
    if provider == "openproject":
        from am_platform_adapters.providers.openproject import OpenProjectDirectory

        return OpenProjectDirectory()
    raise NotImplementedError(f"DIRECTORY_PROVIDER={provider} not wired yet")


def build_prompt_registry():
    provider = os.getenv("PROMPT_PROVIDER", "file").strip().lower()
    if provider == "fake":
        return FakePromptRegistry()
    if provider == "file":
        from am_platform_adapters.prompt_registry import FilePromptRegistry

        try:
            reg = FilePromptRegistry()
            # warm + fallback if empty
            reg.get(prompt_key="triage.default")
            return reg
        except Exception:
            return FakePromptRegistry()
    return FakePromptRegistry()


def build_llm():
    provider = os.getenv("LLM_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeLlm()
    if provider in {"openai_compat", "openai", "litellm"}:
        from am_platform_adapters.providers.llm_gateway import OpenAICompatLlm

        return OpenAICompatLlm()
    if provider == "gemini":
        from am_platform_adapters.providers.llm_gateway import GeminiLlm

        return GeminiLlm()
    raise NotImplementedError(f"LLM_PROVIDER={provider} not wired yet")


def build_handoff(runs=None):
    from am_platform_ports.fakes import FakeHandoff

    return FakeHandoff(runs=runs or build_run_store())


def build_run_store():
    provider = os.getenv("RUN_STORE_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeRunStore()
    if provider == "postgres":
        from am_platform_adapters.providers.postgres_runstore import PostgresRunStore

        return PostgresRunStore()
    raise NotImplementedError(f"RUN_STORE_PROVIDER={provider} not wired yet")


def _build_doc_store_primary():
    provider = os.getenv("DOC_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeDocStore()
    if provider == "minio":
        from am_platform_adapters.providers.minio import MinioDocStore

        return MinioDocStore()
    raise NotImplementedError(f"DOC_PROVIDER={provider} not wired yet")


def _build_doc_store_fallback():
    name = os.getenv("DOC_FALLBACK", "").strip().lower()
    if not name:
        return None
    if name == "gdrive":
        from am_platform_adapters.providers.gdrive import GDriveDocStore

        return GDriveDocStore()
    if name == "fake":
        return FakeDocStore()
    raise NotImplementedError(f"DOC_FALLBACK={name} not wired yet")


def build_doc_store():
    primary = _build_doc_store_primary()
    fallback = _build_doc_store_fallback()
    if fallback is None:
        return primary
    from am_platform_adapters.failover_docstore import FailoverDocStore

    return FailoverDocStore(primary=primary, fallback=fallback)


def build_secret_broker():
    return FakeSecretBroker()


def build_sandbox():
    return FakeToolSandbox()


def build_redactor():
    return FakeRedactor()


def build_triage():
    return FakeTriage()


def build_observability():
    return FakeObservability()


def build_infra_ops():
    return FakeInfraOps(sandbox=FakeToolSandbox(), redactor=FakeRedactor())


def build_target_catalog():
    from am_platform_adapters.providers.spt import FileTargetCatalog

    return FileTargetCatalog()


def build_target_resolver():
    from am_platform_adapters.providers.spt import CatalogTargetResolver, FileTargetCatalog

    return CatalogTargetResolver(FileTargetCatalog())


def build_load_policy():
    env = os.getenv("SPT_ENV", "lab").strip().lower()
    if env == "prod":
        from am_platform_adapters.providers.spt import ProdLoadPolicy

        return ProdLoadPolicy()
    from am_platform_adapters.providers.spt import LabLoadPolicy

    return LabLoadPolicy()


def build_data_prep():
    from am_platform_adapters.providers.spt import DedupeDataPrep

    return DedupeDataPrep()


def build_load_test_runner():
    from am_platform_adapters.providers.spt import SandboxLoadTestRunner

    return SandboxLoadTestRunner()


def build_mail():
    provider = os.getenv("MAIL_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeMail()
    if provider == "zoho":
        from am_platform_adapters.providers.zoho import ZohoMail

        return ZohoMail()
    raise NotImplementedError(f"MAIL_PROVIDER={provider} not wired yet")


def build_calendar():
    provider = os.getenv("CALENDAR_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeCalendar()
    if provider == "zoho":
        from am_platform_adapters.providers.zoho import ZohoCalendar

        return ZohoCalendar()
    raise NotImplementedError(f"CALENDAR_PROVIDER={provider} not wired yet")
