# BONE-MAP Local All-in-One Launcher (Windows PowerShell)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

Write-Host "Starting BONE-MAP FastAPI backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$BackendCmd = "cd `"$BackendDir`"; .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCmd

Write-Host "Starting BONE-MAP Next.js frontend on http://localhost:3000 ..." -ForegroundColor Cyan
$FrontendCmd = "cd `"$FrontendDir`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendCmd

Write-Host "BONE-MAP launched! Open http://localhost:3000 in your browser." -ForegroundColor Green
