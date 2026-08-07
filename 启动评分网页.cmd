@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

start "515450 scoring dashboard" /min cmd /c "cd /d ""%~dp0web"" && npm run dev"
timeout /t 4 /nobreak >nul

python -m dividend_etf_score.sync --site-url http://localhost:3000 --source auto --once
start "" http://localhost:3000

endlocal
