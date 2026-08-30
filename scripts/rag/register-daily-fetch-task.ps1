# Register (or refresh) the daily 08:00 Windows task that pokes Jarvis Daily Fetch.
$ErrorActionPreference = "Stop"
$Poke = Join-Path $PSScriptRoot "poke-daily-fetch.ps1"
if (-not (Test-Path $Poke)) {
    Write-Error "Missing poke script: $Poke"
    exit 1
}
$TaskName = "JarvisDailyFetchPoke"
$Arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Poke`""
try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Arg
    $trigger = New-ScheduledTaskTrigger -Daily -At "08:00"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable:$false
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Registered scheduled task $TaskName at 08:00 daily"
} catch {
    # Fallback when ScheduledTasks cmdlets are unavailable
    $tr = "powershell.exe $Arg"
    schtasks /Create /TN $TaskName /TR $tr /SC DAILY /ST 08:00 /F
}
