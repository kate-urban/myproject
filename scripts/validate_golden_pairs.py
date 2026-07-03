#!/usr/bin/env python3
"""Пакетная валидация эталонных пар 54.04.01 (шаг 2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import Direction, PlanDiscipline, PlanDisciplineCompetency, Profile, StudyPlan
from app.services.importers import StudyPlanImporter
from app.services.rpd_extractor import extract_rpd
from app.services.validation import validate_discipline
from tests.golden_design_data import DESIGN_PLX, GOLDEN_DESIGN_PAIRS


def _plan_from_dto(dto) -> StudyPlan:
    direction = Direction(code=dto.direction_code, name=dto.direction_name)
    profile = Profile(name=dto.profile_name, direction=direction)
    return StudyPlan(
        profile=profile,
        source_file=dto.source_file,
        source_format=dto.source_format,
        form=dto.form,
    )


def _discipline_from_dto(dto, code: str) -> PlanDiscipline:
    item = next(d for d in dto.disciplines if d.code == code)
    return PlanDiscipline(
        code=item.code,
        name=item.name,
        hours_total=item.hours_total,
        hours_contact=item.hours_contact,
        hours_aud=item.hours_aud,
        hours_sr=item.hours_sr,
        hours_control=item.hours_control,
        credits=item.credits,
        department_code=item.department_code,
        in_plan=item.in_plan,
        competencies=[
            PlanDisciplineCompetency(competency_code=code)
            for code in item.competencies
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate golden design pairs")
    parser.add_argument("--pair", action="append", help="Pair id (default: all)")
    args = parser.parse_args()

    if not DESIGN_PLX.is_file():
        print(f"Missing study plan: {DESIGN_PLX}", file=sys.stderr)
        return 2

    plan_dto = StudyPlanImporter().read_dto(DESIGN_PLX)
    plan = _plan_from_dto(plan_dto)
    pairs = GOLDEN_DESIGN_PAIRS
    if args.pair:
        selected = set(args.pair)
        pairs = [pair for pair in pairs if pair.id in selected]

    failed = 0
    for pair in pairs:
        if not pair.files_present:
            print(f"[SKIP] {pair.id}: sample files missing")
            continue
        discipline = _discipline_from_dto(plan_dto, pair.discipline_code)
        rpd = extract_rpd(pair.rpd_path.read_bytes(), pair.rpd_path.name)
        report = validate_discipline(plan, discipline, rpd)
        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] {pair.id} ({pair.discipline_code})")
        if not report.passed:
            failed += 1
            for item in report.results:
                if item.skipped or item.passed or item.severity != "critical":
                    continue
                print(f"  - {item.rule_id}: {item.message}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
