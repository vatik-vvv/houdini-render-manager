# Create GitHub repo and push (run once after: gh auth login)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    $portable = Join-Path $env:TEMP "gh-cli\bin\gh.exe"
    if (Test-Path $portable) { $gh = $portable } else {
        Write-Host "Install GitHub CLI: https://cli.github.com/  then run: gh auth login"
        exit 1
    }
} else {
    $gh = $gh.Source
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
