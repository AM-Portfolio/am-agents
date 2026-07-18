# Docker image

Canonical Dockerfile: [`../../Dockerfile`](../../Dockerfile)

```bash
# from support-agent/
docker build -t am-support-agent:local .
```

- Default CMD: `am-support-agent-gateway` (port 8091)
- Worker: override command to `am-support-agent-worker`
- Runs as UID 10001 (non-root)
- Installs `[temporal]` extra for optional worker workflows

CI builds this context via `.github/workflows/am-support-agent.yml`.
