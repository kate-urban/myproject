"""Дерево учебных планов по структуре папки «УЧЕБНЫЕ ПЛАНЫ»."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import plans_auto_import, plans_delete_after_import, plans_sync_batch_size
from app.models import Direction, PlanDiscipline, Profile, StudyPlan
from app.services.importers import StudyPlanImporter

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PLANS_DIR = _PROJECT_ROOT / "УЧЕБНЫЕ ПЛАНЫ"
_MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "direction_institute_map.yaml"

PLAN_EXTENSIONS = {".plx", ".xlsx", ".xlsm"}


@dataclass
class FolderFile:
    name: str
    relative_path: str


@dataclass
class NavPlan:
    id: str
    direction_code: str
    direction_name: str
    profile_name: str
    source_file: str
    form: str
    year: int | None
    disciplines_count: int
    folder_path: str | None = None


@dataclass
class NavNode:
    id: str
    name: str
    node_type: str = "folder"
    children: list[NavNode] = field(default_factory=list)
    plans: list[NavPlan] = field(default_factory=list)
    files: list[FolderFile] = field(default_factory=list)


def plans_root() -> Path:
    raw = os.getenv("PLANS_FOLDER", str(_DEFAULT_PLANS_DIR))
    return Path(raw).resolve()


def _load_mapping() -> dict:
    if not _MAP_PATH.is_file():
        return {"by_direction_prefix": {}, "form_folders": {}, "zaochnaya_bachelor_extra": ""}
    with _MAP_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _degree_folder(direction_code: str) -> str:
    parts = direction_code.split(".")
    if len(parts) >= 2:
        level = parts[1]
        if level == "04":
            return "Магистры"
        if level == "03":
            return "Бакалавры"
        if level == "06":
            return "Аспиранты"
    return "Бакалавры"


def _institute_for(direction_code: str, mapping: dict) -> str | None:
    prefixes: dict = mapping.get("by_direction_prefix") or {}
    for size in (7, 5, 4):
        prefix = direction_code[:size]
        if prefix in prefixes:
            return prefixes[prefix]
    return None


def _heuristic_folder_segments(
    *,
    form: str,
    direction_code: str,
    year: int | None,
    mapping: dict,
) -> list[str]:
    form_folders: dict = mapping.get("form_folders") or {}
    form_name = form_folders.get(form)
    if not form_name:
        return []

    degree = _degree_folder(direction_code)
    institute = _institute_for(direction_code, mapping)
    segments = [form_name, degree]

    if form == "zaochnaya" and degree == "Бакалавры":
        extra = mapping.get("zaochnaya_bachelor_extra")
        if extra:
            segments.append(str(extra))

    if institute:
        segments.append(institute)
    if year is not None:
        segments.append(str(year))
    return segments


@dataclass
class FolderSyncResult:
    imported: int = 0
    deleted: int = 0
    skipped: int = 0
    pending: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def _relative_folder_path(relative_path: str) -> str | None:
    parent = Path(relative_path).parent.as_posix()
    return None if parent == "." else parent


def _collect_files(node: NavNode) -> list[FolderFile]:
    items = list(node.files)
    for child in node.children:
        items.extend(_collect_files(child))
    return items


def _imported_file_keys(plans: list[StudyPlan]) -> set[tuple[str | None, str]]:
    return {
        (getattr(plan, "folder_path", None), plan.source_file.lower())
        for plan in plans
    }


async def _imported_file_keys_from_db(db: AsyncSession) -> set[tuple[str | None, str]]:
    result = await db.execute(select(StudyPlan.folder_path, StudyPlan.source_file))
    return {(row[0], row[1].lower()) for row in result.all()}


def _file_key(relative_path: str, filename: str | None = None) -> tuple[str | None, str]:
    name = (filename or Path(relative_path).name).lower()
    return _relative_folder_path(relative_path), name


def _file_mtime(root: Path, relative_path: str) -> float:
    try:
        return (root / relative_path).stat().st_mtime
    except OSError:
        return 0.0


def _sort_files_newest_first(root: Path, files: list[FolderFile]) -> list[FolderFile]:
    return sorted(files, key=lambda item: _file_mtime(root, item.relative_path), reverse=True)


def _strip_imported_files(node: NavNode, imported: set[tuple[str | None, str]]) -> None:
    folder_key = None if node.id == "." else node.id
    node.files = [
        item
        for item in node.files
        if (folder_key, item.name.lower()) not in imported
    ]
    for child in node.children:
        _strip_imported_files(child, imported)


async def import_plan_from_relative_path(
    db: AsyncSession,
    relative_path: str,
    *,
    delete_after: bool | None = None,
) -> StudyPlan:
    """Импорт файла из папки УП с опциональным удалением после успешной загрузки в БД."""
    if delete_after is None:
        delete_after = plans_delete_after_import()

    file_path = resolve_plan_file_path(relative_path)
    folder_path = _relative_folder_path(relative_path)
    importer = StudyPlanImporter()
    plan = await importer.import_file(path=file_path, db=db, folder_path=folder_path)
    if delete_after and file_path.is_file():
        file_path.unlink()
    return plan


def _cleanup_imported_file(
    root_path: Path,
    relative_path: str,
    *,
    delete_after: bool,
) -> bool:
    if not delete_after:
        return False
    try:
        file_path = resolve_plan_file_path(relative_path)
    except ValueError:
        return False
    if file_path.is_file():
        file_path.unlink()
        return True
    return False


async def sync_folder_plans(db: AsyncSession) -> FolderSyncResult:
    """Импортировать новые файлы УП из папки «УЧЕБНЫЕ ПЛАНЫ» (сначала самые свежие)."""
    result = FolderSyncResult()
    if not plans_auto_import():
        return result

    root_path = plans_root()
    if not root_path.is_dir():
        return result

    imported_keys = await _imported_file_keys_from_db(db)
    tree = _scan_folder(root_path, root_path)
    all_files = _sort_files_newest_first(root_path, _collect_files(tree))
    delete_after = plans_delete_after_import()
    batch_limit = plans_sync_batch_size()

    pending: list[FolderFile] = []
    for folder_file in all_files:
        key = _file_key(folder_file.relative_path, folder_file.name)
        if key in imported_keys:
            result.skipped += 1
            if _cleanup_imported_file(
                root_path, folder_file.relative_path, delete_after=delete_after
            ):
                result.deleted += 1
            continue
        pending.append(folder_file)

    result.pending = len(pending)
    for folder_file in pending[:batch_limit]:
        try:
            file_path = resolve_plan_file_path(folder_file.relative_path)
            await import_plan_from_relative_path(
                db, folder_file.relative_path, delete_after=delete_after
            )
            result.imported += 1
            if delete_after and not file_path.is_file():
                result.deleted += 1
        except Exception as exc:
            result.errors.append(
                {"file": folder_file.relative_path, "error": str(exc)}
            )
    result.pending = max(0, len(pending) - result.imported)
    return result


def _scan_folder(path: Path, root: Path) -> NavNode:
    rel = path.relative_to(root).as_posix()
    node_id = rel or "."
    node = NavNode(id=node_id, name=path.name if rel else root.name)

    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return node

    for entry in entries:
        if entry.is_dir():
            node.children.append(_scan_folder(entry, root))
        elif entry.suffix.lower() in PLAN_EXTENSIONS:
            node.files.append(
                FolderFile(
                    name=entry.name,
                    relative_path=entry.relative_to(root).as_posix(),
                )
            )
    return node


def _index_nodes(node: NavNode) -> dict[str, NavNode]:
    result = {node.id: node}
    for child in node.children:
        result.update(_index_nodes(child))
    return result


def _index_files(node: NavNode) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in node.files:
        result[item.name.lower()] = node.id
    for child in node.children:
        result.update(_index_files(child))
    return result


def _find_node_by_segments(index: dict[str, NavNode], segments: list[str]) -> NavNode | None:
    if not segments:
        return None
    best: NavNode | None = None
    best_len = 0
    for node in index.values():
        parts = [] if node.id == "." else node.id.split("/")
        if len(parts) < len(segments):
            continue
        if parts[: len(segments)] == segments:
            if len(parts) > best_len:
                best = node
                best_len = len(parts)
    if best:
        return best
    for length in range(len(segments), 0, -1):
        prefix = "/".join(segments[:length])
        if prefix in index:
            return index[prefix]
    return None


def _attach_plan(node: NavNode, plan: NavPlan) -> None:
    if any(existing.id == plan.id for existing in node.plans):
        return
    node.plans.append(plan)


async def build_plans_navigation_tree(
    db: AsyncSession,
    *,
    disciplines_count: dict | None = None,
) -> dict:
    sync_result = await sync_folder_plans(db)

    root_path = plans_root()
    mapping = _load_mapping()

    if root_path.is_dir():
        tree = _scan_folder(root_path, root_path)
    else:
        tree = NavNode(id=".", name=root_path.name, node_type="missing")

    node_index = _index_nodes(tree)
    file_index = _index_files(tree)

    result = await db.execute(
        select(StudyPlan)
        .options(
            selectinload(StudyPlan.profile).selectinload(Profile.direction),
        )
        .order_by(StudyPlan.imported_at.desc())
    )
    plans = list(result.scalars().all())

    _strip_imported_files(tree, _imported_file_keys(plans))

    if disciplines_count is None:
        disciplines_count = {}
        count_result = await db.execute(
            select(PlanDiscipline.study_plan_id, PlanDiscipline.id)
        )
        for plan_id, _ in count_result.all():
            key = str(plan_id)
            disciplines_count[key] = disciplines_count.get(key, 0) + 1

    orphan = NavNode(id="__orphan__", name="Прочие (не в структуре папки)", node_type="orphan")

    for plan in plans:
        profile: Profile = plan.profile
        direction: Direction = profile.direction
        nav_plan = NavPlan(
            id=str(plan.id),
            direction_code=direction.code,
            direction_name=direction.name,
            profile_name=profile.name,
            source_file=plan.source_file,
            form=plan.form,
            year=plan.year,
            disciplines_count=disciplines_count.get(str(plan.id), 0),
            folder_path=getattr(plan, "folder_path", None),
        )

        target: NavNode | None = None
        if nav_plan.folder_path and nav_plan.folder_path in node_index:
            target = node_index[nav_plan.folder_path]
        elif nav_plan.source_file.lower() in file_index:
            target = node_index.get(file_index[nav_plan.source_file.lower()])
        else:
            for rel_path in file_index.values():
                node = node_index.get(rel_path)
                if node and any(
                    f.name.lower() == nav_plan.source_file.lower() for f in node.files
                ):
                    target = node
                    break

        if target is None:
            segments = _heuristic_folder_segments(
                form=plan.form,
                direction_code=direction.code,
                year=plan.year,
                mapping=mapping,
            )
            target = _find_node_by_segments(node_index, segments)

        if target is None:
            _attach_plan(orphan, nav_plan)
        else:
            _attach_plan(target, nav_plan)

    if orphan.plans:
        tree.children.append(orphan)

    payload: dict = {
        "root": root_path.name,
        "root_exists": root_path.is_dir(),
        "tree": _node_to_dict(tree),
    }
    if (
        sync_result.imported
        or sync_result.deleted
        or sync_result.pending
        or sync_result.errors
    ):
        payload["sync"] = {
            "imported": sync_result.imported,
            "deleted": sync_result.deleted,
            "skipped": sync_result.skipped,
            "pending": sync_result.pending,
            "errors": sync_result.errors,
            "auto_import": plans_auto_import(),
        }
    return payload


def _node_to_dict(node: NavNode) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "type": node.node_type,
        "plans": [
            {
                "id": p.id,
                "direction_code": p.direction_code,
                "direction_name": p.direction_name,
                "profile_name": p.profile_name,
                "source_file": p.source_file,
                "form": p.form,
                "year": p.year,
                "disciplines_count": p.disciplines_count,
                "folder_path": p.folder_path,
            }
            for p in sorted(
                node.plans,
                key=lambda x: (x.year or 0, x.direction_code, x.profile_name),
                reverse=True,
            )
        ],
        "files": [{"name": f.name, "relative_path": f.relative_path} for f in node.files],
        "children": [_node_to_dict(child) for child in node.children],
    }


def resolve_plan_file_path(relative_path: str) -> Path:
    root = plans_root()
    target = (root / relative_path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("Недопустимый путь к файлу")
    if not target.is_file():
        raise ValueError("Файл не найден")
    if target.suffix.lower() not in PLAN_EXTENSIONS:
        raise ValueError("Поддерживаются только .plx, .xlsx, .xlsm")
    return target
