@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Сначала запустите setup.bat
    exit /b 1
)

@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Сначала запустите setup.bat
    exit /b 1
)

echo Останавливаем предыдущий процесс на порту 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo Сервер: http://localhost:8000
echo Главная (вход): http://localhost:8000/
echo Редактор: http://localhost:8000/editor
echo Сверка УП: http://localhost:8000/validation
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
