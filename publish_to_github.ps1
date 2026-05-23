# Create GitHub repo and push (run once after: .\tools\gh-auth-login.ps1)
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
    Write-Host "Not logged in. Run: gh auth login"
    exit 1
}

$repo = "houdini-render-manager"
$remoteUrl = "https://github.com/$(& $gh api user -q .login)/$repo.git"

if (git remote get-url origin 2>$null) {
    git remote remove origin
}

& $gh repo create $repo --public `
    --description "Houdini Render Manager — render queue GUI for Houdini ROPs" `
    --source . `
    --remote origin `
    --push

Write-Host "Done: $remoteUrl"
