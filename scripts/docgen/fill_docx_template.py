#!/usr/bin/env python3
"""
Генерация DOCX из шаблона и YAML/JSON с тестовыми данными.

Строгие плейсхолдеры в шаблоне: {{DIRECTOR_LINE}}, {{SIGNATURE_DIRECTOR}}, …
Данные — единственный источник истины (файл --data).

Пример:
  python scripts/docgen/fill_docx_template.py \\
    --template templates/my.docx \\
    --data scripts/docgen/fixtures/example_rpd.yaml \\
    --out output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

_PLACEHOLDER_RE = re.compile(r"\{\{([^#%}][^}]*)\}\}")

# Текстовые плейсхолдеры финализации (совместимость с export_finalize.py)
TEXT_PLACEHOLDERS = frozenset(
    {
        "DIRECTOR_LINE",
        "EXPECTED_DIRECTOR",
        "HEAD_LINE",
        "DISCIPLINE_HEAD_LINE",
        "EXPECTED_DISCIPLINE_HEAD",
        "DISCIPLINE_CODE",
        "DISCIPLINE_NAME",
        "DIRECTION_CODE",
        "DIRECTION_NAME",
        "EDUCATION_LEVEL",
        "PROFILE_SPECIALIZATION",
        "DEPARTMENT_NAME",
        "DIRECTOR_NAME",
        "HEAD_NAME",
        "APPROVAL_DATE",
        "AUTHOR1_DEGREE",
        "AUTHOR1_POSITION",
        "AUTHOR1_NAME",
        "DEPT_PROTOCOL_NO",
        "DEPT_PROTOCOL_DAY",
        "DEPT_PROTOCOL_MONTH",
        "DEPT_PROTOCOL_YEAR",
        "DEPT_HEAD_DEGREE_NAME",
        "APPROVAL_YEAR",
        "REAPPROVAL_YEARS",
        "REAPPROVAL_ROWS",
        "CLIENT_NAME",
        "DOCUMENT_DATE",
    }
)

# PNG над линией подписи — в шаблоне отдельный параграф с ОДНИМ тегом
SIGNATURE_PLACEHOLDERS = frozenset(
    {
        "SIGNATURE_DIRECTOR",
        "SIGNATURE_HEAD",
        "SIGNATURE_DEPT_HEAD",
        "SIGNATURE_SUPERVISOR",
        "SIGNATURE_1",
        "SIGNATURE_2",
    }
)


class DocgenError(Exception):
    pass


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_data(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    elif path.suffix.lower() == ".json":
        data = json.loads(raw)
    else:
        raise DocgenError(f"Формат данных не поддерживается: {path.suffix}")
    if not isinstance(data, dict):
        raise DocgenError("Корень файла данных должен быть объектом (dict)")
    return data


def _normalize_tag_name(tag: str) -> str:
    return tag.replace("-", "_")


def _prepare_render_template(template_path: Path, work_dir: Path) -> Path:
    """Копия шаблона: дефисы в {{SECTION_...}} заменяются на _, иначе Jinja ломается."""
    import io
    import shutil
    import zipfile

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


def _scan_template_placeholders(template_path: Path) -> set[str]:
    """Извлекает {{TAG}} из docx (zip+xml) без полного рендера."""
    import zipfile

    found: set[str] = set()
    with zipfile.ZipFile(template_path) as zf:
        for name in zf.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            for raw in _PLACEHOLDER_RE.findall(text):
                tag = _normalize_tag_name(raw.strip())
                if tag and " " not in tag and "{" not in tag:
                    found.add(tag)
    return found


def _resolve_path(base: Path, value: str | None) -> Path | None:
    if not value or not str(value).strip():
        return None
    p = Path(value)
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def _build_context(
    data: dict[str, Any],
    *,
    data_file: Path,
    template_tags: set[str],
) -> tuple[dict[str, Any], Any, Any]:
    try:
        from docxtpl import DocxTemplate, InlineImage
        from docx.shared import Mm
    except ImportError as exc:
        raise DocgenError(
            "Установите docxtpl: pip install docxtpl"
        ) from exc

    project_root = _PROJECT_ROOT
    placeholders: dict[str, str] = dict(data.get("placeholders") or {})
    signatures: dict[str, Any] = dict(data.get("signatures") or {})
    defaults: dict[str, str] = dict(data.get("defaults") or {})
    required: list[str] = list(data.get("required_placeholders") or [])

    # required = явный список или все теги из шаблона
    tags_to_fill = set(required) if required else template_tags
    missing_in_data: list[str] = []

    context: dict[str, Any] = {}

    for tag in sorted(tags_to_fill):
        if tag in SIGNATURE_PLACEHOLDERS:
            spec = signatures.get(tag)
            if spec is None:
                if tag in template_tags:
                    cfg = {"required": tag in required}
                else:
                    continue
            else:
                cfg = spec if isinstance(spec, dict) else {"png_path": spec}

            required_sig = bool(cfg.get("required", tag in required))
            png = _resolve_path(project_root, cfg.get("png_path"))
            if png is None or not png.is_file():
                if required_sig:
                    raise DocgenError(
                        f"Подпись {tag}: файл не найден "
                        f"({cfg.get('png_path')!r}). Укажите png_path в data.signatures."
                    )
                context[tag] = defaults.get(tag, "")
                continue

            width_mm = float(cfg.get("width_mm", 34))
            # InlineImage создаётся после загрузки шаблона — отложим
            context[tag] = ("__IMAGE__", str(png), width_mm)
            continue

        if tag in TEXT_PLACEHOLDERS or tag in placeholders or tag in defaults:
            value = placeholders.get(tag, defaults.get(tag, ""))
            if tag in required and not str(value).strip():
                missing_in_data.append(tag)
            context[tag] = str(value)
            continue

        if tag in template_tags:
            value = placeholders.get(tag, defaults.get(tag, ""))
            if tag in required and not str(value).strip():
                missing_in_data.append(tag)
            context[tag] = str(value)

    for tag in sorted(template_tags):
        if tag in context:
            continue
        if tag.startswith("SECTION_"):
            context[tag] = str(placeholders.get(tag, defaults.get(tag, "")))
            continue
        if tag in placeholders or tag in defaults:
            context[tag] = str(placeholders.get(tag, defaults.get(tag, "")))

    if missing_in_data:
        raise DocgenError(
            "В тестовых данных нет обязательных полей: "
            + ", ".join(missing_in_data)
        )

    unused = template_tags - set(context.keys())
    # Теги в шаблоне без данных — ошибка (не угадываем)
    orphan_tags = [
        t
        for t in unused
        if t not in defaults
        and t not in signatures
        and t not in placeholders
        and not t.startswith("SECTION_")
    ]
    if orphan_tags and data.get("strict", True):
        raise DocgenError(
            "В шаблоне есть плейсхолдеры без данных: "
            + ", ".join(sorted(orphan_tags))
            + ". Добавьте их в placeholders/signatures или defaults."
        )

    return context, InlineImage, Mm


def fill_template(
    *,
    template_path: Path,
    data_path: Path,
    output_dir: Path,
    output_name: str | None = None,
) -> Path:
    from docxtpl import DocxTemplate

    if not template_path.is_file():
        raise DocgenError(f"Шаблон не найден: {template_path}")

    data = _load_data(data_path)
    render_template = _prepare_render_template(template_path, output_dir / ".render_cache")
    template_tags = _scan_template_placeholders(render_template)
    if not template_tags:
        raise DocgenError(
            "В шаблоне не найдено тегов {{TAG}}. "
            "Добавьте плейсхолдеры в Word и повторите."
        )

    context, InlineImage, Mm = _build_context(
        data,
        data_file=data_path,
        template_tags=template_tags,
    )

    tpl = DocxTemplate(str(render_template))
    render_ctx: dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, tuple) and value[0] == "__IMAGE__":
            _, png_path, width_mm = value
            render_ctx[key] = InlineImage(tpl, png_path, width=Mm(width_mm))
        else:
            render_ctx[key] = value

    tpl.render(render_ctx)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_name = output_name or data.get("output_filename") or f"{template_path.stem}_filled.docx"
    out_path = output_dir / out_name
    if out_path.exists():
        out_path.unlink()
    tpl.save(str(out_path))
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Заполнение DOCX-шаблона из YAML/JSON")
    parser.add_argument("--template", "-t", required=True, type=Path, help="Путь к .docx шаблону")
    parser.add_argument("--data", "-d", required=True, type=Path, help="YAML/JSON с данными")
    parser.add_argument(
        "--out",
        "-o",
        default=Path("output"),
        type=Path,
        help="Каталог для результата (по умолчанию output/)",
    )
    parser.add_argument("--output-name", help="Имя выходного файла")
    args = parser.parse_args(argv)

    try:
        result = fill_template(
            template_path=args.template,
            data_path=args.data,
            output_dir=args.out,
            output_name=args.output_name,
        )
    except DocgenError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
