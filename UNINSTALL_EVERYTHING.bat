@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title E.L.B.E.R.R. v0.9 - Cleanup

echo ============================================================
echo            E.L.B.E.R.R. v0.9 DIGITAL ECOLOGY CLEANUP
echo ============================================================
echo.
echo Removes project-local data and Qwen models used here.
echo Python/Ollama are only uninstalled if you explicitly choose it.
echo.
set /p CONFIRM=Type DELETE ELLBERR to continue: 
if /I not "%CONFIRM%"=="DELETE ELLBERR" (
  echo Cancelled.
  pause
  exit /b 0
)
set "OLLAMA="
where ollama >nul 2>nul && set "OLLAMA=ollama"
if not defined OLLAMA if exist "%LocalAppData%\Programs\Ollama\ollama.exe" set "OLLAMA=%LocalAppData%\Programs\Ollama\ollama.exe"
if defined OLLAMA (
  "%OLLAMA%" rm qwen3:14b >nul 2>nul
  "%OLLAMA%" rm qwen3:8b >nul 2>nul
  "%OLLAMA%" rm qwen3:4b >nul 2>nul
)
if exist "%~dp0_deps" rmdir /s /q "%~dp0_deps"
if exist "%~dp0state" rmdir /s /q "%~dp0state"
if exist "%~dp0generations" rmdir /s /q "%~dp0generations"
echo.
set /p APPS=Also uninstall Ollama and Python 3.13 with winget? [Y/N]: 
if /I "%APPS%"=="Y" (
  where winget >nul 2>nul
  if not errorlevel 1 (
    winget uninstall --id Ollama.Ollama -e
    winget uninstall --id Python.Python.3.13 -e
  )
)
echo.
set /p FOLDER=Delete this entire E.L.B.E.R.R. folder too? [Y/N]: 
if /I "%FOLDER%"=="Y" (
  set "TARGET=%~dp0"
  start "" /min cmd /c "timeout /t 2 /nobreak >nul & cd /d \"%TEMP%\" & rmdir /s /q \"%TARGET%\""
  exit /b 0
)
echo Cleanup complete.
pause
