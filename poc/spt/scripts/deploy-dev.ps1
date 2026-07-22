# Build image (once) + deploy to load-testing - fast pod restarts, no pip in init
# If Docker Desktop is not running locally, use: python scripts/vps-build-load.ps1
param(
    [string]$KubeConfig = "",
    [string]$Namespace = "load-testing",
    [string]$ImageTag = "spt-dev",
    [switch]$SkipBuild,
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PocDir = Split-Path -Parent $ScriptDir
$AmReposRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PocDir))
$DefaultKubeConfig = Join-Path $AmReposRoot "VPS\VPS\kubeconfig.vps"
$Image = "ghcr.io/am-portfolio/am-spt-poc:$ImageTag"

if (-not $KubeConfig) { $KubeConfig = $DefaultKubeConfig }
if (-not (Test-Path $KubeConfig)) { Write-Error "Kubeconfig not found: $KubeConfig" }

$env:KUBECONFIG = $KubeConfig

if (-not $SkipBuild) {
    Write-Host "==> Building $Image (deps + k6 baked in - no pip on pod start) ..."
    docker build -t $Image $PocDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed. Start Docker Desktop, then re-run this script."
    }
}

if (-not $SkipPush) {
    Write-Host "==> Pushing $Image ..."
    docker push $Image
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker push failed. Run: docker login ghcr.io"
    }
    # kind nodes use IfNotPresent — GHCR push alone does not refresh the cluster image.
    Write-Host "==> Loading image into kind (am-preprod) ..."
    & "$PocDir\.venv\Scripts\python.exe" "$ScriptDir\kind-load-local.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "kind-load-local.py failed; cluster may keep a stale spt-dev image."
    }
}

Write-Host "==> Applying k8s manifests ..."
kubectl apply -f "$PocDir\k8s\namespace.yaml"
kubectl apply -f "$PocDir\k8s\pvc.yaml"
kubectl apply -f "$PocDir\k8s\deployment.yaml"

Write-Host "==> Set image tag $ImageTag on deployment ..."
kubectl set image deployment/am-spt-poc am-spt-poc=$Image -n $Namespace

Write-Host "==> Restarting deployment to pick up new image ..."
kubectl rollout restart deployment/am-spt-poc -n $Namespace

Write-Host "==> Waiting for rollout ..."
kubectl rollout status deployment/am-spt-poc -n $Namespace --timeout=180s

kubectl get pods,svc,ingress -n $Namespace -l app=am-spt-poc
Write-Host ""
Write-Host "Portal: https://am.asrax.in/spt-poc/ui"
Write-Host "Health: https://am.asrax.in/spt-poc/health"
