# Pre-commit scan: fail if staged/new files contain likely secrets.
# Does NOT delete or modify any files — read-only check.
# Run from am-agents/: .\scripts\check-no-secrets.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$secretPatterns = @(
    @{ Name = "mongo_uri"; Pattern = "mongodb://[^/\s""']+:[^@\s""']+@" },
    @{ Name = "postgres_uri"; Pattern = "postgresql://[^/\s""']+:[^@\s""']+@" },
    @{ Name = "redis_uri"; Pattern = "redis://:[^@\s""']+@" },
    @{ Name = "litellm_key"; Pattern = "LITELLM_MASTER_KEY=sk-[a-zA-Z0-9]{20,}" },
    @{ Name = "langfuse_secret"; Pattern = "LANGFUSE_SECRET_KEY=sk-lf-[a-zA-Z0-9-]{20,}" },
    @{ Name = "mcp_secret"; Pattern = "AM_MCP_CLIENT_SECRET=[a-zA-Z0-9]{16,}" },
    @{ Name = "kafka_password"; Pattern = "KAFKA_PASSWORD=[^#\r\n""']{8,}" },
    @{ Name = "influx_token"; Pattern = "INFLUX_TOKEN=[a-zA-Z0-9_-]{24,}" }
)

$allowlistPaths = @(
    "db-agent/tests/test_observability.py",
    "scripts/check-no-secrets.ps1"
)

function Test-GitIgnored([string]$RelPath) {
    if (-not (Test-Path ".git")) { return $false }
    git check-ignore -q $RelPath 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-ShouldSkip([string]$RelPath) {
    $norm = $RelPath.Replace("\", "/")
    if (Test-GitIgnored $RelPath) { return $true }
    if ($norm -match "\.env\.(preprod|prod|local)$") { return $true }
    if ($norm -eq ".env") { return $true }
    if ($norm -match "/logs/" -and $norm -notmatch "/logs/README\.md$") { return $true }
    return $false
}

function Get-ScanFiles {
    if (Test-Path ".git") {
        $staged = @(git diff --cached --name-only --diff-filter=ACM 2>$null)
        $candidates = $staged | Where-Object { $_ }
        if ($candidates.Count -gt 0) { return $candidates }
        Write-Host "No staged files; scanning tracked files that differ from HEAD." -ForegroundColor Yellow
        return @(git diff --name-only --diff-filter=ACM 2>$null) +
            @(git ls-files --others --exclude-standard 2>$null) |
            Where-Object { $_ } |
            Select-Object -Unique
    }
    Write-Host "No git repo; scanning source tree (respecting .gitignore patterns)." -ForegroundColor Yellow
    $files = Get-ChildItem -Recurse -File |
        Where-Object {
            $rel = $_.FullName.Substring($Root.Length + 1).Replace("\", "/")
            $rel -notmatch "^(node_modules|\.pytest_cache|__pycache__|\.venv)/" -and
            $rel -notmatch "/(node_modules|\.pytest_cache|__pycache__|\.venv)/"
        } |
        ForEach-Object { $_.FullName.Substring($Root.Length + 1) }
    return $files | Where-Object { -not (Test-ShouldSkip $_) }
}

$failures = @()

foreach ($rel in Get-ScanFiles) {
    $norm = $rel.Replace("\", "/")
    if (Test-ShouldSkip $rel) { continue }
    if ($allowlistPaths -contains $norm) { continue }
    if ($norm -match "(^|/)\.env(\.|$)" -and $norm -notmatch "\.env\.example$") {
        $failures += "ENV FILE MUST NOT BE COMMITTED: $rel"
        continue
    }
    if (-not (Test-Path $rel)) { continue }
    if ($rel -match "\.(png|jpg|gif|ico|woff|pyc|log)$") { continue }
    $content = Get-Content -Raw -Path $rel -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    foreach ($rule in $secretPatterns) {
        if ($content -match $rule.Pattern) {
            $failures += "$($rule.Name) matched in $rel"
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Host "SECRET CHECK FAILED:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}

$count = @(Get-ScanFiles).Count
Write-Host "Secret check passed ($count files scanned)." -ForegroundColor Green
exit 0
