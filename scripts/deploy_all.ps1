# One-command upload + deploy (Windows PowerShell 5.1 compatible, ASCII only)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\deploy_all.ps1 -Ip YOUR_PUBLIC_IP
param(
    [Parameter(Mandatory = $true)][string]$Ip
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] ssh not found. Enable Windows OpenSSH Client."
    exit 1
}

$key = (Read-Host "Paste your DashScope Key (sk-...)").Trim()
if (-not $key.StartsWith("sk-")) {
    Write-Host "[WARN] Key does not start with sk-"
}

$src = (Resolve-Path "$PSScriptRoot\..").Path
$opt = @("-o", "StrictHostKeyChecking=accept-new")

Write-Host "==> [1/3] create ~/memcomp (enter root password)"
ssh @opt "root@$Ip" "mkdir -p ~/memcomp"

Write-Host "==> [2/3] upload code (enter root password)"
scp @opt -r `
    "$src\app" `
    "$src\run.py" `
    "$src\requirements.txt" `
    "$src\.env.example" `
    "$src\deploy.sh" `
    "root@${Ip}:~/memcomp/"

Write-Host "==> [3/3] deploy remotely (enter root password)"
ssh @opt "root@$Ip" "cd ~/memcomp && DASHSCOPE_API_KEY='$key' bash deploy.sh"

Write-Host ""
Write-Host "Done. Self-test in a NEW window:"
Write-Host "  cd D:\Working\memcomp"
Write-Host "  python scripts\smoke_remote.py --url http://${Ip}:8080 --key change-me"
