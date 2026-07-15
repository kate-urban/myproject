@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Сначала запустите setup.bat
    exit /b 1
)

echo Применение правок макета РПД к экспорту...
venv\Scripts\python.exe scripts\docgen\prepare_editable_templates.py --activate
echo.
echo Теперь на вкладке Сверка снова выгрузите DOCX по шаблону.
pause
