# Downloads portable GitHub CLI into tools\gh\bin (no admin / winget required)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$targetBin = Join-Path $root "tools\gh\bin"
$ghExe = Join-Path $targetBin "gh.exe"

if (Test-Path $ghExe) {
    Write-Host "GitHub CLI already installed: $ghExe"
    & $ghExe --version
    exit 0
}

$version = "2.63.2"
$zipUrl = "https://github.com/cli/cli/releases/download/v${version}/gh_${version}_windows_amd64.zip"
$zipPath = Join-Path $env:TEMP "gh_windows_amd64.zip"
$extractRoot = Join-Path $env:TEMP "gh_extract_$version"

Write-Host "Downloading GitHub CLI $version..."
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

if (Test-Path $extractRoot) {
    Remove-Item $extractRoot -Recurse -Force
}
Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

$binDir = Get-ChildItem -Path $extractRoot -Recurse -Directory -Filter "bin" |
    Where-Object { Test-Path (Join-Path $_.FullName "gh.exe") } |
    Select-Object -First 1

if (-not $binDir) {
    Write-Error "gh.exe not found inside downloaded archive"
}

New-Item -ItemType Directory -Path $targetBin -Force | Out-Null
Copy-Item -Path (Join-Path $binDir.FullName "*") -Destination $targetBin -Force

Remove-Item $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

Write-Host "Installed: $ghExe"
& $ghExe --version
