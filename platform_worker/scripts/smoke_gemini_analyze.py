"""Quick real Gemini analyze smoke."""
from __future__ import annotations

from am_platform_adapters.providers.llm_gateway import GeminiLlm

SYSTEM = """Return ONLY JSON with keys:
decision, confidence, rationale, handoff_agent, proposed_actions, ticket_update, resolution_note.
decision must be one of: needs_human, auto_infra, ignore.
For pod CrashLoopBackOff / NotReady prefer auto_infra with tools lab.pod_status then lab.pod_restart.
Never delete. needs_human for application/code bugs. ignore for noise.
"""

USER = (
    "Summary: KubePodNotReady payment-api unready 5m CrashLoopBackOff suspected. "
    "Labels: namespace=am-apps-preprod pod=payment-api env=preprod severity=critical team=payments"
)


def main() -> None:
    llm = GeminiLlm()
    out = llm.complete(
        prompt_key="incident.analyze",
        variables={"system": SYSTEM, "user": USER},
    )
    print("LLM_OK")
    print(out)


if __name__ == "__main__":
    main()
