@echo off
title shorts-pipeline UI
echo Iniciando o servidor da interface web (via WSL)...
start "" cmd /c "timeout /t 3 >nul && start http://localhost:8765"
wsl -e bash -lc "cd /mnt/d/shorts-pipeline && source ~/.venvs/shorts-pipeline/bin/activate && python -m shorts serve --no-open"
pause
