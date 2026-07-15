"""Снимок structured RPD из RpdExtract."""

from __future__ import annotations

from app.services.rpd_extractor import RpdExtract, VolumeBreakdown
from app.services.structured_rpd_sync import build_structured_payload


def test_build_structured_payload_includes_tz_fields() -> None:
    rpd = RpdExtract(
        discipline_code="Б1.О.01.07",
        discipline_name="Тест",
        volume=VolumeBreakdown(contact=100, sr=200),
        topic_numbers=[1, 2],
        topics31_assessments=[{"form_type": "exam", "semester": 1}],
        topic_titles_bold=[{"topic": 1, "title": "Тема 1"}],
        matrix_36_rows=[{"indicator": "ОПК-1", "topic": 1}],
    )
    payload = build_structured_payload(rpd)
    assert payload["passport"]["discipline_code"] == "Б1.О.01.07"
    assert payload["topic_numbers"] == [1, 2]
    assert payload["assessments_31"][0]["form_type"] == "exam"
    assert payload["matrix_36"][0]["indicator"] == "ОПК-1"
