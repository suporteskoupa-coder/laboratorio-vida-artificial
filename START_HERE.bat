@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title E.L.B.E.R.R. v0.9 DIGITAL ECOLOGY - Setup

echo ============================================================
echo              E.L.B.E.R.R. LAB v0.9 DIGITAL ECOLOGY
echo        No Podman / No WSL / No Hyper-V / No Docker
echo ============================================================
echo.

set "PYEXE="
python --version >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"

if not defined PYEXE (
    echo Python not found.
    where winget >nul 2>nul
    if errorlevel 1 (
        echo winget is not available. Install Python 3.13 manually and rerun this file.
        pause
        exit /b 1
    )
    echo Installing Python 3.13 with winget...
    winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
    if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
)
if not defined PYEXE (
    echo Python installed but was not found in this terminal. Close this window and run START_HERE.bat again.
    pause
    exit /b 1
)

set "OLLAMA="
where ollama >nul 2>nul && set "OLLAMA=ollama"
if not defined OLLAMA if exist "%LocalAppData%\Programs\Ollama\ollama.exe" set "OLLAMA=%LocalAppData%\Programs\Ollama\ollama.exe"
if not defined OLLAMA (
    echo Ollama not found.
    where winget >nul 2>nul
    if errorlevel 1 (
        echo winget is not available. Install Ollama manually and rerun this file.
        pause
        exit /b 1
    )
    echo Installing Ollama with winget...
    winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    if exist "%LocalAppData%\Programs\Ollama\ollama.exe" set "OLLAMA=%LocalAppData%\Programs\Ollama\ollama.exe"
)
if not defined OLLAMA (
    echo Ollama installed but was not found in this terminal. Close this window and run START_HERE.bat again.
    pause
    exit /b 1
)

echo.
echo Installing local Wasmtime runtime and selecting the Ollama model...
"%PYEXE%" setup_local.py
if errorlevel 1 (
    echo.
    echo Setup failed. Copy the complete error and send it to ChatGPT.
    pause
    exit /b 1
)

echo.
echo Running containment/self-test...
"%PYEXE%" self_test.py
if errorlevel 1 (
    echo.
    echo Self-test failed. Do not run generations yet.
    echo Copy the complete error and send it to ChatGPT.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Setup and self-test completed successfully.
echo Next: run_3_generations.bat, chat_with_creator.bat, run_life_10_cycles.bat, or LIVE_MODE.bat
echo ============================================================
pause
