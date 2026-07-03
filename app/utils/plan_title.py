"""Разбор метаданных учебного плана из титула UpVo / MMIS."""

from __future__ import annotations

import re
from dataclasses import dataclass

TITUL_RE = re.compile(
    r'направление\s+([\d.]+)\s+"([^"]+)"\s+профиль\s+"([^"]+)"',
    re.IGNORECASE,
)

FORM_BY_CODE = {
    "1": "ochnaya",
    "2": "zaochnaya",
    "3": "ochno_zaochnaya",
}


@dataclass(frozen=True)
class PlanTitleInfo:
    direction_code: str
    direction_name: str
    profile_name: str


def parse_titul(titul: str) -> PlanTitleInfo | None:
    match = TITUL_RE.search(titul or "")
    if not match:
        return None
    return PlanTitleInfo(
        direction_code=match.group(1),
        direction_name=match.group(2).strip(),
        profile_name=match.group(3).strip(),
    )


def form_from_code(code: str | None) -> str:
    return FORM_BY_CODE.get((code or "").strip(), "unknown")


def form_from_filename(filename: str) -> str:
    lower = filename.lower()
    if re.search(r"oz_plx|[-_]oz[-_]|[-_]oz\.", lower) or lower.endswith("oz.plx"):
        return "ochno_zaochnaya"
    if re.search(r"[-_]z_plx|[-_]z[-_]", lower):
        return "zaochnaya"
    return "ochnaya"


def year_from_filename(filename: str) -> int | None:
    match = re.search(r"(?:^|[\-_])(20\d{2})(?:[_\.\-]|$)", filename)
    if not match:
        return None
    return int(match.group(1))
