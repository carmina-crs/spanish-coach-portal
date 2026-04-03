@echo off
echo ============================================
echo  Coach Hiring Tool - Starting...
echo ============================================
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Running with system Python.
    echo If you get import errors, run setup.bat first.
)

echo Opening Coach Hiring Tool in your browser...
echo (Press Ctrl+C in this window to stop the app)
echo.

python -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false

pause
