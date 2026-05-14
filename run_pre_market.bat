@echo off
setlocal

cd /d C:\trading\personal_trading_os

if not exist logs mkdir logs
if not exist output mkdir output
if not exist cache mkdir cache

chcp 65001 >nul
set PYTHONUTF8=1

echo [%date% %time%] Starting pre-market run >> logs\pre_market.log

if not exist .venv\Scripts\python.exe (
    echo [%date% %time%] ERROR: .venv\Scripts\python.exe not found >> logs\pre_market.log
    echo [%date% %time%] Please create venv with: py -3.12 -m venv .venv >> logs\pre_market.log
    exit /b 1
)

if not exist src\main.py (
    echo [%date% %time%] ERROR: src\main.py not found >> logs\pre_market.log
    exit /b 1
)

.venv\Scripts\python.exe src\main.py --session pre_market >> logs\pre_market.log 2>&1

set EXIT_CODE=%ERRORLEVEL%

echo [%date% %time%] Finished pre-market run with exit code %EXIT_CODE% >> logs\pre_market.log

exit /b %EXIT_CODE%
