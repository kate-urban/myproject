"""Пояснения к кодам привязки РПД/ФОС к учебному плану."""

from __future__ import annotations

LINK_REASON_MESSAGES: dict[str, str] = {
    "study_plan_not_found": "Учебный план не найден. Обновите страницу и выберите план снова.",
    "discipline_code_not_found": (
        "Не удалось определить шифр дисциплины из файла. "
        "Имя файла должно содержать шифр дисциплины, например Б1_О_01_07_…"
    ),
    "discipline_not_in_plan": (
        "Дисциплина {discipline_code} есть в файле, но отсутствует в выбранном учебном плане. "
        "Проверьте: 1) выбран ли нужный план слева; 2) файл от этой же программы (направление/профиль)."
    ),
}


def format_link_reason(reason: str | None, *, discipline_code: str | None = None) -> str | None:
    if not reason:
        return None
    template = LINK_REASON_MESSAGES.get(reason)
    if not template:
        return reason
    if "{discipline_code}" in template:
        return template.format(discipline_code=discipline_code or "—")
    return template
