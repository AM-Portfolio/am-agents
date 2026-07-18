# Decommission checklist (Gate E)

**Do not execute until** [production gates](../docs/architecture/production-gates.md) A–D pass and approvals are recorded.

## Approvals required

| Approver | Name | Date | Sign-off |
|----------|------|------|----------|
| User / product owner | | | |
| Tool Agent owner | | | |
| DB Agent owner | | | |
| UI Test Agent owner | | | |
| Platform operations | | | |

## Never delete

- [ ] `tool-agent/`
- [ ] `db-agent/`
- [ ] `ui-test-agent/`
- [ ] Shared libs still consumed by specialists or replacement (`libs/*`) unless fully replaced
- [ ] `catalog/` unless ownership transferred with backup
- [ ] `k8s/kagent/` unless separately migrated

## Candidate deletion inventory (legacy platform path only)

Fill during Gate E prep:

| Resource | Path / name | Backup location | Delete after observe window |
|----------|-------------|-----------------|-----------------------------|
| Legacy gateway code | `gateway/` | | |
| Legacy worker code | `platform_worker/` | | |
| Legacy Deployment/Service | | | |
| Legacy Temporal queue consumer | queue: `agent-platform` | | |
| Legacy CI jobs | | | |
| Legacy Vault paths | | | |
| Legacy RunStore tables (only if unused) | | | |

## Procedure

1. Freeze legacy traffic (route 100% to replacement).
2. Observe agreed window.
3. Archive required history.
4. Delete only approved inventory rows.
5. Verify replacement health and absence of dangling references.
6. Record incident ticket / change record ID: ________
