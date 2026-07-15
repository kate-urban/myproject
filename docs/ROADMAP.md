# Roadmap: Syllabus / валидация УП ↔ РПД ↔ ФОС

## Статус этапов

| Шаг | Название | Статус | Критерий готовности |
|-----|----------|--------|---------------------|
| **0** | Field map + golden pairs | **Закрыт** | `docs/golden_pairs.yaml` → `status: reviewed`, чек-лист выполнен |
| **1** | Импорт учебных планов | **Закрыт** | Excel + XML UpVo → PostgreSQL; smoke-тесты всех plx из golden |
| **2** | Валидация РПД ↔ УП (R001–R029) | **Закрыт** | Правила R015–R029; golden + unit-тесты; XML assessments + hours_control |
| **3** | Валидация ФОС ↔ РПД/УП | **Закрыт** | F001–F014; golden-пары; API `validate-fos` + batch; режим fos_only |
| 4+ | UI, batch-отчёты, PDF/OCR | **В работе** | UI `/validation`, `/workspace`, блокировки, structured snapshot |

---

## Шаг 2 — расширение (2026-07-06)

### Новые правила R015–R029

| ID | Назначение |
|----|------------|
| R015 | Exact match З/У/В п.2 → 3.1 |
| R016 | Обязательные строки 3.5, часы контроля, минимумы КР/КП |
| R017 | КР/КП в 3.1 только +/- |
| R018 | Нумерация X.Y, сумма вопросов vs бюджет СР в 3.5 |
| R019 | Матрица 3.6 |
| R024 | ПК всегда в группах |
| R025 | лек+практ+лаб = контакт 1.3 |
| R026 | лек+практ+лаб по темам = УП/1.3 |
| R027 | сумма строк 3.5 = итог |
| R028 | Формы аттестации 3.1 vs УП по семестрам |
| R029 | Жирные заголовки тем (warning) |

- `CORE_RULE_IDS` — R001–R014, R020–R023 (golden без новых TZ-правил)
- `DEFAULT_RULE_IDS` — все правила включая R015–R029
- После загрузки РПД нужен re-upload DOCX или `refresh-extract`, чтобы обновился `rpd_extract_json`

### Импорт УП

- `PlanDisciplineAssessment` — формы аттестации (exam/zachet/kp/kr…) + семестр из XML/Excel
- `hours_control` — часы контрольных работ (код вида работ 6), отдельно от экзаменов/зачётов
- `selectinload(PlanDiscipline.assessments)` во всех validate-запросах

### Structured RPD

- `ProgramStructuredRpd.payload_json` — снимок extract (passport, topics, 3.5, 3.6, assessments)
- Синхронизация при загрузке РПД: `structured_rpd_sync.sync_structured_rpd`

### Осознанные ограничения

| Правило | Поведение |
|---------|-----------|
| R008, R009 | Skip без `EXPECTED_DIRECTOR` / `EXPECTED_DISCIPLINE_HEAD` в `.env` |
| R012, R029 | Warning (не влияют на `passed`) |
| R015 | Strict exact match — golden B1_O_01_07 может падать при перефразировании |
| LLM / OCR / PDF | Не реализовано — этап 7+ |

---

## Шаг 4 — в работе (2026-07-06)

### Сделано

- **UI сверки:** http://localhost:8000/validation — импорт, загрузка, сверка, отчёты, inline-редактор
- **Блокировки:** `edit_lock.js`, heartbeat, badge «Занято …» на validation, acquire при открытии редактора
- **Редактор:** `/editor?doc=<uuid>` — открытие по ссылке из workspace + lock
- **API:** `program_id`, `lock_holder` в списке дисциплин; `program_id` в `ProgramLinkOut`

### Сделано (2026-07-06, экспорт)

- **Экспорт после сверки:** `GET .../disciplines/{id}/export/?kind=rpd|fos`
- **Пакет ZIP:** `GET .../export-passed/?kind=rpd|fos` — все документы с `passed=true`
- **Сводка:** `GET .../export-summary/`
- **Финализация:** `export_finalize.py` — подписи (`{{DIRECTOR_LINE}}`, …) и переутверждение
- **Журнал:** таблица `export_jobs`
- **UI:** кнопки «⬇ РПД (N)» / «⬇ ФОС (N)» и ⬇ в строке дисциплины на `/validation`
- **R030** — лист переутверждения заполнен (warning)

Настройки `.env`: `EXPORT_REQUIRE_VALIDATION`, `EXPORT_FILL_SIGNATURES`, `EXPECTED_DIRECTOR`, …

### Дальше

- PDF/OCR (этап 7+)
- F015+ после согласования с методистом
- Полные relational-таблицы structured RPD (сейчас JSON-snapshot)
- LLM для fuzzy-сопоставления З/У/В (R015 soft mode)

### Команды

```cmd
set PYTHONPATH=.
venv\Scripts\pytest.exe tests/ -q
venv\Scripts\python.exe scripts\validate_golden_pairs.py
venv\Scripts\python.exe scripts\validate_golden_fos.py
```

---

*Обновлено: 2026-07-06*
