# Install kagent on VPS preprod cluster (Phase 0)
# Usage: .\install-preprod.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $Root "..\..\..")
$Kubeconfig = Join-Path $RepoRoot "VPS\kubeconfig.vps"

if (-not (Test-Path $Kubeconfig)) {
    Write-Error "Missing kubeconfig: $Kubeconfig"
}

$env:KUBECONFIG = $Kubeconfig
Write-Host "KUBECONFIG=$Kubeconfig" -ForegroundColor Cyan

Write-Host "`n[1/6] Checking cluster..." -ForegroundColor Yellow
kubectl get nodes
kubectl get pods -n am-ai -l app.kubernetes.io/name=litellm

Write-Host "`n[2/6] Installing kagent CRDs..." -ForegroundColor Yellow
helm upgrade --install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds `
    --namespace kagent --create-namespace

Write-Host "`n[3/6] Installing kagent chart..." -ForegroundColor Yellow
helm upgrade --install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent `
    --namespace kagent `
    --set kmcp.enabled=true `
    --wait --timeout 10m

Write-Host "`n[4/6] Copying LiteLLM master key to kagent namespace..." -ForegroundColor Yellow
$masterkeyB64 = kubectl get secret litellm-secrets -n am-ai -o jsonpath='{.data.masterkey}'
if (-not $masterkeyB64) {
    Write-Error "Could not read litellm-secrets.masterkey from am-ai namespace"
}
$masterkey = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($masterkeyB64))
kubectl create secret generic litellm-kagent-secret -n kagent `
    --from-literal=masterkey=$masterkey `
    --dry-run=client -o yaml | kubectl apply -f -

Write-Host "`n[5/6] Applying ModelConfig + am-k8s-ops agent..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $Root "modelconfig-litellm.yaml")
kubectl apply -f (Join-Path $Root "agent-k8s-ops.yaml")

Write-Host "`n[6/6] Applying Traefik ingress (kagent.munish.org)..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $Root "ingress.yaml")

Write-Host "`n--- Status ---" -ForegroundColor Green
kubectl get pods -n kagent
kubectl get ingress -n kagent
kubectl get RemoteMCPServer,ModelConfig,Agent -n kagent

Write-Host @"

Done. Open UI:
  https://kagent.munish.org  (cluster Traefik)
  http://localhost:8000      (docker Traefik, after sync_traefik_config / expose_services)
  kubectl port-forward -n kagent svc/kagent-ui 8082:8080 -> http://localhost:8082

Chat with agent: am-k8s-ops
Test: List pods in infra namespace

"@ -ForegroundColor Green
