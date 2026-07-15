"""ИИ-помощник методиста: объяснение ошибок сверки (LLM опционально, иначе шаблон)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.config import ai_assistant_enabled, ai_llm_configured
from app.services.validation.rule_guide import get_rule_guide

_BASE_DIR = Path(__file__).resolve().parents[2]
_CHEATSHEET_CACHE: str | None = None

SYSTEM_PROMPT = """\
Ты — помощник методиста УМУ. Объясняешь ошибки автоматической сверки РПД/ФОС с учебным планом.
Правила:
- Не придумывай числа и коды — опирайся только на контекст (ожидалось/фактически, фрагмент раздела).
- Не заменяешь официальную сверку: это подсказка для редактора.
- Отвечай по-русски, кратко (3–6 абзацев), структурированно: «суть», «где править», «шаги».
- Если в документе «Не предусмотрены учебным планом» в таблице 1.3 — правило по часам может быть пропущено; \
текст в § 3.3 на это не влияет.
"""


def _cheatsheet_excerpt(max_chars: int = 7000) -> str:
    global _CHEATSHEET_CACHE
    if _CHEATSHEET_CACHE is None:
        path = _BASE_DIR / "docs" / "VALIDATION_CHEATSHEET.md"
        _CHEATSHEET_CACHE = path.read_text(encoding="utf-8") if path.is_file() else ""
    return _CHEATSHEET_CACHE[:max_chars]


def html_to_plain(text: str | None, max_len: int = 1800) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        plain = BeautifulSoup(text, "lxml").get_text("\n", strip=True)
    else:
        plain = text
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain[:max_len]


def _format_rule_block(
    *,
    rule_id: str,
    kind: str,
    rule_name: str | None,
    message: str | None,
    expected: str | None,
    actual: str | None,
) -> str:
    guide = get_rule_guide(kind, rule_id) or {}
    lines = [
        f"Правило: {rule_id}" + (f" — {rule_name}" if rule_name else ""),
        f"Сообщение сверки: {message or '—'}",
    ]
    if expected:
        lines.append(f"Ожидалось (УП/эталон): {expected}")
    if actual:
        lines.append(f"В документе: {actual}")
    if guide.get("where"):
        lines.append(f"Где искать: {guide['where']}")
    if guide.get("fix"):
        lines.append(f"Что сделать: {guide['fix']}")
    return "\n".join(lines)


def build_fallback_answer(
    *,
    question: str,
    rule_id: str | None,
    kind: str,
    discipline_code: str | None,
    rule_name: str | None,
    message: str | None,
    expected: str | None,
    actual: str | None,
    section_title: str | None,
    section_snippet: str | None,
) -> str:
    parts: list[str] = []
    if discipline_code:
        parts.append(f"**Дисциплина:** {discipline_code}")

    if rule_id:
        parts.append("**Ошибка сверки**\n" + _format_rule_block(
            rule_id=rule_id,
            kind=kind,
            rule_name=rule_name,
            message=message,
            expected=expected,
            actual=actual,
        ))

        if rule_id == "R025" and expected and actual:
            parts.append(
                "**Суть:** правило R025 сравнивает сумму лекций + практик + лабораторных "
                "со строкой «Контактная работа» в **таблице 1.3**. "
                "Фраза «Не предусмотрены учебным планом» в тексте § 3.3 не отменяет проверку — "
                "смотрите именно таблицу 1.3 и колонку очной формы."
            )
        elif rule_id == "R022":
            parts.append(
                "**Суть:** R022 сверяет контактные часы в таблице 1.3 с учебным планом. "
                "Ошибка часто возникает, если взята не та колонка (заочная/очная) или сумма тем из § 3."
            )
        elif rule_id == "R018":
            parts.append(
                "**Суть:** R018 проверяет нумерацию и часы вопросов самостоятельной работы (X.Y) "
                "и их сумму относительно итога таблицы 3.5."
            )
        else:
            parts.append(
                "**Суть:** автоматическая сверка нашла расхождение между учебным планом и документом. "
                "Сверка не «понимает» пояснительный текст — только извлечённые из таблиц числа и коды."
            )

        guide = get_rule_guide(kind, rule_id)
        if guide:
            parts.append(f"**Где править:** {guide.get('where', '—')}")
            parts.append(f"**Рекомендация:** {guide.get('fix', '—')}")
    else:
        parts.append(
            "Выберите ошибку в списке сверху или укажите код правила (R025, F007 …), "
            "чтобы получить точное объяснение."
        )

    if section_title or section_snippet:
        snippet = html_to_plain(section_snippet, 600)
        parts.append(
            f"**Текущий раздел:** {section_title or '—'}"
            + (f"\n\nФрагмент:\n{snippet}" if snippet else "")
        )

    q = (question or "").strip().lower()
    if q and q not in ("объясни", "объяснить", "помоги", "help"):
        parts.append(
            f"_Вопрос:_ {question.strip()}\n\n"
            "Ответ сформирован по методичке и данным сверки. "
            "Для развёрнутого ответа на произвольный вопрос настройте `AI_API_KEY` в `.env`."
        )
    elif not ai_llm_configured():
        parts.append(
            "_Подсказка:_ для ответов на произвольные вопросы добавьте `AI_API_KEY` "
            "(OpenAI или совместимый API) в `.env`."
        )

    return "\n\n".join(parts)


def _build_user_prompt(payload: dict[str, Any]) -> str:
    blocks = [
        _format_rule_block(
            rule_id=payload.get("rule_id") or "—",
            kind=payload.get("kind") or "rpd",
            rule_name=payload.get("rule_name"),
            message=payload.get("message"),
            expected=payload.get("expected"),
            actual=payload.get("actual"),
        ),
    ]
    if payload.get("discipline_code"):
        blocks.append(f"Дисциплина: {payload['discipline_code']}")
    if payload.get("section_title"):
        blocks.append(f"Раздел документа: {payload['section_title']}")
    snippet = html_to_plain(payload.get("section_snippet"), 1200)
    if snippet:
        blocks.append(f"Фрагмент раздела:\n{snippet}")
    blocks.append("Фрагмент методички:\n" + _cheatsheet_excerpt(5000))
    blocks.append(f"Вопрос методиста:\n{payload.get('question') or 'Объясни эту ошибку и что исправить.'}")
    return "\n\n---\n\n".join(blocks)


async def ask_llm(payload: dict[str, Any]) -> str:
    api_key = os.getenv("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI_API_KEY not configured")

    base = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")
    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(payload)},
        ],
        "temperature": 0.2,
        "max_tokens": 900,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        response.raise_for_status()
        data = response.json()

    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected LLM response shape") from exc


async def assist_validation(
    *,
    question: str,
    rule_id: str | None,
    kind: str,
    discipline_code: str | None,
    rule_name: str | None,
    message: str | None,
    expected: str | None,
    actual: str | None,
    section_title: str | None,
    section_snippet: str | None,
) -> tuple[str, str]:
    """Returns (answer, source) where source is 'llm' or 'local'."""
    payload = {
        "question": question,
        "rule_id": rule_id,
        "kind": kind,
        "discipline_code": discipline_code,
        "rule_name": rule_name,
        "message": message,
        "expected": expected,
        "actual": actual,
        "section_title": section_title,
        "section_snippet": section_snippet,
    }

    if ai_llm_configured():
        try:
            return await ask_llm(payload), "llm"
        except Exception:
            pass

    return build_fallback_answer(
        question=question,
        rule_id=rule_id,
        kind=kind,
        discipline_code=discipline_code,
        rule_name=rule_name,
        message=message,
        expected=expected,
        actual=actual,
        section_title=section_title,
        section_snippet=section_snippet,
    ), "local"
