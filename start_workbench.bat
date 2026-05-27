@echo off
cd /d "%~dp0"
start "Investment Research API" cmd /k python scripts\run_api.py
start "Investment Research Frontend" cmd /k "cd frontend && npm run dev"
echo API: http://127.0.0.1:8000/api/health
echo UI:  http://localhost:3000
