@echo off
echo ============================================
echo  Coach Hiring Tool - First-Time Setup
echo ============================================
echo.

REM Try multiple Python launchers
set PYTHON_CMD=

for %%P in (python python3 py) do (
    %%P --version >nul 2>&1
    if !errorlevel! == 0 (
        set PYTHON_CMD=%%P
        goto :found_python
    )
)

echo ERROR: Python is not installed.
echo.
echo Please install Python 3.10 or higher:
echo   1. Go to: https://www.python.org/downloads/
echo   2. Click "Download Python 3.x.x"
echo   3. Run the installer
echo   4. IMPORTANT: Check the box "Add python.exe to PATH"
echo   5. Click "Install Now"
echo   6. Re-run this setup.bat after installation
echo.
pause
exit /b 1

:found_python
echo Python found: %PYTHON_CMD%
echo.

echo [1/3] Creating virtual environment...
%PYTHON_CMD% -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Could not create virtual environment.
    pause
    exit /b 1
)

echo [2/3] Installing dependencies (this may take 1-2 minutes)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Package installation failed.
    echo Try running this file as Administrator.
    pause
    exit /b 1
)

echo.
echo [3/3] Setup complete!
echo.
echo ============================================
echo  DONE! Now double-click run.bat to start.
echo ============================================
pause
