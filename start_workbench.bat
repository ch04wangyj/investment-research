@echo off
setlocal
cd /d "%~dp0"

set API_PORT=8000
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /I "%%A"=="API_PORT" set API_PORT=%%B
    )
)

if not exist "frontend\.env.local" (
    > "frontend\.env.local" echo NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:%API_PORT%
)

start "Investment Research API" cmd /k python scripts\run_api.py
start "Investment Research Frontend" cmd /k "cd frontend && npm run dev"
echo API: http://127.0.0.1:%API_PORT%/api/health
echo UI:  http://localhost:3000
