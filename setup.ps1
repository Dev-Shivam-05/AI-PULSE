# =====================================================================
#  FactVerse — one-shot Windows setup
#  Run from the project root:   powershell -ExecutionPolicy Bypass -File setup.ps1
# =====================================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host "==> FactVerse setup in $root" -ForegroundColor Cyan

# 1) ffmpeg (provides ffmpeg + ffprobe)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "==> Installing ffmpeg via winget (Gyan.FFmpeg)..." -ForegroundColor Yellow
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "   (You may need to open a NEW terminal so ffmpeg lands on PATH.)" -ForegroundColor DarkYellow
} else {
    Write-Host "ffmpeg already installed." -ForegroundColor Green
}

# 2) virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "==> Creating virtual environment (.venv)..." -ForegroundColor Yellow
    py -3 -m venv .venv
}
$py = Join-Path $root ".venv\Scripts\python.exe"

# 3) dependencies
Write-Host "==> Installing Python dependencies..." -ForegroundColor Yellow
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

# 4) secrets
if (-not (Test-Path ".env")) {
    Write-Host "==> Creating .env from template (fill in your keys)..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

# 5) verify
Write-Host "==> Verifying configuration..." -ForegroundColor Yellow
& $py -m factverse.config

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  1) Edit .env with your API keys / account creds"
Write-Host "  2) One-time YouTube auth:   .\.venv\Scripts\python scripts\factverse_engine.py auth"
Write-Host "  3) Test run:                .\.venv\Scripts\python scripts\factverse_engine.py"
