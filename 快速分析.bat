@echo off
cd /d "%~dp0"

if "%1"=="" (
    echo Usage: 快速分析.bat TICKER
    echo Example: 快速分析.bat AAPL
    echo         快速分析.bat 600519
    pause
    exit /b
)

python scripts\run_analysis.py %1 --save-db
pause
