"""Тесты детектора качества PDF."""

from __future__ import annotations

from app.services.pdf_quality import assess_pdf_text_quality


def test_pdf_quality_empty() -> None:
    result = assess_pdf_text_quality("")
    assert result["quality"] == "empty"
    assert result["needs_manual_passport"] is True


def test_pdf_quality_poor_spaced_letters() -> None:
    text = "Р А Б О Ч А Я   П Р О Г Р А М М А   Б 1 . В . 1 8"
    result = assess_pdf_text_quality(text)
    assert result["quality"] == "poor"
    assert result["needs_manual_passport"] is True


def test_pdf_quality_good_with_passport() -> None:
    text = (
        'дисциплины: Б1.В.18 Сметное дело\n'
        "Объем дисциплины 4 з.е.\n"
        "ФИО автора РП и ФОС: Иванов И.И."
    )
    result = assess_pdf_text_quality(text)
    assert result["quality"] == "good"
    assert result["needs_manual_passport"] is False
