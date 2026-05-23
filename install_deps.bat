@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Install failed.
    pause
    exit /b 1
)
echo Done. Restart Houdini Render Manager.
pause
