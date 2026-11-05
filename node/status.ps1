<#
ToolDojo Node - health summary (v3-N.1). No admin needed, changes nothing.

    powershell -ExecutionPolicy Bypass -File C:\ToolDojo\app\node\status.ps1

Exit code 0 = healthy, 1 = something needs a look (the reason is printed).
#>
param([string]$Root = "C:\ToolDojo")
$ErrorActionPreference = "Continue"
$TaskName = "ToolDojo Node"
$Data = Join-Path $Root "data"
$problems = @()

Write-Output "=== ToolDojo Node status  ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') local, $((Get-Date).ToUniversalTime().ToString('HH:mm')) UTC)"

# --- the scheduled task
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Output ("Task      : {0}; last run {1}, result 0x{2:X}; runs as {3}" -f $task.State, $info.LastRunTime, $info.LastTaskResult, $task.Principal.UserId)
    if ($task.State -eq "Disabled") { $problems += "the task is disabled" }
} else {
    Write-Output "Task      : NOT INSTALLED"
    $problems += "the task is not installed (run node\install.ps1)"
}

# --- the supervisor's own heartbeat
$statusPath = Join-Path $Data "status.json"
if (-not (Test-Path $statusPath)) {
    Write-Output "Supervisor: no status.json yet"
    $problems += "no heartbeat file"
} else {
    $s = Get-Content $statusPath -Raw | ConvertFrom-Json
    $age = ((Get-Date).ToUniversalTime() - ([DateTimeOffset]::Parse($s.updated)).UtcDateTime).TotalSeconds
    $alive = "ALIVE"
    if ($age -gt 120) { $alive = "NOT RUNNING"; $problems += ("no heartbeat for {0:N0} s" -f $age) }
    Write-Output ("Supervisor: {0} (heartbeat {1:N0} s ago, pid {2}, since {3}, code {4})" -f $alive, $age, $s.pid, $s.boot, $s.version)
    if ($s.paused) { Write-Output ("Paused    : " + $s.paused) }
    Write-Output ("Network   : {0}   clock skew: {1} s   disk free: {2} GB   import check: {3}" -f $s.network_ok, $s.clock_skew_s, $s.disk_free_gb, $s.import_ok)
    if ($s.import_ok -eq $false) { $problems += "the code fails its import check" }
    if ($s.disk_ok -eq $false) { $problems += "disk below the floor" }
    if ($s.update) { Write-Output ("Update    : " + $s.update) }
    Write-Output ("Profile   : {0} {1} - {2}" -f $s.profile.stream_profile, $s.profile.encoder, $s.profile.verdict)
    if ($s.profile.stream_profile -eq "insufficient") { $problems += "preflight says the hardware is insufficient" }
    foreach ($e in $s.job_table_errors) { Write-Output ("Job table : ERROR " + $e); $problems += "job table error" }
    Write-Output "Jobs:"
    foreach ($p in $s.jobs.PSObject.Properties) {
        $j = $p.Value
        $state = "idle"
        if ($j.running) { $state = "RUNNING pid " + $j.pid + " (silent " + $j.silent_s + " s)" }
        elseif ($j.done) { $state = "done for this slot" }
        elseif ($j.skipped) { $state = "skipped: " + $j.skipped }
        if (-not $j.enabled) { $state = "disabled" }
        Write-Output ("  {0,-12} {1,-26} {2}" -f $p.Name, $j.window, $state)
        Write-Output ("  {0,-12} next window {1}; slot {2}: attempts {3}, last exit {4} {5}" -f "", $j.next_window, $j.slot, $j.attempts, $j.last_exit, $j.last_reason)
    }
}

# --- the end of the supervisor log
$logPath = Join-Path $Data "logs\supervisor.log"
if (Test-Path $logPath) {
    Write-Output "Last log lines ($logPath):"
    Get-Content $logPath -Tail 12 | ForEach-Object { Write-Output ("  " + $_) }
}

if ($problems.Count -eq 0) {
    Write-Output "RESULT: healthy"
    exit 0
}
Write-Output ("RESULT: needs a look - " + ($problems -join "; "))
exit 1
