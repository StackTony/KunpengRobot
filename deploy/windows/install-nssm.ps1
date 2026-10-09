# 鲲鹏运维平台 - Windows 裸机安装脚本 (NSSM 注册系统服务)
# 前置: 已安装 Python 3.11+ / PostgreSQL / Redis / NSSM (https://nssm.cc)
# 用法: 管理员 PowerShell 执行  .\install-nssm.ps1
param(
    [string]$InstallDir = "C:\kunpeng",
    [string]$BackendDir = (Resolve-Path "$PSScriptRoot\..\..\backend").Path
)

$ErrorActionPreference = "Stop"

Write-Host "==> 安装目录: $InstallDir"
New-Item -ItemType Directory -Force -Path "$InstallDir\data" | Out-Null

if (-not (Test-Path "$InstallDir\venv")) {
    Write-Host "==> 创建虚拟环境"
    python -m venv "$InstallDir\venv"
}

Write-Host "==> 安装 Python 依赖"
& "$InstallDir\venv\Scripts\pip.exe" install -r "$BackendDir\requirements.txt"

if (-not (Test-Path "$InstallDir\.env")) {
    Write-Host "==> 写入环境配置"
    $secret = -join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })
    @"
DATABASE_URL=postgresql+asyncpg://kunpeng:kunpeng@127.0.0.1:5432/kunpeng
REDIS_URL=redis://127.0.0.1:6379/0
SECRET_KEY=$secret
DATA_DIR=$($InstallDir.Replace('\','/'))/data
"@ | Out-File -Encoding utf8 "$InstallDir\.env"
}

Write-Host "==> 注册 NSSM 服务 (kunpeng-api / kunpeng-worker)"
$venvPython = "$InstallDir\venv\Scripts\python.exe"
$venvUvicorn = "$InstallDir\venv\Scripts\uvicorn.exe"

nssm install kunpeng-api $venvUvicorn "app.main:app --host 127.0.0.1 --port 8000"
nssm set kunpeng-api AppDirectory $BackendDir
nssm set kunpeng-api AppEnvironmentExtraExtra ""
# 写入环境变量
Get-Content "$InstallDir\.env" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { nssm set kunpeng-api AppEnvironmentExtra "$($Matches[1])=$($Matches[2])" }
}
nssm set kunpeng-api AppStdout "$InstallDir\logs\api.log"
nssm set kunpeng-api AppStderr "$InstallDir\logs\api-error.log"
nssm start kunpeng-api

nssm install kunpeng-worker $venvPython "-m app.worker"
nssm set kunpeng-worker AppDirectory $BackendDir
Get-Content "$InstallDir\.env" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { nssm set kunpeng-worker AppEnvironmentExtra "$($Matches[1])=$($Matches[2])" }
}
nssm set kunpeng-worker AppStdout "$InstallDir\logs\worker.log"
nssm set kunpeng-worker AppStderr "$InstallDir\logs\worker-error.log"
nssm start kunpeng-worker

Write-Host "==> 完成: API http://127.0.0.1:8000"
Write-Host "    前端: 构建后由 Nginx/IIS 托管 (配置参考 deploy/nginx/nginx.conf)"
Write-Host "    服务管理: nssm status kunpeng-api / nssm restart kunpeng-worker"
