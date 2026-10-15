@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 먼저 README.md의 로컬 실행 절차로 가상환경과 의존성을 설치하세요.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" check_env.py
if errorlevel 1 (
  pause
  exit /b 1
)
".venv\Scripts\python.exe" server.py --open-browser
if errorlevel 1 pause
