"""Синхронизация пользовательского макета РПД/ФОС перед экспортом."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

RPD_TAGGED_USER = _PROJECT_ROOT / "templates" / "tagged" / "РПД_FGOS3_макет_с_тегами.docx"
RPD_EDITABLE = _PROJECT_ROOT / "templates" / "editable" / "РПД_FGOS3_макет_с_тегами.docx"
RPD_TAGGED_CANON = _PROJECT_ROOT / "templates" / "tagged" / "Maket_RPd_FGOS_3_tagged.docx"

FOS_TAGGED_USER = _PROJECT_ROOT / "templates" / "tagged" / "ФОС_FGOS3_макет_с_тегами.docx"
FOS_EDITABLE = _PROJECT_ROOT / "templates" / "editable" / "ФОС_FGOS3_макет_с_тегами.docx"
FOS_TAGGED_CANON = _PROJECT_ROOT / "templates" / "tagged" / "Maket_FOSd_FGOS_3_tagged.docx"

LAYOUT_RPD = _PROJECT_ROOT / "Layout" / "Maket_RPd_FGOS_3.docx"
LAYOUT_FOS = _PROJECT_ROOT / "Layout" / "Maket_FOSd_FGOS_3.docx"
ACTIVE_RPD = _PROJECT_ROOT / "templates" / "layout_Maket_RPd_FGOS_3.docx"
ACTIVE_FOS = _PROJECT_ROOT / "templates" / "layout_Maket_FOSd_FGOS_3.docx"


def _pick_source(candidates: tuple[Path, ...]) -> Path | None:
    for path in candidates:
        if path.is_file() and not path.name.startswith("~$"):
            return path
    return None


def _needs_sync(source: Path, *destinations: Path) -> bool:
    try:
        source_mtime = source.stat().st_mtime
    except OSError:
        return False
    for dest in destinations:
        if not dest.is_file():
            return True
        try:
            if source_mtime > dest.stat().st_mtime:
                return True
        except OSError:
            return True
    return False


def _copy_template(source: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, dest)
        return True
    except OSError as exc:
        logger.warning("Не удалось обновить макет %s: %s", dest.name, exc)
        return False


def sync_user_template(*, rpd: bool = False, fos: bool = False, force: bool = False) -> list[str]:
    """
    Копирует пользовательский макет в Layout/ и templates/layout_*.docx.

    По умолчанию — только если исходник новее активного файла.
    Возвращает список обновлённых типов («rpd», «fos»).
    """
    updated: list[str] = []

    if rpd:
        source = _pick_source((RPD_TAGGED_USER, RPD_EDITABLE, RPD_TAGGED_CANON))
        if source and (force or _needs_sync(source, ACTIVE_RPD, LAYOUT_RPD)):
            ok = all(
                _copy_template(source, dest)
                for dest in (LAYOUT_RPD, ACTIVE_RPD, RPD_TAGGED_CANON)
            )
            if ok:
                updated.append("rpd")
                logger.info("Макет РПД обновлён из %s", source.name)

    if fos:
        source = _pick_source((FOS_TAGGED_USER, FOS_EDITABLE, FOS_TAGGED_CANON))
        if source and (force or _needs_sync(source, ACTIVE_FOS, LAYOUT_FOS)):
            ok = all(
                _copy_template(source, dest)
                for dest in (LAYOUT_FOS, ACTIVE_FOS, FOS_TAGGED_CANON)
            )
            if ok:
                updated.append("fos")
                logger.info("Макет ФОС обновлён из %s", source.name)

    return updated


def sync_user_template_for_export(doc_kind: str, *, force: bool = False) -> list[str]:
    """Обновить макет перед экспортом по типу документа."""
    if doc_kind == "rpd":
        return sync_user_template(rpd=True, force=force)
    if doc_kind == "fos":
        return sync_user_template(fos=True, force=force)
    return []
