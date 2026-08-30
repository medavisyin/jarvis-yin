# OS-level 08:00 poke: wake Jarvis via HTTP so Daily Fetch can start while the display is off.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $Root "logs"
$Log = Join-Path $LogDir "daily-fetch-scheduler.log"
$Url = "http://127.0.0.1:18889/api/toolbar/daily-fetch/scheduler"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
try {
    $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 20
    Add-Content -Path $Log -Value "$ts result=task_poke status=$($resp.StatusCode)" -Encoding utf8
} catch {
    Add-Content -Path $Log -Value "$ts result=task_poke_failed $($_.Exception.Message)" -Encoding utf8
}
exit 0
