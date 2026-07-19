"""Generic capability plugins for support-agent orchestration.

Folder names use underscores (`work_item`); manifest `name` is the capability
backend id (`work-item`). Vendor code lives only under `adapters/<vendor>/`.

Enable selectively (default manifests are disabled so existing specialist
deployments are unchanged):

```
TOOL_AGENT_CAPABILITY_PLUGINS=work-item,chat,mail,document,directory,observe,spt
```

Provider selection (defaults to `memory` for local/tests):

| Plugin    | Env                   | Adapters              |
|-----------|-----------------------|-----------------------|
| work-item | WORK_ITEM_PROVIDER    | memory, openproject   |
| chat      | CHAT_PROVIDER         | memory, cliq          |
| mail      | MAIL_PROVIDER         | memory, zoho          |
| document  | DOCUMENT_PROVIDER     | memory, minio         |
| directory | DIRECTORY_PROVIDER    | memory, openproject   |
| observe   | OBSERVE_PROVIDER      | memory, grafana       |
| spt       | SPT_PROVIDER          | memory, k6            |

Writes require `/plan` then `/execute` with confirmation token + optional
`plan_hash` / `idempotency_key` on the execute request.
"""
