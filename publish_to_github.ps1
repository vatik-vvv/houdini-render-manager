# Create GitHub repo (if needed) and push. Run once after: .\tools\gh-auth-login.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$localGh = Join-Path $PSScriptRoot "tools\gh\bin\gh.exe"
$ghCmd = Get-Command gh -ErrorAction SilentlyContinue
if ($ghCmd) {
    $gh = $ghCmd.Source
} elseif (Test-Path $localGh) {
    $gh = $localGh
} else {
    Write-Host "GitHub CLI not found. Run:"
    Write-Host "  .\tools\install_gh.ps1"
    Write-Host "  .\tools\gh-auth-login.ps1"
    exit 1
}

& $gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Run: .\tools\gh-auth-login.ps1"
    exit 1
}

$repo = "houdini-render-manager"
$user = & $gh api user -q .login
$remoteUrl = "https://github.com/$user/$repo.git"

$hasOrigin = @(git remote 2>$null) -contains "origin"
if ($hasOrigin) {
    git remote set-url origin $remoteUrl
} else {
    git remote add origin $remoteUrl
}

$repoExists = $false
& $gh repo view "$user/$repo" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    $repoExists = $true
}

if (-not $repoExists) {
    Write-Host "Creating $remoteUrl ..."
    & $gh repo create $repo --public `
        --description "Houdini Render Manager — render queue GUI for Houdini ROPs"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create repository"
    }
} else {
    Write-Host "Repository already exists: $remoteUrl"
}

Write-Host "Pushing branch main..."
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Done: $remoteUrl"
