"""Импорт учебного плана из нативного XML *.plx (АС UpVo / MMIS)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from app.services.importers.dto import DisciplineDTO, StudyPlanDTO
from app.utils.plan_title import PlanTitleInfo, form_from_code, parse_titul

# ТипОбъекта=1 — блок/модуль без собственного РПД; 2 — дисциплина; 3 — практика; 6 — ГИА.
IMPORTABLE_OBJECT_TYPES = {"2", "3", "6"}

# Служебные виды работ в ПланыНовыеЧасы (не участвуют в R022/R023).
SKIP_WORK_TYPE_CODES = {"50", "51", "1000", "1001"}


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _attr(el: ET.Element, name: str, default: str = "") -> str:
    return el.attrib.get(name, default)


def _int_attr(el: ET.Element, name: str) -> int | None:
    raw = _attr(el, name)
    if not raw:
        return None
    try:
        return int(float(raw.replace(",", ".")))
    except ValueError:
        return None


def _float_attr(el: ET.Element, name: str) -> float | None:
    raw = _attr(el, name)
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _read_xml_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8")


def _iter_by_local_name(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [el for el in root.iter() if _local_tag(el.tag) == local_name]


def _load_work_types(root: ET.Element) -> dict[str, dict[str, str]]:
    work_types: dict[str, dict[str, str]] = {}
    for el in _iter_by_local_name(root, "СправочникВидыРабот"):
        code = _attr(el, "Код")
        if code:
            work_types[code] = dict(el.attrib)
    return work_types


def _hour_bucket(work_code: str, meta: dict[str, str]) -> str | None:
    if not work_code or work_code in SKIP_WORK_TYPE_CODES:
        return None
    type_code = meta.get("КодТипРабот", "")
    if type_code == "7":
        return "control"
    if type_code in {"5", "6"} or work_code in {"107", "108", "140"}:
        return "sr"
    if meta.get("Контактный", "").lower() == "true":
        return "contact"
    return None


def _aggregate_row_hours(
    root: ET.Element,
    row_code: str,
    work_types: dict[str, dict[str, str]],
) -> tuple[int | None, int | None, int | None, int | None]:
    """Суммирует часы из <ПланыНовыеЧасы> для строки плана (КодОбъекта = row_code)."""
    per_slot: dict[tuple[str, str, str], int] = {}
    for el in _iter_by_local_name(root, "ПланыНовыеЧасы"):
        if _attr(el, "КодОбъекта") != row_code:
            continue
        work_code = _attr(el, "КодВидаРаботы")
        if not work_code or work_code in SKIP_WORK_TYPE_CODES:
            continue
        qty = _int_attr(el, "Количество")
        if qty is None:
            continue
        slot = (
            _attr(el, "Курс") or "0",
            _attr(el, "Семестр") or "0",
            work_code,
        )
        per_slot[slot] = max(per_slot.get(slot, 0), qty)

    contact = sr = control = 0
    for (_, _, work_code), qty in per_slot.items():
        bucket = _hour_bucket(work_code, work_types.get(work_code, {}))
        if bucket == "contact":
            contact += qty
        elif bucket == "sr":
            sr += qty
        elif bucket == "control":
            control += qty

    return (
        contact or None,
        contact or None,
        sr or None,
        None,
    )


class PlxXmlReader:
    """Читает *.plx и возвращает StudyPlanDTO."""

    def read(self, path: str | Path) -> StudyPlanDTO:
        file_path = Path(path)
        root = ET.fromstring(_read_xml_text(file_path))

        doc_el = next(
            (el for el in root.iter() if _local_tag(el.tag) == "Документ"),
            root,
        )
        plan_el = next(
            (el for el in root.iter() if _local_tag(el.tag) == "Планы"),
            None,
        )
        if plan_el is None:
            raise ValueError(f"В {file_path.name} не найден элемент <Планы>")

        titul = _attr(plan_el, "Титул")
        title_info = parse_titul(titul)
        if title_info is None:
            oop_el = next(
                (el for el in root.iter() if _local_tag(el.tag) == "ООП"),
                None,
            )
            if oop_el is None:
                raise ValueError(
                    f"Не удалось разобрать титул и не найден <ООП> в {file_path.name}"
                )
            title_info = PlanTitleInfo(
                direction_code=_attr(oop_el, "Шифр"),
                direction_name=_attr(oop_el, "Название"),
                profile_name=_attr(oop_el, "Название"),
            )

        form_code = _attr(plan_el, "КодФормыОбучения") or _attr(
            doc_el, "КодФормыОбучения"
        )
        year = _int_attr(plan_el, "ГодНачалаПодготовки")

        competency_by_id: dict[str, str] = {}
        for comp_el in _iter_by_local_name(root, "ПланыКомпетенции"):
            comp_id = _attr(comp_el, "Код")
            cipher = _attr(comp_el, "ШифрКомпетенции")
            if comp_id and cipher:
                competency_by_id[comp_id] = cipher

        discipline_links: dict[str, list[str]] = {}
        for link_el in _iter_by_local_name(root, "ПланыКомпетенцииДисциплины"):
            row_code = _attr(link_el, "КодСтроки")
            comp_id = _attr(link_el, "КодКомпетенции")
            cipher = competency_by_id.get(comp_id)
            if not row_code or not cipher:
                continue
            discipline_links.setdefault(row_code, []).append(cipher)

        work_types = _load_work_types(root)

        disciplines: list[DisciplineDTO] = []
        for row_el in _iter_by_local_name(root, "ПланыСтроки"):
            if _attr(row_el, "СчитатьВПлане").lower() != "true":
                continue

            code = _attr(row_el, "ДисциплинаКод").strip()
            if not code:
                continue

            object_type = _attr(row_el, "ТипОбъекта")
            if object_type and object_type not in IMPORTABLE_OBJECT_TYPES:
                continue

            row_code = _attr(row_el, "Код")
            credits = _float_attr(row_el, "ЗЕТфакт")
            if credits is None:
                credits = _float_attr(row_el, "ТрудоемкостьКредитов")

            comp_codes = sorted(set(discipline_links.get(row_code, [])))
            hours_contact, hours_aud, hours_sr, hours_control = _aggregate_row_hours(
                root, row_code, work_types
            )
            disciplines.append(
                DisciplineDTO(
                    code=code,
                    name=_attr(row_el, "Дисциплина").strip(),
                    in_plan=True,
                    credits=credits,
                    hours_total=_int_attr(row_el, "ЧасовПоПлану"),
                    hours_contact=hours_contact,
                    hours_aud=hours_aud,
                    hours_sr=hours_sr,
                    hours_control=hours_control,
                    department_code=_attr(row_el, "КодКафедры") or None,
                    plx_row_code=row_code or None,
                    nesting_level=_int_attr(row_el, "УровеньВложения") or 1,
                    row_order=_int_attr(row_el, "Порядок") or 0,
                    object_type=object_type or None,
                    competencies=comp_codes,
                )
            )

        disciplines.sort(key=lambda d: (d.row_order, d.code))

        source_file = _attr(plan_el, "ИмяФайла") or file_path.name
        return StudyPlanDTO(
            source_file=source_file,
            source_format="xml_upvo",
            direction_code=title_info.direction_code,
            direction_name=title_info.direction_name,
            profile_name=title_info.profile_name,
            form=form_from_code(form_code),
            year=year,
            qualification=_attr(plan_el, "Квалификация") or None,
            fgos_number=_attr(plan_el, "НомерФГОС") or None,
            disciplines=disciplines,
        )
