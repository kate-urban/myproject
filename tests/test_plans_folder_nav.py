"""Тесты дерева папки «УЧЕБНЫЕ ПЛАНЫ»."""

from __future__ import annotations

from pathlib import Path

from app.services.plans_folder_nav import (
    _find_node_by_segments,
    _heuristic_folder_segments,
    _index_nodes,
    _prune_empty_nodes,
    _scan_folder,
    plans_root,
)


def test_plans_root_exists() -> None:
    root = plans_root()
    assert root.name == "УЧЕБНЫЕ ПЛАНЫ"
    assert root.is_dir()


def test_scan_has_top_level_forms() -> None:
    root = plans_root()
    tree = _scan_folder(root, root)
    names = {child.name for child in tree.children}
    assert "ОЧНОЕ ОБУЧЕНИЕ" in names
    assert "ЗАОЧНОЕ ОБУЧЕНИЕ" in names


def test_heuristic_path_for_design_master() -> None:
    mapping = {
        "form_folders": {"ochnaya": "ОЧНОЕ ОБУЧЕНИЕ"},
        "by_direction_prefix": {"54.04": "ИЛиП"},
        "zaochnaya_bachelor_extra": "Полное обучение ЗО",
    }
    segments = _heuristic_folder_segments(
        form="ochnaya",
        direction_code="54.04.01",
        year=2026,
        mapping=mapping,
    )
    assert segments == ["ОЧНОЕ ОБУЧЕНИЕ", "Магистры", "ИЛиП", "2026"]


def test_find_node_by_segments() -> None:
    root = plans_root()
    tree = _scan_folder(root, root)
    index = _index_nodes(tree)
    node = _find_node_by_segments(
        index,
        ["ОЧНОЕ ОБУЧЕНИЕ", "Магистры", "ИЛиП", "2026"],
    )
    assert node is not None
    assert node.name == "2026"


def test_scan_skips_net_nabora_placeholder(tmp_path: Path) -> None:
    year_dir = (
        tmp_path / "УЧЕБНЫЕ ПЛАНЫ" / "ОЧНОЕ ОБУЧЕНИЕ" / "Бакалавры" / "ИЛБиИ" / "2026"
    )
    (year_dir / "Нет набора").mkdir(parents=True)

    tree = _scan_folder(tmp_path / "УЧЕБНЫЕ ПЛАНЫ", tmp_path / "УЧЕБНЫЕ ПЛАНЫ")
    index = _index_nodes(tree)
    assert "ОЧНОЕ ОБУЧЕНИЕ/Бакалавры/ИЛБиИ/2026/Нет набора" not in index


def test_prune_empty_nodes_hides_scaffold_years(tmp_path: Path) -> None:
    root = tmp_path / "УЧЕБНЫЕ ПЛАНЫ"
    for year in ("2022", "2023", "2024"):
        (root / "ОЧНОЕ ОБУЧЕНИЕ" / "Бакалавры" / "ИЛАСиОД" / year).mkdir(
            parents=True
        )

    tree = _scan_folder(root, root)
    _prune_empty_nodes(tree)

    institute = _find_node_by_segments(
        _index_nodes(tree),
        ["ОЧНОЕ ОБУЧЕНИЕ", "Бакалавры", "ИЛАСиОД"],
    )
    assert institute is None
