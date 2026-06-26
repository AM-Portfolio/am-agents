# kagent Phase 0 — preprod VPS cluster (kind-am-preprod)

Install kagent for Kubernetes ops testing. Uses existing LiteLLM in `am-ai`.

## Prerequisites

- `KUBECONFIG` → [VPS/kubeconfig.vps](../../../VPS/kubeconfig.vps)
- LiteLLM running in `am-ai` (`litellm-secrets` with `masterkey`)

## Quick install (PowerShell)

```powershell
$env:KUBECONFIG = "a:\InfraCode\AM-Portfolio-grp\VPS\kubeconfig.vps"
cd am-agents\k8s\kagent
.\install-preprod.ps1
```

## Manual steps

```bash
export KUBECONFIG=VPS/kubeconfig.vps

# 1. CRDs + chart
helm upgrade --install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
  --namespace kagent --create-namespace

helm upgrade --install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
  --namespace kagent \
  --set kmcp.enabled=true \
  --wait --timeout 10m

# 2. LiteLLM secret for ModelConfig
kubectl create namespace kagent --dry-run=client -o yaml | kubectl apply -f -
MASTERKEY=$(kubectl get secret litellm-secrets -n am-ai -o jsonpath='{.data.masterkey}' | base64 -d)
kubectl create secret generic litellm-kagent-secret -n kagent \
  --from-literal=masterkey="$MASTERKEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. ModelConfig + K8s agent
kubectl apply -f modelconfig-litellm.yaml
kubectl apply -f agent-k8s-ops.yaml

# 4. Traefik ingress
kubectl apply -f ingress.yaml

# 5. Verify
kubectl get pods,ingress,RemoteMCPServer,ModelConfig,Agent -n kagent
kubectl port-forward -n kagent svc/kagent-ui 8082:8080
```

## Public URL (Traefik)

| Route | Backend |
|-------|---------|
| `https://kagent.munish.org` | Cluster Traefik → `kagent-ui:8080` (see `ingress.yaml`) |
| `http://localhost:8000` on host `kagent.munish.org` | Docker Traefik → `kagent-ui.kagent.svc.cluster.local:8080` (see `am-infra/traefik/infra.yaml`) |

DNS: point `kagent.munish.org` at the VPS IP. Use port **80/443** for cluster Traefik, or **8000** if you route via docker Traefik (`npm run expose` / `expose_services.py` in am-infra).

## Basic test prompts (UI)

| Prompt | Expected |
|--------|----------|
| List pods in infra namespace | mongodb-0, kafka-0, headlamp, … |
| Which pods are not Running in am-ai? | langfuse-web CrashLoopBackOff if still broken |
| Show logs for headlamp in infra | log lines in Results |
| What Helm releases are installed? | langfuse, litellm, headlamp, … |

## UI: no Send button?

kagent chat does **not** submit on Enter alone.

1. **Use Ctrl+Enter** (Windows) or **Cmd+Enter** (Mac) to send.
2. The **Send** button is **below** the text box — scroll down or zoom out (Ctrl+-) if you only see the textarea.
3. **Ready** is a status label (not a checkbox). When it shows Ready, input is enabled.
4. Prefer agent **am-k8s-ops** (preprod ops agent) over wizard-created `my-first-k8s-agent`.

If chat hangs on "Thinking…", refresh and use **+ New Chat**.

## tool-agent MCP (am-infra-ops)

After deploying tool-agent to preprod:

```powershell
kubectl apply -f tool-agent-mcp-deployment.yaml
kubectl apply -f remote-mcpserver-tool-agent.yaml
kubectl apply -f agent-am-infra-ops.yaml
kubectl get RemoteMCPServer,Agent -n kagent | findstr am-tool-agent
kubectl get RemoteMCPServer,Agent -n kagent | findstr am-infra-ops
```

Use agent **am-infra-ops** for K8s + mongo/kafka/vault/grafana queries. Prefer plan→execute flow (configured in agent system prompt).

## Uninstall

```bash
helm uninstall kagent -n kagent
helm uninstall kagent-crds -n kagent
kubectl delete namespace kagent
```
