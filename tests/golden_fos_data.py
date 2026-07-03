"""Эталонные пары plx + rpd/fos для шага 3 (F001–F012)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
DESIGN_PLX = SAMPLES / "M540401-2026.plx"
IST_PLX = SAMPLES / "B090302-CTM-2026.plx"


@dataclass(frozen=True)
class GoldenFosPair:
    id: str
    discipline_code: str
    discipline_name: str
    plx_path: Path
    fos_file: str
    rpd_file: str | None = None
    fos_only: bool = False
    validation_passes: bool = True
    expected_fail_rules: tuple[str, ...] = ()
    credits: float | None = None
    hours_total: int | None = None
    department_code: str | None = None
    plan_competencies: tuple[str, ...] = ()

    @property
    def fos_path(self) -> Path:
        return SAMPLES / self.fos_file

    @property
    def rpd_path(self) -> Path | None:
        if not self.rpd_file:
            return None
        return SAMPLES / self.rpd_file

    @property
    def files_present(self) -> bool:
        if not self.plx_path.is_file() or not self.fos_path.is_file():
            return False
        if self.fos_only:
            return True
        return self.rpd_path is not None and self.rpd_path.is_file()


GOLDEN_FOS_TRIPLE_PAIRS: tuple[GoldenFosPair, ...] = (
    GoldenFosPair(
        id="design_ftd01",
        discipline_code="ФТД.01",
        discipline_name="История развития науки и техники",
        plx_path=DESIGN_PLX,
        credits=2,
        hours_total=72,
        department_code="52",
        plan_competencies=("УК-5.1",),
        rpd_file="FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx",
        fos_file="FOS_FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx",
    ),
)

GOLDEN_FOS_ONLY_PAIRS: tuple[GoldenFosPair, ...] = (
    GoldenFosPair(
        id="design_fos_ftd02",
        discipline_code="ФТД.02",
        discipline_name="Визуализация проектных решений",
        plx_path=DESIGN_PLX,
        fos_file="FOS_FTD_02_Vizualizatsia_proektnykh_resheniy_k55.docx",
        fos_only=True,
    ),
    GoldenFosPair(
        id="design_fos_ftd03",
        discipline_code="ФТД.03",
        discipline_name="Концептуальные эко-инсталляции",
        plx_path=DESIGN_PLX,
        fos_file="FOS_FTD_03_Kontseptualnye_eko-installyatsii_k55.docx",
        fos_only=True,
    ),
)

GOLDEN_FOS_IST_PAIRS: tuple[GoldenFosPair, ...] = (
    GoldenFosPair(
        id="ist_b1o23",
        discipline_code="Б1.О.23",
        discipline_name="Теория информации, данные, знания",
        plx_path=IST_PLX,
        fos_file="FOS_B1_O_23_Teoria_informatsii_dannye_znania_k45.docx",
        fos_only=True,
        plan_competencies=("ОПК-1.1", "УК-1.2"),
    ),
    GoldenFosPair(
        id="ist_b1o13",
        discipline_code="Б1.О.13",
        discipline_name="Технологии программирования",
        plx_path=IST_PLX,
        fos_file="FOS_B1_O_13_Tekhnologii_programmirovania_k45.docx",
        fos_only=True,
        validation_passes=False,
        expected_fail_rules=("F003",),
        plan_competencies=("ОПК-1.1", "ОПК-6.1", "ОПК-6.3"),
    ),
)

GOLDEN_FOS_PAIRS: tuple[GoldenFosPair, ...] = (
    *GOLDEN_FOS_TRIPLE_PAIRS,
    *GOLDEN_FOS_ONLY_PAIRS,
    *GOLDEN_FOS_IST_PAIRS,
)
