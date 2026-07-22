# Deploy am-spt-poc to preprod (kind-am-preprod on VPS)
param(
    [string]$KubeConfig = "",
    [string]$Namespace = "load-testing",
    [string]$ReleaseName = "am-spt-poc",
    [string]$ImageTag = "local",
    [switch]$SkipBuild,
    [switch]$LocalPoc
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PocDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PocDir)
$AmReposRoot = Split-Path -Parent $RepoRoot
$DefaultKubeConfig = Join-Path $AmReposRoot "VPS\VPS\kubeconfig.vps"

if (-not $KubeConfig) {
    $KubeConfig = $DefaultKubeConfig
}
if (-not (Test-Path $KubeConfig)) {
    Write-Error "Kubeconfig not found: $KubeConfig"
}

$PipelinesChart = Join-Path $AmReposRoot "am-pipelines\helm\universal-chart"

if (-not (Test-Path $PipelinesChart)) {
    Write-Error "universal-chart not found at $PipelinesChart"
}

$env:KUBECONFIG = $KubeConfig

if (-not $SkipBuild) {
    Write-Host "==> Building Docker image am-spt-poc:$ImageTag ..."
    docker build -t "ghcr.io/am-portfolio/am-spt-poc:$ImageTag" $PocDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed. Start Docker Desktop or use CI publish, then deploy with -SkipBuild -ImageTag <tag>"
    }
}

$ValuesFiles = @("$PocDir\helm\values.yaml")
if ($LocalPoc) {
    $ValuesFiles += "$PocDir\helm\values.preprod-local.yaml"
} else {
    $ValuesFiles += @("$PocDir\helm\vault-mappings.yaml", "$PocDir\helm\values.preprod.yaml")
}

$HelmArgs = @(
    "upgrade", "--install", $ReleaseName, $PipelinesChart,
    "--namespace", $Namespace,
    "--create-namespace",
    "--set", "global.image.registry=ghcr.io/am-portfolio",
    "--set", "global.image.tag=$ImageTag",
    "--set", "global.image.pullPolicy=IfNotPresent",
    "--set", "language=python"
)
foreach ($vf in $ValuesFiles) {
    $HelmArgs += @("-f", $vf)
}
$HelmArgs += @("--wait", "--timeout", "5m")

Write-Host "==> Helm upgrade --install $ReleaseName ..."
& helm @HelmArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Pods:"
kubectl -n $Namespace get pods -l "app.kubernetes.io/instance=$ReleaseName"

Write-Host ""
Write-Host "Verify:"
Write-Host "  curl https://am.asrax.in/spt-poc/health"
Write-Host "  curl https://am.asrax.in/spt-poc/ping"
