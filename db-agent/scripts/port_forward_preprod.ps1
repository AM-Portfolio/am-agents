# Port-forward preprod infra for local db-agent testing (run in separate terminals).
# Requires kubectl context pointing at preprod cluster.

Write-Host "Starting preprod port-forwards (Ctrl+C to stop each job)..." -ForegroundColor Cyan
Write-Host @"

  LiteLLM (required for LLM_ROUTING=direct):  localhost:4000
  MongoDB:   localhost:27017
  Redis:     localhost:6379
  Postgres:  localhost:5432
  Kafka:     localhost:9092
             peek/consume also needs broker DNS OR set KAFKA_UI_URL (see .env.preprod)
  InfluxDB:  localhost:8086

  Qdrant uses https://qdrant.munish.org (no forward needed).
  Optional gateway: cd am-platform/am-mcp-gateway && npm run preprod

"@

$jobs = @(
    @{ Ns = "am-ai";   Svc = "litellm";     Port = "4000:4000" },
    @{ Ns = "infra";   Svc = "mongodb";     Port = "27017:27017" },
    @{ Ns = "infra";   Svc = "redis";       Port = "6379:6379" },
    @{ Ns = "infra";   Svc = "postgresql";  Port = "5432:5432" },
    @{ Ns = "infra";   Svc = "kafka";       Port = "9092:9092" },
    @{ Ns = "infra";   Svc = "influxdb";    Port = "8086:8086" }
)

foreach ($j in $jobs) {
    Start-Job -Name "$($j.Svc)-pf" -ScriptBlock {
        param($ns, $svc, $port)
        kubectl -n $ns port-forward "svc/$svc" $port
    } -ArgumentList $j.Ns, $j.Svc, $j.Port | Out-Null
    Write-Host "  -> $($j.Svc) :$($j.Port.Split(':')[0])" -ForegroundColor Green
}

Write-Host "`nJobs running. Check: Get-Job | Receive-Job" -ForegroundColor Yellow
Write-Host "Stop all: Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Yellow
Wait-Job
