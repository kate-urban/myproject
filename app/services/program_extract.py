"""Применение extract РПД/ФОС к модели Program."""

from __future__ import annotations

from app.models import Program
from app.services.fos_extractor import FosExtract
from app.services.rpd_extractor import RpdExtract


def apply_rpd_extract(program: Program, rpd: RpdExtract) -> None:
    program.rpd_discipline_code = rpd.discipline_code
    program.rpd_discipline_name = rpd.discipline_name
    program.rpd_direction_code = rpd.direction_code
    program.rpd_profile_name = rpd.profile_name
    program.rpd_department_code = rpd.department_code
    program.rpd_hours_total = rpd.hours_total
    program.rpd_credits = rpd.credits
    program.rpd_competencies = ";".join(rpd.competencies)
    program.rpd_extract_json = rpd.to_json()


def apply_fos_extract(program: Program, fos: FosExtract) -> None:
    program.fos_extract_json = fos.to_json()
