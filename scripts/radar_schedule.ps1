<#
v3-L.2 ToolDojo Radar Live - daily schedule (docs/spec/ai-pulse-v3l2.md row 24).

    powershell -ExecutionPolicy Bypass -File scripts\radar_schedule.ps1 -DryRun     # show, change nothing
    powershell -ExecutionPolicy Bypass -File scripts\radar_schedule.ps1 -Install    # daily 20:00 local
    powershell -ExecutionPolicy Bypass -File scripts\radar_schedule.ps1 -Install -At 21:00
    powershell -ExecutionPolicy Bypass -File scripts\radar_schedule.ps1 -Uninstall  # the off switch

Install ONLY after the private test stream looked right (spec section 6, step 4).
The task runs as the current user (no admin rights), only while that user is signed in
(a locked screen is fine), wakes the PC from sleep, never starts on battery, never runs
twice at once, and is stopped by Windows after 3 hours whatever happens (sessions are
capped at 120 min in the script itself).
#>
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$DryRun,
    [string]$At = "20:00"
)
$ErrorActionPreference = "Stop"
$TaskName = "ToolDojo Radar Live"
$Root = Split-Path -Parent $PSScriptRoot

if ($At -notmatch '^([01]\d|2[0-3]):[0-5]\d$') {
    Write-Output "-At must be HH:MM (24 h), got '$At'"
    exit 2
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Removed '$TaskName'. Radar Live will not start again."
    } else {
        Write-Output "'$TaskName' is not installed."
    }
    exit 0
}

# pyw = the Python launcher without a console window, so nothing pops up at 20:00
$launcher = Get-Command pyw -ErrorAction SilentlyContinue
if (-not $launcher) { $launcher = Get-Command py -ErrorAction Stop }
$script = Join-Path $Root "scripts\radar_live.py"
if (-not (Test-Path $script)) {
    Write-Output "Cannot find $script"
    exit 2
}

$plan = [ordered]@{
    Task      = $TaskName
    Runs      = "$($launcher.Source) -3 scripts\radar_live.py"
    In        = $Root
    Daily     = $At
    User      = "$env:USERDOMAIN\$env:USERNAME (signed in; no admin)"
    WakePC    = "yes"
    Battery   = "never starts on battery"
    TimeLimit = "3 h"
}
$plan.GetEnumerator() | ForEach-Object { Write-Output ("{0,-10} {1}" -f $_.Key, $_.Value) }

if ($DryRun -or -not $Install) {
    Write-Output "Dry run: nothing was registered. Use -Install to register it."
    exit 0
}

$action = New-ScheduledTaskAction -Execute $launcher.Source -Argument "-3 scripts\radar_live.py" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -WakeToRun -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "ToolDojo Radar Live: automated live board (docs/spec/ai-pulse-v3l2.md). Remove with scripts\radar_schedule.ps1 -Uninstall." | Out-Null
Write-Output "Installed '$TaskName' daily at $At. Logs: logs\radar_live.log"
