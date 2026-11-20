@echo off
cd /d "%~dp0"
title Y.A.A.R. - Mini Project
where py >nul 2>nul
if not errorlevel 1 (
    py -3 app.py
    goto end
)
where python >nul 2>nul
if not errorlevel 1 (
    python app.py
    goto end
)
echo Install Python 3 from https://www.python.org/downloads/ and select Add Python to PATH.
:end
pause
