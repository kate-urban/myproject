"""Парсер не должен выносить нумерованные вопросы экзамена в отдельные разделы."""

from app.services.parser import DocumentParser


def test_exam_question_is_not_major_chapter() -> None:
    parser = DocumentParser()
    assert parser._looks_like_exam_question_heading(
        "2. Объясните образование времен группы Simple."
    )
    assert not parser._is_major_chapter_heading(
        "2. Объясните образование времен группы Simple."
    )


def test_competency_chapter_still_major() -> None:
    parser = DocumentParser()
    assert parser._is_major_chapter_heading("2. ПЕРЕЧЕНЬ ПЛАНИРУЕМЫХ РЕЗУЛЬТАТОВ")
    assert parser._is_major_chapter_heading("2.1 Универсальные компетенции и индикаторы их достижения")
