"""Проверка загрузки direction_institute_map.yaml."""

from pathlib import Path

from app.services import plans_folder_nav as nav


def test_direction_institute_map_path_exists() -> None:
    assert nav._MAP_PATH.is_file(), f"missing map file: {nav._MAP_PATH}"


def test_direction_institute_map_loads_entries() -> None:
    mapping = nav._load_mapping()
    prefixes = mapping.get("by_direction_prefix") or {}
    assert prefixes, "by_direction_prefix should not be empty"
