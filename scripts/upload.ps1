# Upload code to Alibaba Cloud server (Windows PowerShell 5.1 compatible, ASCII only)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\upload.ps1 -Ip YOUR_PUBLIC_IP
param(
    [Parameter(Mandatory = $true)][string]$Ip
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] ssh not found. Enable Windows OpenSSH Client."
    exit 1
}

$src = (Resolve-Path "$PSScriptRoot\..").Path
$opt = @("-o", "StrictHostKeyChecking=accept-new")

Write-Host "==> [1/2] create ~/memcomp on server (enter root password)"
ssh @opt "root@$Ip" "mkdir -p ~/memcomp"

Write-Host "==> [2/2] upload code (enter root password)"
scp @opt -r `
    "$src\app" `
    "$src\run.py" `
    "$src\requirements.txt" `
    "$src\.env.example" `
    "$src\deploy.sh" `
    "root@${Ip}:~/memcomp/"

Write-Host ""
Write-Host "Upload done. Next:"
Write-Host "  ssh root@$Ip"
Write-Host "  cd ~/memcomp ; DASHSCOPE_API_KEY=sk-YOURKEY bash deploy.sh"
