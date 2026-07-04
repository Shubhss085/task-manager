@echo off
title Task Manager
cd /d "%~dp0"
echo.
echo   =================================
echo        Task Manager App
echo   =================================
echo.
echo   Starting server...
echo   Open http://127.0.0.1:5000 in your browser
echo   Press Ctrl+C to stop
echo.
python backend\app.py
pause
