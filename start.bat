@echo off
title OpenShort LiveClipper
echo ============================================================
echo   Starting OpenShort LiveClipper for PC...
echo   Autonomous Live Stream ^& Game Highlight Clipper
echo ============================================================
echo.

python main.py

if %errorlevel% neq 0 (
    echo.
    echo An error occurred while launching. Press any key to exit.
    pause >nul
)
