# Document Processor

Загрузка PDF/DOCX → редактирование разделов в браузере → экспорт в Word по шаблону.

## Требования

- **Python 3.12 или 3.13** (рекомендуется; Python 3.14 может не поддерживаться всеми пакетами)
- **PostgreSQL** с базой `docdb`

## Быстрый старт (Windows)

```cmd
cd D:\Syllabus\myproject
setup.bat
run.bat
```

Откройте http://localhost:8000/

## Ручная установка

### 1. Файл `.env`

```env
DATABASE_URL=postgresql+asyncpg://postgres:ПАРОЛЬ@127.0.0.1:5432/docdb
TEMPLATES_DIR=./templates
EXPORTS_DIR=./exports
```

### 2. Виртуальное окружение (без Activate.ps1)

PowerShell может блокировать `Activate.ps1`. Используйте **cmd** или вызывайте Python напрямую:

```cmd
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe test_sqlalchemy.py
venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Если нужен Activate.ps1 в PowerShell

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Или используйте **cmd**:

```cmd
venv\Scripts\activate.bat
```

## Создание базы данных

SQL выполняется **в PostgreSQL**, не в PowerShell:

```cmd
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE docdb;"
```

Подробнее: [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md)
