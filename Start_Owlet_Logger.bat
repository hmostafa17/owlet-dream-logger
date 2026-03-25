@echo off
REM Owlet Dream Logger Launcher
REM This batch file starts the Owlet monitoring application

echo.
echo ========================================
echo   Owlet Dream Logger
echo ========================================
echo.
echo Starting server...
echo Open your browser to: http://localhost:8000
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM Change to the script directory
cd /d "%~dp0"

REM Start the application
python main.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Application failed to start
    echo ========================================
    pause
)
