@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title E.L.B.E.R.R. v0.9 - Cognitive Model

set "PYEXE="
python --version >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PYEXE (
  echo Python not found. Run START_HERE.bat first.
  pause
  exit /b 1
)

"%PYEXE%" setup_cognitive.py
if errorlevel 1 (
  echo.
  echo Failed to install the cognitive model. Copy the error shown above to investigate.
  pause
  exit /b 1
)

echo.
echo High-intelligence cognitive model enabled.
echo Next: run SELF_TEST.bat, then chat_with_creator.bat.
pause
