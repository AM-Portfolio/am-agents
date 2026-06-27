# Deploy tool-agent MCP bridge + am-infra-ops agent for kagent UI
# Usage: .\deploy-tool-agent-kagent.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $Root "..\..\..")
$Kubeconfig = Join-Path $RepoRoot "VPS\kubeconfig.vps"
$ScriptsDir = Join-Path $RepoRoot "am-agents\tool-agent\scripts"

if (-not (Test-Path $Kubeconfig)) {
    Write-Error "Missing kubeconfig: $Kubeconfig"
}
foreach ($f in @("mcp_http_server.py", "mcp_tools.py")) {
    if (-not (Test-Path (Join-Path $ScriptsDir $f))) {
        Write-Error "Missing $f under $ScriptsDir"
    }
}

$env:KUBECONFIG = $Kubeconfig
Write-Host "KUBECONFIG=$Kubeconfig" -ForegroundColor Cyan

Write-Host "`n[1/5] ConfigMap: MCP bridge scripts (no image rebuild required)..." -ForegroundColor Yellow
kubectl create configmap am-tool-agent-mcp-bridge -n kagent `
    --from-file="$ScriptsDir\mcp_http_server.py" `
    --from-file="$ScriptsDir\mcp_tools.py" `
    --dry-run=client -o yaml | kubectl apply -f -

Write-Host "`n[2/5] Deployment + Service: am-tool-agent-mcp..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $Root "tool-agent-mcp-deployment.yaml")

Write-Host "`n[3/5] RemoteMCPServer..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $Root "remote-mcpserver-tool-agent.yaml")

Write-Host "`n[4/5] Agent: am-infra-ops (K8s + tool-agent)..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $Root "agent-am-infra-ops.yaml")

Write-Host "`n[5/5] Wait for MCP pod..." -ForegroundColor Yellow
kubectl rollout status deployment/am-tool-agent-mcp -n kagent --timeout=120s
kubectl wait --for=condition=Accepted remotemcpserver/am-tool-agent-mcp -n kagent --timeout=120s 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "RemoteMCPServer not Accepted yet - check kmcp controller logs." -ForegroundColor Yellow
}

Write-Host "`n--- Status ---" -ForegroundColor Green
kubectl get pods -n kagent -l app=am-tool-agent-mcp
kubectl get RemoteMCPServer am-tool-agent-mcp -n kagent
kubectl get Agent am-infra-ops -n kagent

Write-Host ""
Write-Host "Done. kagent UI test (Ctrl+Enter to send):" -ForegroundColor Green
Write-Host "  1. Open https://kagent.munish.org"
Write-Host "  2. Select agent am-infra-ops"
Write-Host "  3. Prompt: List kafka topics in preprod read-only, backend kafka"
Write-Host ""
Write-Host "Local smoke:" -ForegroundColor Green
Write-Host "  kubectl port-forward -n kagent svc/am-tool-agent-mcp 8085:8085"
Write-Host "  python am-agents/tool-agent/scripts/test_kagent_tool_agent_flow.py"
