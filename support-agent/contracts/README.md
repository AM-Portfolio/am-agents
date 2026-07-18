# Contracts package

Pydantic implementation: `src/am_support_agent/contracts/` (`enums.py`, `schemas.py`, `capabilities.py`, `incident.py`).

Logical shapes also documented in:

- [a2a.md](a2a.md) — task / result / stream / feedback
- [capabilities.md](capabilities.md) — agent cards + routing preference
- Ownership freeze: [docs/capability-ownership.md](../docs/capability-ownership.md)
- Architecture SoT: [docs/architecture/a2a-protocol.md](../../docs/architecture/a2a-protocol.md)

## Package layout

```text
src/am_support_agent/contracts/
  enums.py           # A2A + CapabilityId + IncidentValidationStatus
  schemas.py         # A2A task/result envelopes
  capabilities.py    # Neutral tool DTOs (work-item, chat, mail, observe, spt)
  incident.py        # IncidentContext / Validation / Episode / MemoryQuery
contracts/*.md       # design notes
```

## Compatibility with `am_platform_ports`

Existing `libs/platform-ports` already defines run/incident/SPT schemas. A2A contracts **complement** those ports:

- Ports = vendor-blind workflow dependencies (RunStore, Ticket, LLM, …)
- A2A = specialist-agent invocation envelope (discover/plan/execute/…)
- Neutral capability DTOs = tool-agent plugin I/O without vendor names

Do not fork incident/run schemas without a migration note in `MIGRATION_MAP.md`.
