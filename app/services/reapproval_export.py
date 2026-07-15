"""Экспорт листов переутверждения PDF (ТЗ сценарий 2, AC-REAP-1..3)."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz
import yaml

from app.models_tz import ProgramAmendment
from app.services.archive_typography import insert_cyrillic_text
from app.services.export_finalize import _current_academic_year_start
from app.services.signature_storage import resolve_signature_path

_LAYOUT_PATH = Path(__file__).resolve().parents[1] / "data" / "reapproval_layout.yaml"
_MM = 72.0 / 25.4

_MONTHS_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


@dataclass(frozen=True)
class _RowLayout:
    year_y: float
    status_y: float
    dept_y: float
    proto_y: float
    attach_y: float
    sign_y: float


@dataclass
class ReapprovalSignature:
    full_name: str = ""
    png_path: str | None = None


@dataclass
class _ProtocolFields:
    number: str = ""
    day: str = ""
    month: str = ""
    year_label: str = ""


@dataclass
class _RowFill:
    academic_year_start: int | None = None
    kind: str = "empty"  # empty | none | changed
    department_name: str = ""
    protocol: _ProtocolFields | None = None
    attach_year_start: int | None = None
    change_summary: str = ""


def _academic_year_label(start_year: int) -> str:
    return f"{start_year}/{start_year + 1}"


def _format_year_phrase(year: int) -> str:
    if year >= 2000:
        y1 = f"{year // 100} {year % 100:02d}"
        y2 = year + 1
        y2s = f"{y2 // 100} {y2 % 100:02d}"
        return f"на {y1} / {y2s} учебный год"
    return f"на {year}/{year + 1} учебный год"


def _format_year_short(year: int) -> str:
    if year >= 2000:
        return f"{year // 100} {year % 100:02d} г."
    return f"{year} г."


def _load_layout() -> tuple[list[_RowLayout], dict]:
    if not _LAYOUT_PATH.is_file():
        return _default_layout()
    raw = yaml.safe_load(_LAYOUT_PATH.read_text(encoding="utf-8")) or {}
    rows = [
        _RowLayout(
            year_y=float(item["year_y"]),
            status_y=float(item["status_y"]),
            dept_y=float(item["dept_y"]),
            proto_y=float(item["proto_y"]),
            attach_y=float(item["attach_y"]),
            sign_y=float(item["sign_y"]),
        )
        for item in raw.get("rows", [])
    ]
    return rows or _default_layout()[0], raw


def _default_layout() -> tuple[list[_RowLayout], dict]:
    rows = [
        _RowLayout(133.3, 161.5, 181.2, 231.3, 259.8, 290.1),
        _RowLayout(342.6, 370.4, 388.5, 436.8, 470.6, 500.8),
        _RowLayout(555.2, 584.7, 602.8, 651.2, 682.8, 711.3),
    ]
    return rows, {}


def _row_text_for_amendment(amendment: ProgramAmendment) -> str:
    kind = (amendment.amendment_kind or "").lower()
    year_label = _academic_year_label(amendment.enrollment_year)
    if kind == "none":
        return f"на {year_label} учебный год — без изменений"
    protocol = amendment.protocol_ref or "протокол изменений от «___» __________ ____ г."
    summary = (amendment.change_summary or "").strip()
    base = f"на {year_label} учебный год — {protocol}"
    return f"{base}. {summary}".strip() if summary else base


def _parse_protocol_ref(text: str | None) -> _ProtocolFields:
    if not text:
        return _ProtocolFields()
    fields = _ProtocolFields()
    number = re.search(r"№\s*(\d+)", text)
    if number:
        fields.number = number.group(1)
    day = re.search(r"«\s*(\d{1,2})\s*»", text)
    if day:
        fields.day = day.group(1)
    for idx, name in enumerate(_MONTHS_RU):
        if name and name in text.lower():
            fields.month = name
            break
    year = re.search(r"(\d{4})\s*г", text)
    if year:
        fields.year_label = _format_year_short(int(year.group(1)))
    else:
        short = re.search(r"(\d{2})\s*г", text)
        if short:
            fields.year_label = f"{short.group(1)} г."
    return fields


def _protocol_from_amendment(amendment: ProgramAmendment) -> _ProtocolFields:
    fields = _parse_protocol_ref(amendment.protocol_ref)
    if amendment.approved_on:
        approved = amendment.approved_on
        if not fields.day:
            fields.day = str(approved.day)
        if not fields.month and 1 <= approved.month <= 12:
            fields.month = _MONTHS_RU[approved.month]
        if not fields.year_label:
            fields.year_label = _format_year_short(approved.year)
    return fields


def _fill_from_amendment(amendment: ProgramAmendment, department_name: str = "") -> _RowFill:
    kind = (amendment.amendment_kind or "").lower()
    row_kind = "none" if kind == "none" else "changed"
    protocol = _protocol_from_amendment(amendment)
    return _RowFill(
        academic_year_start=amendment.enrollment_year,
        kind=row_kind,
        department_name=department_name,
        protocol=protocol,
        attach_year_start=amendment.enrollment_year if row_kind == "changed" else None,
        change_summary=(amendment.change_summary or "").strip(),
    )


def build_row_fills(
    *,
    variant: str,
    amendments: list[ProgramAmendment] | None = None,
    reapproval_years: list[int] | None = None,
    department_name: str = "",
) -> list[_RowFill]:
    current = _current_academic_year_start()
    slots = [current - 2, current - 1, current]
    fills: list[_RowFill] = [_RowFill() for _ in slots]

    if variant == "empty":
        return fills

    if variant == "simple":
        fills[0] = _RowFill(
            academic_year_start=slots[0],
            kind="none",
            department_name=department_name,
            protocol=_ProtocolFields(number="1", day="31", month="августа", year_label=_format_year_short(slots[0] + 1)),
        )
        return fills

    if variant == "transition":
        fills[0] = _RowFill(
            academic_year_start=slots[0],
            kind="none",
            department_name=department_name,
            protocol=_ProtocolFields(number="1", day="31", month="августа", year_label=_format_year_short(slots[0] + 1)),
        )
        fills[1] = _RowFill(
            academic_year_start=slots[1],
            kind="changed",
            department_name=department_name,
            protocol=_ProtocolFields(
                number="1",
                day="31",
                month="августа",
                year_label=_format_year_short(slots[1] + 1),
            ),
            attach_year_start=slots[1],
        )
        return fills

    year_to_amendment: dict[int, ProgramAmendment] = {
        item.enrollment_year: item for item in (amendments or [])
    }

    for year in reapproval_years or []:
        if year not in year_to_amendment:
            offset = year - slots[0]
            if 0 <= offset < 3:
                fills[offset] = _RowFill(
                    academic_year_start=year,
                    kind="none",
                    department_name=department_name,
                )

    for slot_year in slots:
        amendment = year_to_amendment.get(slot_year)
        if amendment is None:
            continue
        offset = slot_year - slots[0]
        if 0 <= offset < 3:
            fills[offset] = _fill_from_amendment(amendment, department_name=department_name)

    return fills


def _fill_to_row_text(fill: _RowFill) -> str:
    if fill.academic_year_start is None:
        return ""
    year_label = _academic_year_label(fill.academic_year_start)
    if fill.kind == "none":
        return f"на {year_label} учебный год — без изменений"
    protocol = fill.protocol
    if protocol and protocol.number:
        proto = f"протокол №{protocol.number} от «{protocol.day or '___'}» {protocol.month or '__________'} {protocol.year_label or '____'}"
    else:
        proto = "протокол изменений от «___» __________ ____ г."
    base = f"на {year_label} учебный год — {proto}"
    return f"{base}. {fill.change_summary}".strip() if fill.change_summary else base


def build_reapproval_rows(
    *,
    variant: str,
    amendments: list[ProgramAmendment] | None = None,
    enrollment_year: int | None = None,
    reapproval_years: list[int] | None = None,
    department_name: str = "",
) -> list[str]:
    del enrollment_year
    fills = build_row_fills(
        variant=variant,
        amendments=amendments,
        reapproval_years=reapproval_years,
        department_name=department_name,
    )
    return [_fill_to_row_text(fill) for fill in fills]


def _reapproval_template_path() -> Path | None:
    candidates = [
        Path("samples/Информационные материалы/Макет переутверждения.pdf"),
        Path("samples/Informatsionnye_materialy/Maket_pereutverzhdeniya.pdf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _whiteout(page: fitz.Page, rect: fitz.Rect) -> None:
    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))


def _rect_at(base_y: float, spec: list[float]) -> fitz.Rect:
    x0, y_off, x1, height = spec
    return fitz.Rect(x0, base_y + y_off, x1, base_y + height)


def _point_at(base_y: float, spec: list[float]) -> tuple[float, float]:
    return float(spec[0]), base_y + float(spec[1])


def _sign_line_geometry(layout: _RowLayout, layout_cfg: dict) -> tuple[float, float, float]:
    """Левая черта «(подпись)»: x0, x1, y линии."""
    y_off = float(layout_cfg.get("sign_line_y_offset", 16.5))
    x0 = float(layout_cfg.get("sign_line_x0", 230.6))
    x1 = float(layout_cfg.get("sign_line_x1", 328.2))
    return x0, x1, layout.sign_y + y_off


def _name_line_geometry(layout: _RowLayout, layout_cfg: dict) -> tuple[float, float, float]:
    """Правая черта «(расшифровка подписи)»."""
    y_off = float(layout_cfg.get("sign_line_y_offset", 16.5))
    x0 = float(layout_cfg.get("sign_name_line_x0", 380.6))
    x1 = float(layout_cfg.get("sign_name_line_x1", 493.3))
    return x0, x1, layout.sign_y + y_off


def _insert_signature_image(
    page: fitz.Page,
    layout: _RowLayout,
    layout_cfg: dict,
    signature: ReapprovalSignature,
) -> bool:
    if not signature.png_path:
        return False
    png = resolve_signature_path(signature.png_path)
    if png is None:
        return False

    line_x0, line_x1, line_y = _sign_line_geometry(layout, layout_cfg)
    gap = float(layout_cfg.get("sign_image_gap_pt", 1.5))
    w_mm = float(layout_cfg.get("sign_image_width_mm", 34))
    h_mm = float(layout_cfg.get("sign_image_height_mm", 24))
    min_attach_gap = float(layout_cfg.get("sign_image_min_attach_gap_pt", 18))

    line_w = line_x1 - line_x0
    w_pt = min(w_mm * _MM, line_w * 0.98)
    max_h = line_y - gap - (layout.attach_y + min_attach_gap)
    h_pt = min(h_mm * _MM, max(max_h, 36.0))
    bottom = line_y - gap
    top = bottom - h_pt
    center = (line_x0 + line_x1) / 2
    left = center - w_pt / 2

    _whiteout(page, fitz.Rect(line_x0 - 4, top - 3, line_x1 + 4, line_y + 1))
    page.insert_image(
        fitz.Rect(left, top, left + w_pt, bottom),
        filename=str(png),
    )
    return True


def _insert_signature_name(
    page: fitz.Page,
    layout: _RowLayout,
    layout_cfg: dict,
    full_name: str,
) -> None:
    if not full_name:
        return
    nx0, nx1, line_y = _name_line_geometry(layout, layout_cfg)
    baseline_off = float(layout_cfg.get("sign_name_baseline_offset", -3.5))
    name_y = line_y + baseline_off
    name_x = nx0 + 6
    _whiteout(page, fitz.Rect(nx0 - 2, line_y - 16, nx1 + 2, line_y + 2))
    insert_cyrillic_text(page, (name_x, name_y), full_name[:40], fontsize=12)


def _fill_row(
    page: fitz.Page,
    layout: _RowLayout,
    fill: _RowFill,
    *,
    layout_cfg: dict,
    signature: ReapprovalSignature | None = None,
) -> None:
    if fill.kind == "empty" or fill.academic_year_start is None:
        return

    year = fill.academic_year_start
    year_rect = layout_cfg.get("year_rect", [190, -4, 395, 18])
    status_rect = layout_cfg.get("status_rect", [278, -4, 490, 18])
    dept_rect = layout_cfg.get("dept_rect", [205, -4, 340, 18])

    _whiteout(page, _rect_at(layout.year_y, year_rect))
    insert_cyrillic_text(page, (195.5, layout.year_y + 13), _format_year_phrase(year), fontsize=12)

    _whiteout(page, _rect_at(layout.status_y, status_rect))
    if fill.kind == "none":
        insert_cyrillic_text(page, (283.6, layout.status_y + 13), "без изменений", fontsize=12)
    else:
        insert_cyrillic_text(page, (392.4, layout.status_y + 13), "с изменениями", fontsize=12)

    dept_name = fill.department_name or ""
    if dept_name:
        _whiteout(page, _rect_at(layout.dept_y, dept_rect))
        insert_cyrillic_text(page, (210.5, layout.dept_y + 13), dept_name[:48], fontsize=12)

    protocol = fill.protocol or _ProtocolFields()
    if protocol.number or protocol.day or protocol.month or protocol.year_label:
        proto_whiteout = layout_cfg.get("protocol_whiteout", [160, -4, 445, 18])
        _whiteout(page, _rect_at(layout.proto_y, proto_whiteout))
        if protocol.number:
            x, y = _point_at(layout.proto_y, layout_cfg.get("protocol_no", [165.6, 13]))
            insert_cyrillic_text(page, (x, y), protocol.number, fontsize=12)
        if protocol.day:
            x, y = _point_at(layout.proto_y, layout_cfg.get("protocol_day", [221.6, 13]))
            insert_cyrillic_text(page, (x, y), f"« {protocol.day} »", fontsize=12)
        if protocol.month:
            x, y = _point_at(layout.proto_y, layout_cfg.get("protocol_month", [309.5, 13]))
            insert_cyrillic_text(page, (x, y), protocol.month, fontsize=12)
        if protocol.year_label:
            x, y = _point_at(layout.proto_y, layout_cfg.get("protocol_year", [390.0, 13]))
            insert_cyrillic_text(page, (x, y), protocol.year_label, fontsize=12)

    if fill.kind == "changed" and fill.attach_year_start is not None:
        attach_whiteout = layout_cfg.get("attach_whiteout", [230, -4, 325, 18])
        _whiteout(page, _rect_at(layout.attach_y, attach_whiteout))
        ay = fill.attach_year_start
        x_a, y_a = _point_at(layout.attach_y, layout_cfg.get("attach_year_a", [236.9, 13]))
        x_b, y_b = _point_at(layout.attach_y, layout_cfg.get("attach_year_b", [283.2, 13]))
        if ay >= 2000:
            insert_cyrillic_text(page, (x_a, y_a), str(ay // 100), fontsize=10)
            insert_cyrillic_text(page, (x_b, y_b), f"/ {ay % 100:02d}", fontsize=10)
        else:
            insert_cyrillic_text(page, (x_a, y_a), str(ay), fontsize=10)

    sign_name = (signature.full_name if signature else "") or ""
    _insert_signature_name(page, layout, layout_cfg, sign_name)

    if signature:
        _insert_signature_image(page, layout, layout_cfg, signature)


def _draw_page(
    *,
    fills: list[_RowFill],
    signature: ReapprovalSignature | None = None,
) -> bytes:
    row_layouts, layout_cfg = _load_layout()
    template = _reapproval_template_path()
    if template is not None:
        doc = fitz.open(str(template))
        page = doc[0]
    else:
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

    for layout, fill in zip(row_layouts, fills):
        if fill.academic_year_start is not None:
            _fill_row(page, layout, fill, layout_cfg=layout_cfg, signature=signature)

    buffer = io.BytesIO()
    doc.save(buffer, deflate=True)
    doc.close()
    return buffer.getvalue()


def build_reapproval_pdf_bytes(
    *,
    variant: str,
    discipline_code: str,
    discipline_name: str,
    amendments: list[ProgramAmendment] | None = None,
    enrollment_year: int | None = None,
    direction_label: str = "",
    reapproval_years: list[int] | None = None,
    department_name: str = "",
    signature: ReapprovalSignature | None = None,
) -> bytes:
    del discipline_code, discipline_name, direction_label, enrollment_year
    fills = build_row_fills(
        variant=variant,
        amendments=amendments,
        reapproval_years=reapproval_years,
        department_name=department_name,
    )
    return _draw_page(fills=fills, signature=signature)
