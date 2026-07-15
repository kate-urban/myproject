"""Тесты экспорта отчётов и UI сверки."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.models import Direction, Profile, StudyPlan
from app.services.validation.fos_engine import FosPlanValidationReport
from app.services.validation.engine import PlanValidationReport
from app.services.validation.report_export import (
    build_validation_report_payload,
    payload_to_json,
    render_validation_report_html,
)


def _plan() -> StudyPlan:
    direction = Direction(code="54.04.01", name="Дизайн")
    profile = Profile(name="Экодизайн", direction=direction)
    return StudyPlan(
        id=uuid4(),
        profile=profile,
        source_file="M540401-2026.plx",
        source_format="xml_upvo",
        form="ochnaya",
        year=2026,
    )


def test_build_validation_report_payload_and_html() -> None:
    plan = _plan()
    rpd_report = PlanValidationReport(
        study_plan_id=plan.id,
        total_disciplines=1,
        checked=1,
        passed=1,
        failed=0,
        missing_rpd=0,
        passed_all=True,
        items=[],
    )
    fos_report = FosPlanValidationReport(
        study_plan_id=plan.id,
        total_disciplines=1,
        checked=1,
        passed=0,
        failed=1,
        missing_fos=0,
        fos_only=1,
        passed_all=False,
        items=[],
    )
    payload = build_validation_report_payload(
        plan,
        rpd_report=rpd_report,
        fos_report=fos_report,
    )
    assert payload["study_plan"]["direction_code"] == "54.04.01"
    assert payload["rpd_validation"]["passed_all"] is True
    assert payload["fos_validation"]["fos_only"] == 1

    html = render_validation_report_html(payload)
    assert "54.04.01" in html
    assert "РПД" in html
    assert "ФОС" in html

    data = payload_to_json(payload)
    assert '"direction_code": "54.04.01"' in data


def test_validation_html_present() -> None:
    path = Path(__file__).resolve().parents[1] / "validation.html"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Сверка УП" in text
    assert "validation_page.js" in text
    assert "/study-plans/" in text or "study-plans" in text
    assert "</style>" in text
    assert "<body>" in text
