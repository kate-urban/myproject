"""LLM-предложения правок для ошибок сверки (уровень 3: diff + подтверждение)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.services.ai_assistant import html_to_plain, _cheatsheet_excerpt, _format_rule_block
from app.services.validation.rule_guide import get_rule_guide
from app.services.validation.rules import RuleResult, ValidationContext
from app.services.validation_fix import FixChange, SuggestFixResult, suggest_validation_fix

FIX_SYSTEM_PROMPT = """\
Ты — помощник методиста УМУ. Предлагаешь минимальные правки HTML раздела РПД/ФОС для устранения ошибки сверки.

Правила:
- Верни ТОЛЬКО валидный JSON (без markdown).
- Не придумывай эталонные числа и коды — бери их из поля «Ожидалось» / контекста УП.
- В «old» — точная подстрока из фрагмента раздела (как в документе, включая пробелы в ячейках таблицы).
- Меняй только то, что нужно для исправления ошибки; не переписывай весь раздел.
- Если эталон неизвестен или правка неочевидна — верни пустой массив changes и объясни в explanation.
- Для текстовых З/У/В копируй формулировки буквально из «Ожидалось», без перефразирования.

Схема ответа:
{
  "explanation": "кратко: что меняем и почему",
  "changes": [
    {
      "field": "краткий_идентификатор",
      "row_label": "название строки таблицы или контекст",
      "old": "точный фрагмент из документа",
      "new": "исправленное значение"
    }
  ]
}
"""

_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _is_plain_number(value: str | None) -> bool:
    return bool(value and _PLAIN_NUMBER_RE.match(str(value).strip()))


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Пустой ответ LLM")
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Ответ LLM должен быть JSON-объектом")
    return data


def _coerce_changes(raw_changes: Any) -> list[FixChange]:
    if not isinstance(raw_changes, list):
        return []
    result: list[FixChange] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        old = str(item.get("old") or "").strip()
        new = str(item.get("new") or "").strip()
        if not old or not new or old == new:
            continue
        result.append(
            FixChange(
                field=str(item.get("field") or "value")[:80],
                old=old,
                new=new,
                row_label=(str(item.get("row_label")).strip()[:120] if item.get("row_label") else None),
            )
        )
    return result


def _plain_html(html: str) -> str:
    return html_to_plain(html, max_len=50_000)


def _change_present_in_html(html: str, change: FixChange) -> bool:
    if change.old in html:
        return True
    plain = _plain_html(html)
    return change.old in plain


def _verify_changes(changes: list[FixChange], rule_result: RuleResult) -> tuple[list[FixChange], bool]:
    """Оставляет только изменения, где old есть в документе; apply_safe если new совпадает с эталоном."""
    expected = (rule_result.expected or "").strip()
    actual = (rule_result.actual or "").strip()
    verified: list[FixChange] = []
    safe_flags: list[bool] = []

    for change in changes:
        verified.append(change)
        safe = False
        if expected and change.new.strip() == expected:
            safe = True
        elif actual and change.old.strip() == actual and expected and change.new.strip() == expected:
            safe = True
        elif _is_plain_number(expected) and _is_plain_number(change.new) and change.new.strip() == expected:
            safe = True
        safe_flags.append(safe)

    apply_safe = bool(verified) and all(safe_flags)
    return verified, apply_safe


def apply_changes_to_html(section_html: str, changes: list[FixChange]) -> tuple[str | None, list[FixChange]]:
    """Применить правки к HTML; каждая old-подстрока заменяется один раз."""
    if not section_html or not changes:
        return None, []

    result = section_html
    applied: list[FixChange] = []
    for change in changes:
        if change.old not in result:
            return None, applied
        result = result.replace(change.old, change.new, 1)
        applied.append(change)
    return result, applied


def _build_fix_user_prompt(
    *,
    rule_id: str,
    kind: str,
    discipline_code: str | None,
    rule_result: RuleResult,
    section_title: str | None,
    section_html: str,
    ctx: ValidationContext,
) -> str:
    guide = get_rule_guide(kind, rule_id) or {}
    blocks = [
        _format_rule_block(
            rule_id=rule_id,
            kind=kind,
            rule_name=rule_result.name,
            message=rule_result.message,
            expected=rule_result.expected,
            actual=rule_result.actual,
        ),
    ]
    if discipline_code:
        blocks.append(f"Дисциплина: {discipline_code}")
    blocks.append(f"Шифр из УП: {ctx.discipline.code}")
    if ctx.discipline.name:
        blocks.append(f"Название из УП: {ctx.discipline.name}")
    if ctx.discipline.credits is not None:
        blocks.append(f"З.е. из УП: {ctx.discipline.credits}")
    if ctx.discipline.hours_total is not None:
        blocks.append(f"Часы из УП: {ctx.discipline.hours_total}")
    if guide.get("where"):
        blocks.append(f"Где править: {guide['where']}")
    if guide.get("fix"):
        blocks.append(f"Рекомендация: {guide['fix']}")
    if section_title:
        blocks.append(f"Раздел: {section_title}")
    plain = html_to_plain(section_html, 6000)
    if plain:
        blocks.append(f"Фрагмент раздела (plain text):\n{plain}")
    blocks.append("Фрагмент методички:\n" + _cheatsheet_excerpt(4000))
    blocks.append(
        "Верни JSON с минимальными правками (changes), чтобы устранить ошибку сверки."
    )
    return "\n\n---\n\n".join(blocks)


async def ask_llm_fix(user_prompt: str) -> dict[str, Any]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI_API_KEY not configured")

    base = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")
    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "60"))

    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": FIX_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
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
        content = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected LLM response shape") from exc

    return _parse_llm_json(content)


async def suggest_llm_validation_fix(
    rule_id: str,
    section_html: str,
    ctx: ValidationContext,
    rule_result: RuleResult,
    *,
    kind: str = "rpd",
    section_title: str | None = None,
    discipline_code: str | None = None,
) -> SuggestFixResult:
    """Сформировать правку через LLM с diff и проверкой эталона."""
    rule_id = (rule_id or "").upper()
    if rule_result.passed or rule_result.skipped:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=False,
            apply_safe=False,
            message="Правило уже выполнено или пропущено",
        )

    user_prompt = _build_fix_user_prompt(
        rule_id=rule_id,
        kind=kind,
        discipline_code=discipline_code,
        rule_result=rule_result,
        section_title=section_title,
        section_html=section_html,
        ctx=ctx,
    )

    try:
        payload = await ask_llm_fix(user_prompt)
    except Exception as exc:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=False,
            apply_safe=False,
            message=f"LLM не смог предложить правку: {exc}",
        )

    explanation = str(payload.get("explanation") or "").strip()
    raw_changes = _coerce_changes(payload.get("changes"))

    if not raw_changes:
        msg = explanation or "ИИ не предложил конкретных правок для этого раздела"
        return SuggestFixResult(
            rule_id=rule_id,
            supported=True,
            apply_safe=False,
            message=msg,
        )

    present = [ch for ch in raw_changes if _change_present_in_html(section_html, ch)]
    if not present:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=True,
            apply_safe=False,
            message=(
                (explanation + " — " if explanation else "")
                + "Предложенные фрагменты не найдены в HTML раздела; откройте нужный раздел и повторите"
            ),
        )

    verified, apply_safe = _verify_changes(present, rule_result)
    patched_html, applied = apply_changes_to_html(section_html, verified)
    if not patched_html or not applied:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=True,
            apply_safe=False,
            message="Не удалось применить предложенные правки к HTML",
        )

    prefix = f"{explanation} — " if explanation else ""
    return SuggestFixResult(
        rule_id=rule_id,
        supported=True,
        apply_safe=apply_safe,
        patched_html=patched_html,
        changes=applied,
        message=prefix + f"ИИ предложил изменений: {len(applied)}"
        + (" (эталон совпадает)" if apply_safe else " — проверьте diff перед применением"),
        source="llm",
        explanation=explanation or None,
    )


async def suggest_validation_fix_auto(
    rule_id: str,
    section_html: str,
    ctx: ValidationContext,
    rule_result: RuleResult,
    *,
    prefer_llm: bool = False,
    kind: str = "rpd",
    section_title: str | None = None,
    discipline_code: str | None = None,
) -> tuple[SuggestFixResult, str]:
    """Детерминированная правка, при необходимости — LLM. Возвращает (result, source)."""
    rule_id = (rule_id or "").upper()
    if not prefer_llm:
        deterministic = suggest_validation_fix(rule_id, section_html, ctx, rule_result)
        if deterministic.patched_html and deterministic.changes:
            return deterministic, "deterministic"

    llm_result = await suggest_llm_validation_fix(
        rule_id,
        section_html,
        ctx,
        rule_result,
        kind=kind,
        section_title=section_title,
        discipline_code=discipline_code,
    )
    return llm_result, "llm"
