@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0SubtitleStudio.exe" goto portable
if not exist ".venv\Scripts\pythonw.exe" (
  echo Source launch requires .venv. Download the Windows portable build for use without Python.
  echo Developer setup is documented in docs\build.md.
  pause
  exit /b 1
)
".venv\Scripts\pythonw.exe" "%~dp0app.py" --open %*
exit /b %errorlevel%

:portable
"%~dp0SubtitleStudio.exe" --open %*
exit /b %errorlevel%
