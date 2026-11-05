<#
ToolDojo Node - undo node\install.ps1 (v3-N.1). Run in an ADMIN PowerShell.

    powershell -ExecutionPolicy Bypass -File C:\ToolDojo\app\node\uninstall.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File C:\ToolDojo\app\node\uninstall.ps1
    ... -RemoveAccount      also delete the 'tooldojo' user
    ... -RemoveFiles        also delete C:\ToolDojo (code, logs AND the .env with your keys)

By default it stops and removes the task, kills the node's own processes (only programs
that live under C:\ToolDojo), and restores the power / Windows Update values that
install.ps1 saved in data\install_backup.json. Files and the account are kept.
#>
param(
    [switch]$DryRun,
    [string]$Root = "C:\ToolDojo",
    [string]$Account = "tooldojo",
    [switch]$RemoveAccount,
    [switch]$RemoveFiles
)
$ErrorActionPreference = "Continue"
$TaskName = "ToolDojo Node"
$Data = Join-Path $Root "data"
$script:N = 0

function Step([string]$What, [scriptblock]$Do) {
    $script:N++
    if ($DryRun) { Write-Output ("WOULD [{0,2}] {1}" -f $script:N, $What); return }
    Write-Output ("DO    [{0,2}] {1}" -f $script:N, $What)
    try { & $Do } catch { Write-Output ("      FAILED: " + $_.Exception.Message) }
}

function Set-RegDword([string]$Path, [string]$Name, $Value) {
    if ($null -eq $Value) {
        Remove-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
        return
    }
    if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
    New-ItemProperty -Path $Path -Name $Name -Value ([int]$Value) -PropertyType DWord -Force | Out-Null
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $DryRun) {
    Write-Output "Please run this in an ADMIN PowerShell."
    exit 2
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Step "stop and unregister the task '$TaskName'" {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
} else {
    Write-Output "  task    : '$TaskName' is not installed"
}

Step "kill any process still running from $Root (python, ffmpeg, chromium of the node; by PID, nothing else)" {
    $prefix = $Root.TrimEnd("\") + "\"
    Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$backupPath = Join-Path $Data "install_backup.json"
if (Test-Path $backupPath) {
    $b = Get-Content $backupPath -Raw | ConvertFrom-Json
    Step "restore sleep / hibernate / lid power values saved at install" {
        if ($b.standby) {
            & powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE $b.standby.ac
            & powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE $b.standby.dc
        }
        if ($b.hibernate) {
            & powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE $b.hibernate.ac
            & powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE $b.hibernate.dc
        }
        if ($b.lid) {
            & powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION $b.lid.ac
        }
        & powercfg /setactive SCHEME_CURRENT
    }
    Step "restore Fast Startup, Windows Update active hours and the auto-restart policy saved at install" {
        Set-RegDword "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" "HiberbootEnabled" $b.HiberbootEnabled
        Set-RegDword "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "ActiveHoursStart" $b.ActiveHoursStart
        Set-RegDword "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "ActiveHoursEnd" $b.ActiveHoursEnd
        Set-RegDword "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "SmartActiveHoursState" $b.SmartActiveHoursState
        Set-RegDword "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" "NoAutoRebootWithLoggedOnUsers" $b.NoAutoRebootWithLoggedOnUsers
    }
} else {
    Write-Output "  backup  : no $backupPath - power and update settings left as they are"
}

if ($RemoveAccount) {
    Step "delete the local user '$Account' and unhide-list entry (its profile folder under C:\Users stays)" {
        Remove-LocalUser -Name $Account -ErrorAction SilentlyContinue
        Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList" -Name $Account -ErrorAction SilentlyContinue
    }
} else {
    Step "disable the local user '$Account' (kept; -RemoveAccount deletes it)" {
        Disable-LocalUser -Name $Account -ErrorAction SilentlyContinue
    }
}

if ($RemoveFiles) {
    Step "DELETE $Root (code, venv, logs and the .env holding your stream key)" {
        Remove-Item -Recurse -Force $Root
    }
} else {
    Write-Output "  files   : $Root kept (-RemoveFiles deletes it, including .env)"
}

if ($DryRun) { Write-Output "Dry run finished: $script:N actions listed, nothing changed." }
else { Write-Output "Uninstalled. Nothing will start at boot any more." }
exit 0
