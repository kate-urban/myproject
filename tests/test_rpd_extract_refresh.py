"""Тесты авто-обновления rpd_extract_json."""

from __future__ import annotations

import json

from app.models import Program
from app.services.rpd_extract_refresh import rpd_extract_is_stale


def test_stale_when_no_tz_keys() -> None:
    program = Program(rpd_extract_json=json.dumps({
        "discipline_code": "Б1.О.08",
        "hours_total": 216,
        "volume": {"contact": 72},
    }))
    assert rpd_extract_is_stale(program) is True


def test_fresh_when_tz_present() -> None:
    program = Program(rpd_extract_json=json.dumps({
        "discipline_code": "Б1.О.08",
        "topics31_zuv_phrases": ["знать основы"],
        "topic_numbers": [1, 2],
        "sr_rows": [{"label": "А", "hours": 10}],
    }))
    assert rpd_extract_is_stale(program) is False
