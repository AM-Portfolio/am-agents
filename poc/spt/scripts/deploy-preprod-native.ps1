# DEPRECATED — pip-on-start init containers fail on this cluster (PyPI/egress timeouts).
# Use scripts/deploy-dev.ps1 or scripts/vps-build-load.ps1 instead (pre-built image).
param(
    [string]$KubeConfig = "",
    [string]$Namespace = "load-testing",
    [switch]$SkipVendorSeed
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PocDir = Split-Path -Parent $ScriptDir
$AmReposRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PocDir))
$DefaultKubeConfig = Join-Path $AmReposRoot "VPS\VPS\kubeconfig.vps"

if (-not $KubeConfig) { $KubeConfig = $DefaultKubeConfig }
if (-not (Test-Path $KubeConfig)) { Write-Error "Kubeconfig not found: $KubeConfig" }

$env:KUBECONFIG = $KubeConfig
Write-Host "Using KUBECONFIG: $KubeConfig"
Write-Host "Namespace: $Namespace"

Write-Host "==> Removing legacy resources from am-apps-preprod (if any) ..."
kubectl delete deployment,service,ingress,configmap am-spt-poc am-spt-poc-src -n am-apps-preprod --ignore-not-found 2>$null

Write-Host "==> Ensuring namespace $Namespace ..."
kubectl apply -f "$PocDir\k8s\namespace.yaml"
kubectl apply -f "$PocDir\k8s\pvc.yaml"

if (-not $SkipVendorSeed) {
    Write-Host "==> Seeding vendor wheels on PVC (offline pip for init) ..."
    $vendorTar = Join-Path $env:TEMP "am-spt-vendor.tar.gz"
    if (-not (Test-Path "$PocDir\vendor\wheels")) {
        Write-Error "Missing vendor/wheels - run pip download first (see README)"
    }
    Push-Location $PocDir
    if (Test-Path "vendor\bin\k6") {
        tar -czf $vendorTar vendor/wheels vendor/bin/k6
    } else {
        tar -czf $vendorTar vendor/wheels
    }
    Pop-Location

    kubectl delete pod spt-vendor-seed -n $Namespace --ignore-not-found 2>$null | Out-Null
    $seedFile = Join-Path $PocDir "k8s\vendor-seed-pod.json"
    $overrides = Get-Content $seedFile -Raw
    kubectl run spt-vendor-seed -n $Namespace --restart=Never --image=busybox --overrides=$overrides
    kubectl wait --for=condition=Ready pod/spt-vendor-seed -n $Namespace --timeout=120s
    kubectl exec -n $Namespace spt-vendor-seed -- mkdir -p /data/vendor
    kubectl cp "$vendorTar" "${Namespace}/spt-vendor-seed:/tmp/vendor.tar.gz"
    kubectl exec -n $Namespace spt-vendor-seed -- sh -c 'cd /data; tar -xzf /tmp/vendor.tar.gz; ls vendor/wheels | head'
    kubectl delete pod spt-vendor-seed -n $Namespace --wait=true
}

Write-Host "==> Packaging source tarball (app only) ..."
$tarPath = Join-Path $env:TEMP "am-spt-poc-src.tar"
Push-Location $PocDir
tar -cf $tarPath app k6 playwright catalog requirements.txt
Pop-Location

Write-Host "==> Creating ConfigMap in $Namespace ..."
kubectl create configmap am-spt-poc-src -n $Namespace `
    --from-file=src.tar=$tarPath `
    --dry-run=client -o yaml | kubectl apply -f -

Write-Host "==> Applying k8s manifests ..."
kubectl apply -f "$PocDir\k8s\deployment.yaml"
Write-Host "==> Restarting pod ..."
kubectl rollout restart deployment/am-spt-poc -n $Namespace

Write-Host "==> Waiting for rollout ..."
kubectl -n $Namespace rollout status deployment/am-spt-poc --timeout=600s

kubectl -n $Namespace get pods,svc,ingress -l app=am-spt-poc
Write-Host ""
Write-Host "Verify:"
Write-Host "  curl https://am-dev.asrax.in/spt-poc/health"
Write-Host "  Portal: https://am-dev.asrax.in/spt-poc/ui"
