"""Smoke-тесты шага 1: импорт всех учебных планов из golden_pairs.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.importers import StudyPlanImporter

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
GOLDEN_YAML = ROOT / "docs" / "golden_pairs.yaml"


def _load_study_plans() -> list[dict]:
    data = yaml.safe_load(GOLDEN_YAML.read_text(encoding="utf-8"))
    plans: list[dict] = []
    for item in data.get("study_plans", []):
        file_name = item.get("file")
        if not file_name:
            continue
        path = SAMPLES / file_name
        if path.is_file():
            plans.append({**item, "path": path})
    return plans


STUDY_PLANS = _load_study_plans()


@pytest.mark.parametrize(
    "plan",
    STUDY_PLANS,
    ids=[item["id"] for item in STUDY_PLANS],
)
def test_golden_study_plan_imports(plan: dict) -> None:
    dto = StudyPlanImporter().read_dto(plan["path"])
    assert dto.direction_code == plan["direction_code"]
    assert dto.profile_name == plan["profile_name"]
    assert len(dto.disciplines) > 0


def test_golden_yaml_step0_reviewed() -> None:
    meta = yaml.safe_load(GOLDEN_YAML.read_text(encoding="utf-8")).get("meta", {})
    assert meta.get("status") == "reviewed"
