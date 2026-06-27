# Vault MCP auth for kagent-vault-mcp (preprod)

## Recommended: dedicated Vault token with scoped policy

1. Create policy `kagent-vault-mcp-read` (reads only under `apps/data/preprod/`):

```hcl
path "apps/data/preprod/*" {
  capabilities = ["read", "list"]
}
path "sys/mounts" {
  capabilities = ["read", "list"]
}
```

2. Optional write policy (only if `VAULT_MCP_WRITES_ENABLED=true` on tool-agent):

```hcl
path "apps/data/preprod/infra/*" {
  capabilities = ["create", "update", "delete"]
}
path "apps/data/preprod/services/*" {
  capabilities = ["create", "update", "delete"]
}
```

3. Create token and secret:

```bash
export KUBECONFIG=VPS/kubeconfig.vps
vault token create -policy=kagent-vault-mcp-read -period=768h

kubectl create secret generic kagent-vault-mcp -n kagent \
  --from-literal=VAULT_TOKEN='<token>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

4. Deploy:

```bash
kubectl apply -f vault-mcp-deployment.yaml
kubectl get pods,svc -n kagent -l app=kagent-vault-mcp
```

5. Local spike (port-forward):

```bash
kubectl port-forward -n kagent svc/kagent-vault-mcp 18080:8080
cd am-agents/tool-agent
python scripts/spike_vault_mcp.py http://127.0.0.1:18080/mcp
```

## Kubernetes auth (future)

For long-lived clusters, prefer Kubernetes auth:

- Role: `kagent-vault-mcp` bound to SA `kagent/kagent-vault-mcp`
- Policy: same read (and optional write) paths as above
- Inject token via Vault Agent sidecar or periodic token renewal CronJob

`VAULT_ADDR` in the deployment points at `vault-internal.vault.svc.cluster.local:8200`.
