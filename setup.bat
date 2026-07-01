@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Document Processor: установка ===

where python >nul 2>&1
if errorlevel 1 (
    echo Ошибка: Python не найден. Установите Python 3.12 или 3.13 с python.org
    exit /b 1
)

python --version

if not exist "venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    python -m venv venv
    if errorlevel 1 (
        echo Ошибка создания venv
        exit /b 1
    )
)

echo Устанавливаю зависимости...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Ошибка установки. Если у вас Python 3.14, попробуйте Python 3.12 или 3.13.
    exit /b 1
)

echo.
echo Проверка подключения к БД...
venv\Scripts\python.exe test_sqlalchemy.py
if errorlevel 1 (
    echo.
    echo БД недоступна. Проверьте PostgreSQL и файл .env
    exit /b 1
)

echo.
echo Готово. Запуск сервера:
echo   run.bat
echo или:
echo   venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
