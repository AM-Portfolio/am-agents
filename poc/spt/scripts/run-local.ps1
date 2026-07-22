# Run SPT portal locally with .env - no Docker/VPS deploy needed
param(
    [int]$Port = 8150,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$PocDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $PocDir

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - set SPT_AUTH_PASSWORD then re-run."
}

if (-not (Test-Path ".venv")) {
    Write-Host "==> Creating .venv ..."
    python -m venv .venv
}

$py = Join-Path $PocDir ".venv\Scripts\python.exe"
$pip = Join-Path $PocDir ".venv\Scripts\pip.exe"
if (-not $SkipInstall) {
    Write-Host "==> Installing requirements ..."
    & $pip install -q -r requirements.txt
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null

$k6Win = Join-Path $PocDir "vendor\bin\k6.exe"
$k6Lin = Join-Path $PocDir "vendor\bin\k6"
if (Test-Path $k6Win) {
    Write-Host "k6: $k6Win"
} elseif (Test-Path $k6Lin) {
    Write-Warning "vendor\bin\k6 is Linux - on Windows set K6_BIN=./vendor/bin/k6.exe"
} else {
    Write-Warning "k6 not found - set K6_BIN in .env"
}

# Free port if a stale uvicorn is holding it (common after hung k6 runs)
$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($c in $listeners) {
    $opid = $c.OwningProcess
    if ($opid -and $opid -gt 0) {
        Write-Host "==> Freeing port $Port (PID $opid) ..."
        Stop-Process -Id $opid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Host "Portal:  http://localhost:$Port/ui"
Write-Host "Health:  http://localhost:$Port/health"
Write-Host "Runs return immediately; UI auto-refreshes while status=running"
Write-Host ""

& $py -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
