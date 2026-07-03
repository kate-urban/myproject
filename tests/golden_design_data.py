"""Эталонные пары 54.04.01 (M540401) из docs/golden_pairs.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
DESIGN_PLX = SAMPLES / "M540401-2026.plx"


@dataclass(frozen=True)
class GoldenDesignPair:
    id: str
    discipline_code: str
    discipline_name: str
    credits: float
    hours_total: int
    department_code: str
    rpd_file: str
    validation_passes: bool = True
    known_failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def rpd_path(self) -> Path:
        return SAMPLES / self.rpd_file

    @property
    def files_present(self) -> bool:
        return DESIGN_PLX.is_file() and self.rpd_path.is_file()


GOLDEN_DESIGN_PAIRS: tuple[GoldenDesignPair, ...] = (
    GoldenDesignPair(
        id="design_b1o0107",
        discipline_code="Б1.О.01.07",
        discipline_name="Проектная деятельность",
        credits=11,
        hours_total=396,
        department_code="55",
        rpd_file="B1_O_01_07_Proektnaya_deyatelnost_k55.docx",
    ),
    GoldenDesignPair(
        id="design_b1v0103",
        discipline_code="Б1.В.01.03",
        discipline_name="Маркетинг экологических продуктов",
        credits=4,
        hours_total=144,
        department_code="51",
        rpd_file="B1_V_01_03_Marketing_ekologicheskikh_produktov_k51.docx",
    ),
    GoldenDesignPair(
        id="design_b1v0205",
        discipline_code="Б1.В.02.05",
        discipline_name="Компьютерные технологии в науке и производстве",
        credits=3,
        hours_total=108,
        department_code="45",
        rpd_file="B1_V_02_05_Kompyuternye_tekhnologii_v_nauke_i_proizvodstve_k45.docx",
    ),
    GoldenDesignPair(
        id="design_b2o03p",
        discipline_code="Б2.О.03(П)",
        discipline_name="Производственная практика. Проектная практика",
        credits=18,
        hours_total=648,
        department_code="55",
        rpd_file="B2_O_03_P_Proizvodstvennaya_praktika_Proektnaya_praktika_k55.docx",
    ),
    GoldenDesignPair(
        id="design_ftd01",
        discipline_code="ФТД.01",
        discipline_name="История развития науки и техники",
        credits=2,
        hours_total=72,
        department_code="52",
        rpd_file="FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx",
    ),
    GoldenDesignPair(
        id="design_ftd04",
        discipline_code="ФТД.04",
        discipline_name="Основы таксидермии",
        credits=2,
        hours_total=72,
        department_code="40",
        rpd_file="FTD_04_Osnovy_taxidermii_k40.docx",
    ),
)

PAIR_IDS = [pair.id for pair in GOLDEN_DESIGN_PAIRS]
