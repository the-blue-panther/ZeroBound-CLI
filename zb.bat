@echo off
setlocal

cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt -q

echo Playwright installation (if needed)...
playwright install chromium --with-deps

echo Starting ZeroBound CLI...
python cli.py

pause
