# Build offline image on VPS (no local Docker) and load into kind-am-preprod
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PocDir = Split-Path -Parent $ScriptDir
$PocParent = Split-Path -Parent $PocDir
$tar = Join-Path $env:TEMP "am-spt-poc-build.tar.gz"

Write-Host "==> Packaging POC ..."
tar -czf $tar -C $PocParent spt

Write-Host "==> Building on VPS + kind load ..."
python "$ScriptDir\vps-build-load.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Done. Deploy with: .\scripts\deploy-dev.ps1 -SkipBuild -SkipPush"
