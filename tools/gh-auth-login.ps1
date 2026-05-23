# Run GitHub login using project-local gh.exe
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$ghExe = Join-Path $root "tools\gh\bin\gh.exe"

if (-not (Test-Path $ghExe)) {
    Write-Host "GitHub CLI not found. Run first: .\tools\install_gh.ps1"
    exit 1
}

Write-Host "Starting login (choose GitHub.com, HTTPS, login via browser)..."
& $ghExe auth login
