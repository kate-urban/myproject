"""Экспорт DOCX через {{TAG}} макет (docxtpl) — один источник оформления."""

from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.utils.section_slug import section_slug

_PLACEHOLDER_RE = re.compile(r"\{\{([^#%}][^}]*)\}\}")
_SECTION_TAG_RE = re.compile(r"^SECTION_")

SIGNATURE_TAGS = frozenset(
    {
        "SIGNATURE_DIRECTOR",
        "SIGNATURE_HEAD",
        "SIGNATURE_DEPT_HEAD",
        "SIGNATURE_SUPERVISOR",
    }
)


def scan_template_tags(template_path: str | Path) -> set[str]:
    found: set[str] = set()
    path = Path(template_path)
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            for raw in _PLACEHOLDER_RE.findall(text):
                tag = raw.strip().replace("-", "_")
                if tag and " " not in tag and "{" not in tag:
                    found.add(tag)
    return found


def template_uses_tagged_layout(template_path: str | Path) -> bool:
    tags = scan_template_tags(template_path)
    if not tags:
        return False
    if any(_SECTION_TAG_RE.match(tag) for tag in tags):
        return True
    header_tags = {
        "DISCIPLINE_CODE",
        "DISCIPLINE_NAME",
        "DIRECTION_CODE",
        "HEAD_LINE",
        "SIGNATURE_DIRECTOR",
    }
    return len(tags & header_tags) >= 2


def _prepare_render_template(template_path: Path, work_dir: Path) -> Path:
    """Копия шаблона: дефисы в SECTION_* → _ для Jinja."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / f"{template_path.stem}_render.docx"
    shutil.copy2(template_path, out_path)
    tag_pattern = re.compile(r"\{\{(SECTION_[^}]+)\}\}")
    with zipfile.ZipFile(out_path, "r") as zin:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    text = data.decode("utf-8")
                    text = tag_pattern.sub(
                        lambda m: "{{" + m.group(1).replace("-", "_") + "}}",
                        text,
                    )
                    data = text.encode("utf-8")
                zout.writestr(item, data)
        payload.seek(0)
        out_path.write_bytes(payload.read())
    return out_path


def _match_section_tag(section_name: str, template_tags: set[str]) -> str | None:
    slug = section_slug(section_name)
    direct = f"SECTION_{slug}"
    if direct in template_tags:
        return direct

    number_match = re.match(r"^(\d+(?:\.\d+)*)", section_name.strip())
    section_num = number_match.group(1) if number_match else ""
    section_lower = section_name.lower()

    best: str | None = None
    best_score = 0
    for tag in template_tags:
        if not tag.startswith("SECTION_"):
            continue
        body = tag[8:].lower()
        score = 0
        if section_num and body.startswith(section_num.replace(".", "_")):
            score += 10
        if section_num and section_num.replace(".", "_") in body:
            score += 8
        slug_lower = slug.lower()
        if slug_lower in body or body in slug_lower:
            score += 5
        for word in re.findall(r"\w{4,}", section_lower):
            if word in body:
                score += 1
        if score > best_score:
            best_score = score
            best = tag
    return best if best_score >= 5 else None


def _html_to_subdoc(tpl, html: str):
    from app.utils.html_converter import html_to_docx_elements

    sub = tpl.new_subdoc()
    if html and str(html).strip():
        html_to_docx_elements(html, sub)
    return sub


def _resolve_signature_path(raw: str | None, project_root: Path) -> Path | None:
    from app.services.signature_storage import resolve_signature_path

    return resolve_signature_path(raw, project_root)


def build_tagged_context(
    tpl,
    *,
    template_tags: set[str],
    sections_data: dict[str, str],
    sections_order: list[str] | None,
    project_root: Path,
    rpd=None,
    discipline_code: str | None = None,
    discipline_name: str | None = None,
    direction_code: str | None = None,
    direction_name: str | None = None,
    profile_name: str | None = None,
    department_name: str | None = None,
    education_level: str | None = None,
    approval_date: str | None = None,
    authors: list[str] | None = None,
    signatures: list | None = None,
) -> dict[str, Any]:
    from docx.shared import Mm
    from docxtpl import InlineImage

    if rpd:
        discipline_code = discipline_code or rpd.discipline_code
        discipline_name = discipline_name or rpd.discipline_name
        direction_code = direction_code or rpd.direction_code
        profile_name = profile_name or rpd.profile_name
        authors = authors if authors is not None else list(rpd.authors or [])

    director = (os.getenv("EXPECTED_DIRECTOR") or "").strip()
    head = (os.getenv("EXPECTED_DISCIPLINE_HEAD") or "").strip()
    if rpd:
        director = director or (rpd.director_name or "")
        head = head or (rpd.discipline_head or "")

    author_name = authors[0] if authors else ""
    education_level = education_level or os.getenv(
        "EDUCATION_LEVEL_LABEL", "уровень бакалавриата"
    )
    approval_date = approval_date or (
        str(rpd.approval_year) if rpd and rpd.approval_year else ""
    )

    text_values: dict[str, str] = {
        "DIRECTOR_LINE": director,
        "EXPECTED_DIRECTOR": director,
        "DIRECTOR_NAME": director,
        "HEAD_LINE": head,
        "DISCIPLINE_HEAD_LINE": head,
        "EXPECTED_DISCIPLINE_HEAD": head,
        "HEAD_NAME": head,
        "DISCIPLINE_CODE": discipline_code or "",
        "DISCIPLINE_NAME": discipline_name or "",
        "DIRECTION_CODE": direction_code or "",
        "DIRECTION_NAME": direction_name or "",
        "EDUCATION_LEVEL": education_level,
        "PROFILE_SPECIALIZATION": profile_name or "",
        "DEPARTMENT_NAME": department_name or "",
        "APPROVAL_DATE": approval_date,
        "APPROVAL_YEAR": approval_date,
        "AUTHOR1_NAME": author_name,
        "AUTHOR1_POSITION": "",
        "AUTHOR1_DEGREE": "",
        "DEPT_PROTOCOL_NO": "",
        "DEPT_PROTOCOL_DAY": "",
        "DEPT_PROTOCOL_MONTH": "",
        "DEPT_PROTOCOL_YEAR": approval_date,
        "DEPT_HEAD_DEGREE_NAME": head,
        "REAPPROVAL_ROWS": "",
        "REAPPROVAL_YEARS": "",
    }

    sig_by_role = {
        "director": "SIGNATURE_DIRECTOR",
        "discipline_head": "SIGNATURE_HEAD",
        "dept_head": "SIGNATURE_DEPT_HEAD",
    }

    context: dict[str, Any] = {}
    for tag in template_tags:
        if tag in SIGNATURE_TAGS:
            role = next((r for r, t in sig_by_role.items() if t == tag), None)
            png_path = None
            if signatures and role:
                for sig in signatures:
                    if getattr(sig, "role", None) == role and getattr(sig, "is_active", True):
                        png_path = _resolve_signature_path(
                            getattr(sig, "png_path", None), project_root
                        )
                        break
            if png_path and png_path.is_file():
                context[tag] = InlineImage(tpl, str(png_path), width=Mm(34))
            else:
                context[tag] = ""
            continue

        if tag.startswith("SECTION_"):
            continue

        context[tag] = text_values.get(tag, "")

    order = sections_order or list(sections_data.keys())
    for section_name in order:
        html = sections_data.get(section_name)
        if not html or not str(html).strip():
            continue
        tag = _match_section_tag(section_name, template_tags)
        if tag:
            context[tag] = _html_to_subdoc(tpl, html)

    for tag in template_tags:
        if tag.startswith("SECTION_") and tag not in context:
            context[tag] = ""

    return context


def render_tagged_template(
    *,
    template_path: str | Path,
    output_path: str | Path,
    sections_data: dict[str, str],
    sections_order: list[str] | None = None,
    project_root: Path | None = None,
    **kwargs,
) -> dict[str, int]:
    from docxtpl import DocxTemplate

    template_path = Path(template_path)
    output_path = Path(output_path)
    project_root = project_root or Path(__file__).resolve().parents[2]

    template_tags = scan_template_tags(template_path)
    with tempfile.TemporaryDirectory() as tmp:
        render_path = _prepare_render_template(template_path, Path(tmp))
        tpl = DocxTemplate(str(render_path))
        context = build_tagged_context(
            tpl,
            template_tags=template_tags,
            sections_data=sections_data,
            sections_order=sections_order,
            project_root=project_root,
            **kwargs,
        )
        tpl.render(context)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tpl.save(str(output_path))

    section_tags = [t for t in template_tags if t.startswith("SECTION_")]
    filled_sections = sum(
        1
        for name in (sections_order or list(sections_data.keys()))
        if _match_section_tag(name, template_tags)
    )
    return {
        "template_tags": len(template_tags),
        "section_tags": len(section_tags),
        "sections_filled": filled_sections,
    }
