<#
ToolDojo Node - one-time installer (v3-N.1, docs/spec/ai-pulse-v3n1.md).

Run it ONCE, in an ADMIN PowerShell, from the folder you unzipped the bundle into:

    powershell -ExecutionPolicy Bypass -File node\install.ps1            # install
    powershell -ExecutionPolicy Bypass -File node\install.ps1 -DryRun    # print every action, change nothing

What it does (every step prints first; -DryRun prints and stops there):
  1. prerequisites: Python 3.11, git, ffmpeg (winget, with manual fallbacks printed)
  2. C:\ToolDojo\{app,data,venv,bin,ms-playwright}; the code is a git clone of the bundle's
     branch (so the node can update itself), or the ZIP snapshot when the clone fails
  3. the venv, node\requirements-node.txt, Playwright's Chromium
  4. .env: asks for the stream URL/key and the optional keys ONCE (or -EnvFile <path>)
  5. a local standard user "tooldojo" with a random password nobody needs to know,
     hidden from the sign-in screen; folder permissions locked to it + admins
  6. power: never sleep/hibernate (AC and battery), lid does nothing on AC, Fast Startup off
  7. Windows Update: active hours 08:00-02:00, no auto-restart while signed in (Home may
     ignore that policy), time sync service on
  8. the "ToolDojo Node" scheduled task: at start-up + every 5 min (a no-op while it runs),
     whether or not anyone is signed in (session 0: it can never show a window)
  9. starts it once, waits for the encoder preflight, prints the verdict and status

Re-running is safe: existing code, .env and account are kept (the password is re-rolled).
Undo: node\uninstall.ps1.
#>
param(
    [switch]$DryRun,
    [string]$Root = "C:\ToolDojo",
    [string]$EnvFile = "",
    [string]$Account = "tooldojo",
    [switch]$SkipPrereqs,
    [switch]$Remeasure
)
$ErrorActionPreference = "Continue"
$Bundle = Split-Path -Parent $PSScriptRoot
$App = Join-Path $Root "app"
$Data = Join-Path $Root "data"
$Venv = Join-Path $Root "venv"
$Bin = Join-Path $Root "bin"
$PwDir = Join-Path $Root "ms-playwright"
$TaskName = "ToolDojo Node"
$RepoUrl = "https://github.com/Dev-Shivam-05/AI-PULSE.git"
$script:N = 0
$script:Failed = @()

function Say([string]$Text) { Write-Output $Text }

function Step([string]$What, [scriptblock]$Do) {
    $script:N++
    if ($DryRun) {
        Say ("WOULD [{0,2}] {1}" -f $script:N, $What)
        return
    }
    Say ("DO    [{0,2}] {1}" -f $script:N, $What)
    try {
        & $Do
    } catch {
        Say ("      FAILED: " + $_.Exception.Message)
        $script:Failed += $What
    }
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    # PowerShell 5.1's Out-File/Set-Content write a BOM, and a BOM turns the first .env key
    # into "\ufeffYT_STREAM_URL" for Python - so write the bytes ourselves.
    $enc = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

function Test-MachineWide([string]$Path) {
    # The task runs as another account, which cannot read the owner's C:\Users\<name>
    # folder: a per-user Python or git is invisible to it, so only a machine-wide one counts.
    if (-not $Path) { return $false }
    $users = Join-Path $env:SystemDrive "Users"
    return (-not $Path.StartsWith($users, [StringComparison]::OrdinalIgnoreCase))
}

function Find-Python311 {
    $c = "C:\Program Files\Python311\python.exe"
    if (Test-Path $c) { return $c }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $out = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $p = ($out | Select-Object -First 1).Trim()
            if (Test-MachineWide $p) { return $p }
        }
    }
    return $null
}

function Find-Exe([string]$Name, [string[]]$Extra) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($e in $Extra) { if ($e -and (Test-Path $e)) { return $e } }
    $pkgs = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $pkgs) {
        $hit = Get-ChildItem -Path $pkgs -Recurse -Filter "$Name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

function Winget-Install([string]$Id, [string]$Scope) {
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $wg) { throw "winget is not available - see node\README.md 'Manual prerequisites'" }
    $args2 = @("install", "-e", "--id", $Id, "--silent", "--accept-package-agreements", "--accept-source-agreements")
    if ($Scope) { $args2 += @("--scope", $Scope) }
    & winget @args2
    Refresh-Path
}

function Get-PowerIndex([string]$Sub, [string]$Setting) {
    # "Current AC Power Setting Index: 0x00000384" - labels are localised, the hex is not
    $out = & powercfg /q SCHEME_CURRENT $Sub $Setting 2>$null
    $hex = @()
    foreach ($line in $out) {
        $m = [regex]::Match([string]$line, "0x[0-9a-fA-F]{8}\s*$")
        if ($m.Success) { $hex += [Convert]::ToInt32($m.Value.Trim(), 16) }
    }
    if ($hex.Count -ge 2) { return @{ ac = $hex[$hex.Count - 2]; dc = $hex[$hex.Count - 1] } }
    return $null
}

function Get-RegValue([string]$Path, [string]$Name) {
    $item = Get-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
    if ($item) { return $item.$Name }
    return $null
}

function Set-RegDword([string]$Path, [string]$Name, [int]$Value) {
    if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
    New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType DWord -Force | Out-Null
}

function New-RandomPassword {
    $chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_=+#%"
    $bytes = New-Object byte[] 28
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $p = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
    # guarantee every class, whatever the random draw (local password policy may ask)
    return ("Td7#" + $p)
}

function Read-Secret([string]$Prompt) {
    $sec = Read-Host -Prompt $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

# ------------------------------------------------------------------ 0. checks
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$tz = (Get-TimeZone).Id
Say "ToolDojo Node installer  (bundle: $Bundle)"
Say ("  Windows : " + $(if ($os) { $os.Caption + " " + $os.Version } else { "unknown" }))
Say "  Time zone: $tz"
Say "  Target  : $Root   account: $Account   task: '$TaskName'"
if ($DryRun) { Say "  MODE    : DRY RUN - nothing below is executed" }
if (-not $isAdmin) {
    if ($DryRun) {
        Say "  NOTE    : not elevated; a real install must run in an ADMIN PowerShell"
    } else {
        Say "Please run this in an ADMIN PowerShell (Start > type PowerShell > Run as administrator)."
        exit 2
    }
}
if ($tz -ne "India Standard Time") {
    Say "  WARNING : the PC is not on India Standard Time; jobs are scheduled in UTC (unaffected),"
    Say "            but the Windows Update active hours below assume IST."
}
if (-not (Test-Path (Join-Path $Bundle "node\supervisor.py"))) {
    Say "Cannot find node\supervisor.py next to this script - run it from the unzipped bundle."
    exit 2
}
$branch = "main"
$bundleInfo = Join-Path $Bundle "BUNDLE.json"
if (Test-Path $bundleInfo) {
    $bi = Get-Content $bundleInfo -Raw | ConvertFrom-Json
    if ($bi.update_branch) { $branch = [string]$bi.update_branch }
    Say ("  Bundle  : commit " + $bi.commit + " from " + $bi.source_branch + "; node updates from '" + $branch + "'")
}
if (Get-ScheduledTask -TaskName "ToolDojo Radar Live" -ErrorAction SilentlyContinue) {
    Say "  WARNING : the old laptop task 'ToolDojo Radar Live' exists on THIS PC; it would stream twice."
    Say "            Remove it: powershell -File scripts\radar_schedule.ps1 -Uninstall"
}

# ------------------------------------------------------------------ 1. prerequisites
$py311 = Find-Python311
$git = Find-Exe "git" @("C:\Program Files\Git\cmd\git.exe")
if (-not (Test-MachineWide $git)) { $git = $null }
$ffmpeg = Find-Exe "ffmpeg" @((Join-Path $Bin "ffmpeg.exe"), "C:\ffmpeg\bin\ffmpeg.exe")
Say ("  Found   : python3.11=" + $(if ($py311) { $py311 } else { "no" }) + "  git=" + $(if ($git) { $git } else { "no" }) + "  ffmpeg=" + $(if ($ffmpeg) { $ffmpeg } else { "no" }))

if (-not $SkipPrereqs) {
    if (-not $py311) {
        Step "winget install Python.Python.3.11 --scope machine; a per-user Python is invisible to the task's account (fallback: python.org 3.11 installer, tick 'Install for all users')" {
            Winget-Install "Python.Python.3.11" "machine"
        }
        if (-not $DryRun) { $py311 = Find-Python311 }
    }
    if (-not $git) {
        Step "winget install Git.Git --scope machine (fallback: git-scm.com installer; without git the node runs the ZIP snapshot and never self-updates)" {
            Winget-Install "Git.Git" "machine"
        }
        if (-not $DryRun) {
            $git = Find-Exe "git" @("C:\Program Files\Git\cmd\git.exe")
            if (-not (Test-MachineWide $git)) { $git = $null }
        }
    }
    if (-not $ffmpeg) {
        Step "winget install Gyan.FFmpeg (fallback: unzip a gyan.dev 'release essentials' build and put ffmpeg.exe + ffprobe.exe in $Bin)" {
            Winget-Install "Gyan.FFmpeg" ""
        }
        if (-not $DryRun) { $ffmpeg = Find-Exe "ffmpeg" @((Join-Path $Bin "ffmpeg.exe")) }
    }
}

# ------------------------------------------------------------------ 2. folders + code
Step "create $Root\{app,data,bin}" {
    foreach ($d in @($Root, $Data, $Bin)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}

$haveApp = Test-Path (Join-Path $App "node\supervisor.py")
if ($haveApp) {
    Say "  app     : $App already exists - kept as it is (the node updates itself)"
} else {
    $cloned = $false
    if ($git) {
        Step "git clone --depth 1 --branch $branch $RepoUrl $App" {
            & $git clone --quiet --depth 1 --branch $branch $RepoUrl $App
            if ($LASTEXITCODE -ne 0) { throw "git clone exited $LASTEXITCODE" }
            if (-not (Test-Path (Join-Path $App "node\supervisor.py"))) {
                # the branch exists but has no node/ yet (not merged): use the snapshot
                Remove-Item -Recurse -Force $App
                throw "branch '$branch' has no node\ folder yet; using the ZIP snapshot"
            }
        }
        if (-not $DryRun) { $cloned = Test-Path (Join-Path $App "node\supervisor.py") }
    }
    if (-not $cloned) {
        Step "if the clone failed or git is missing: copy the ZIP snapshot to $App (no git history, so self-update stays off until a re-install can clone)" {
            New-Item -ItemType Directory -Force -Path $App | Out-Null
            Get-ChildItem -Path $Bundle -Force | Where-Object { $_.Name -ne ".git" } | ForEach-Object {
                Copy-Item -Path $_.FullName -Destination $App -Recurse -Force
            }
        }
    }
}

$musicSrc = Join-Path $Bundle "assets\music\radar"
if (Test-Path $musicSrc) {
    Step "copy the radar music bed (owner's Audio Library tracks, gitignored) to $App\assets\music\radar" {
        $dst = Join-Path $App "assets\music\radar"
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Path (Join-Path $musicSrc "*.mp3") -Destination $dst -Force
    }
}

if ($ffmpeg) {
    Step "copy ffmpeg.exe + ffprobe.exe from $(Split-Path -Parent $ffmpeg) to $Bin (the task's account cannot see a per-user winget folder)" {
        $src = Split-Path -Parent $ffmpeg
        foreach ($exe in @("ffmpeg.exe", "ffprobe.exe")) {
            $s = Join-Path $src $exe
            if ((Test-Path $s) -and ($s -ne (Join-Path $Bin $exe))) { Copy-Item $s (Join-Path $Bin $exe) -Force }
        }
    }
} else {
    Say "  MISSING : ffmpeg - put ffmpeg.exe and ffprobe.exe in $Bin, then re-run this installer"
    $script:Failed += "ffmpeg"
}

# ------------------------------------------------------------------ 3. venv + deps
if ($py311 -or $DryRun) {
    Step "create the venv $Venv with Python 3.11 and pip install -r node\requirements-node.txt" {
        if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) { & $py311 -m venv $Venv }
        $vpy = Join-Path $Venv "Scripts\python.exe"
        & $vpy -m pip install --quiet --upgrade pip
        & $vpy -m pip install --quiet -r (Join-Path $App "node\requirements-node.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip install exited $LASTEXITCODE" }
    }
    Step "playwright install chromium into $PwDir (shared by the task's account; headless only)" {
        $env:PLAYWRIGHT_BROWSERS_PATH = $PwDir
        & (Join-Path $Venv "Scripts\python.exe") -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw "playwright install exited $LASTEXITCODE" }
    }
} else {
    Say "  MISSING : Python 3.11 - install it (python.org, 'Install for all users'), then re-run"
    $script:Failed += "python"
}

# ------------------------------------------------------------------ 4. credentials (.env)
$envPath = Join-Path $App ".env"
if ($EnvFile) {
    Step "copy $EnvFile to $envPath" { Copy-Item $EnvFile $envPath -Force }
} elseif ((Test-Path $envPath) -and -not $DryRun) {
    Say "  .env    : $envPath exists - kept (edit it in Notepad as admin to change a key)"
} else {
    Step "ask for YT_STREAM_URL, YT_STREAM_KEY and the optional GEMINI_API_KEY / TELEGRAM_BOT_TOKEN / NODE_TELEGRAM_CHAT_ID; write $envPath" {
        Say "      Paste each value and press Enter. Keys are typed hidden. Leave optional ones empty."
        $url = Read-Host -Prompt "YT_STREAM_URL (Studio > Go live > Stream > Stream URL, the rtmps:// one)"
        $key = Read-Secret "YT_STREAM_KEY (Stream key)"
        $gem = Read-Secret "GEMINI_API_KEY (optional, better narration)"
        $tok = Read-Secret "TELEGRAM_BOT_TOKEN (optional, failure alerts)"
        $chat = Read-Host -Prompt "NODE_TELEGRAM_CHAT_ID (optional, your own chat id for alerts)"
        $lines = @("# ToolDojo Node secrets - written by node\install.ps1. Never commit, never share.",
                   "YT_STREAM_URL=$url", "YT_STREAM_KEY=$key")
        if ($gem) { $lines += "GEMINI_API_KEY=$gem" }
        if ($tok) { $lines += "TELEGRAM_BOT_TOKEN=$tok" }
        if ($chat) { $lines += "NODE_TELEGRAM_CHAT_ID=$chat" }
        Write-Utf8NoBom $envPath (($lines -join "`r`n") + "`r`n")
        $key = $null; $gem = $null; $tok = $null
    }
}

# ------------------------------------------------------------------ 5. account + permissions
$secPw = $null
$plainPw = $null
Step "create/refresh the local standard user '$Account' (random password, never expires, not shown on the sign-in screen)" {
    $script:plainPw = New-RandomPassword
    $script:secPw = ConvertTo-SecureString $script:plainPw -AsPlainText -Force
    $u = Get-LocalUser -Name $Account -ErrorAction SilentlyContinue
    if ($u) {
        Set-LocalUser -Name $Account -Password $script:secPw -PasswordNeverExpires $true
        Enable-LocalUser -Name $Account
    } else {
        New-LocalUser -Name $Account -Password $script:secPw -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires -Description "ToolDojo Node: runs the live streams in the background. No sign-in." | Out-Null
    }
    # S-1-5-32-545 = the built-in Users group, whatever the Windows display language
    Add-LocalGroupMember -SID "S-1-5-32-545" -Member $Account -ErrorAction SilentlyContinue
    Set-RegDword "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList" $Account 0
}
Step "icacls: $Root = SYSTEM/Administrators full + '$Account' read/execute; $App and $Data = '$Account' modify; .env = '$Account' read only" {
    & icacls $Root /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "${Account}:(OI)(CI)RX" /Q | Out-Null
    & icacls $App /grant "${Account}:(OI)(CI)M" /Q | Out-Null
    & icacls $Data /grant "${Account}:(OI)(CI)M" /Q | Out-Null
    if (Test-Path $envPath) {
        & icacls $envPath /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F" "${Account}:R" /Q | Out-Null
    }
}

# ------------------------------------------------------------------ 6/7. power + updates
$backupPath = Join-Path $Data "install_backup.json"
Step "save the current power/registry values to $backupPath (uninstall.ps1 restores them)" {
    if (-not (Test-Path $backupPath)) {
        $b = [ordered]@{
            standby = Get-PowerIndex "SUB_SLEEP" "STANDBYIDLE"
            hibernate = Get-PowerIndex "SUB_SLEEP" "HIBERNATEIDLE"
            lid = Get-PowerIndex "SUB_BUTTONS" "LIDACTION"
            HiberbootEnabled = Get-RegValue "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" "HiberbootEnabled"
            ActiveHoursStart = Get-RegValue "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "ActiveHoursStart"
            ActiveHoursEnd = Get-RegValue "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "ActiveHoursEnd"
            SmartActiveHoursState = Get-RegValue "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "SmartActiveHoursState"
            NoAutoRebootWithLoggedOnUsers = Get-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" "NoAutoRebootWithLoggedOnUsers"
        }
        Write-Utf8NoBom $backupPath ($b | ConvertTo-Json -Depth 4)
    }
}
Step "powercfg: sleep never + hibernate never on AC and on battery (a laptop battery then rides through a short power cut)" {
    & powercfg /change standby-timeout-ac 0
    & powercfg /change hibernate-timeout-ac 0
    & powercfg /change standby-timeout-dc 0
    & powercfg /change hibernate-timeout-dc 0
}
Step "powercfg: closing the lid on AC does nothing (LIDACTION=0); screen may still turn off" {
    & powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
    & powercfg /setactive SCHEME_CURRENT
}
Step "registry: Fast Startup off (HiberbootEnabled=0) so every power-on is a real boot and the start-up trigger fires" {
    Set-RegDword "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" "HiberbootEnabled" 0
}
Step "registry: Windows Update active hours 08:00-02:00 local (covers 9-12 use, Radar 20:00-23:00 IST, Trials 00:10-00:45 IST), automatic active hours off" {
    Set-RegDword "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "ActiveHoursStart" 8
    Set-RegDword "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "ActiveHoursEnd" 2
    Set-RegDword "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" "SmartActiveHoursState" 0
}
Step "registry policy: NoAutoRebootWithLoggedOnUsers=1 (honoured on Pro; Windows Home may ignore it)" {
    Set-RegDword "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" "NoAutoRebootWithLoggedOnUsers" 1
}
Step "time sync: w32time service automatic + resync now (the supervisor also corrects its own schedule from an HTTPS Date header)" {
    Set-Service -Name w32time -StartupType Automatic
    Start-Service -Name w32time -ErrorAction SilentlyContinue
    & w32tm /resync /force | Out-Null
}
Say "  firewall: no rule needed - the node only makes outbound connections"

# ------------------------------------------------------------------ 8. the scheduled task
$pyw = Join-Path $Venv "Scripts\pythonw.exe"
$sup = Join-Path $App "node\supervisor.py"
$argLine = '"' + $sup + '" --data "' + $Data + '"'
Step "register task '$TaskName': $pyw $argLine ; triggers AtStartup(+30 s) and every 5 min; user $env:COMPUTERNAME\$Account, Password logon (runs whether or not anyone is signed in), RunLevel Limited; no time limit; restart on failure 999x every 1 min; never two at once; runs on battery" {
    if ($Remeasure) { Remove-Item (Join-Path $Data "node.local.json") -ErrorAction SilentlyContinue }
    $action = New-ScheduledTaskAction -Execute $pyw -Argument $argLine -WorkingDirectory $App
    $t1 = New-ScheduledTaskTrigger -AtStartup
    $t1.Delay = "PT30S"
    $t2 = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 5)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -Priority 7
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($t1, $t2) -Settings $settings -User "$env:COMPUTERNAME\$Account" -Password $script:plainPw -RunLevel Limited -Description "ToolDojo Node supervisor (docs/spec/ai-pulse-v3n1.md). Status: node\status.ps1. Remove: node\uninstall.ps1." -Force | Out-Null
    $script:plainPw = $null
}

# ------------------------------------------------------------------ 9. first start + preflight
Step "start the task now and wait (up to 20 min) for the encoder preflight it runs from inside the task" {
    Start-ScheduledTask -TaskName $TaskName
    $pf = Join-Path $Data "node.local.json"
    $deadline = (Get-Date).AddMinutes(20)
    while (-not (Test-Path $pf) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 10
        Write-Host -NoNewline "."
    }
    Write-Host ""
    $rep = Join-Path $Data "preflight_report.txt"
    if (Test-Path $rep) { Get-Content $rep } else { Say "      no preflight result yet - check node\status.ps1 in a few minutes" }
}

Say ""
if ($DryRun) {
    Say "Dry run finished: $script:N actions listed, nothing changed."
    exit 0
}
if ($script:Failed.Count -gt 0) {
    Say ("Finished WITH PROBLEMS: " + ($script:Failed -join "; "))
    Say "Fix the item(s) above and run this installer again (it is safe to re-run)."
    exit 1
}
Say "Installed. Check it any time:  powershell -ExecutionPolicy Bypass -File $App\node\status.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $App "node\status.ps1") -Root $Root
exit 0
