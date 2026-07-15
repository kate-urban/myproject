"""Tests for auto-sync of user-edited layout templates."""

from __future__ import annotations

import time
from pathlib import Path

from app.services.editable_template_sync import sync_user_template


def test_sync_user_template_skips_when_active_is_newer(tmp_path, monkeypatch) -> None:
    tagged = tmp_path / "templates" / "tagged"
    editable = tmp_path / "templates" / "editable"
    layout = tmp_path / "Layout"
    tagged.mkdir(parents=True)
    editable.mkdir(parents=True)
    layout.mkdir(parents=True)

    source = tagged / "РПД_FGOS3_макет_с_тегами.docx"
    active = tmp_path / "templates" / "layout_Maket_RPd_FGOS_3.docx"
    layout_dest = layout / "Maket_RPd_FGOS_3.docx"
    canon = tagged / "Maket_RPd_FGOS_3_tagged.docx"

    source.write_bytes(b"old-source")
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_bytes(b"new-active")
    layout_dest.write_bytes(b"new-layout")
    canon.write_bytes(b"new-canon")

    time.sleep(0.02)

    monkeypatch.setattr("app.services.editable_template_sync._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "app.services.editable_template_sync.RPD_TAGGED_USER",
        source,
    )
    monkeypatch.setattr(
        "app.services.editable_template_sync.RPD_EDITABLE",
        editable / "РПД_FGOS3_макет_с_тегами.docx",
    )
    monkeypatch.setattr(
        "app.services.editable_template_sync.RPD_TAGGED_CANON",
        canon,
    )
    monkeypatch.setattr("app.services.editable_template_sync.ACTIVE_RPD", active)
    monkeypatch.setattr("app.services.editable_template_sync.LAYOUT_RPD", layout_dest)

    assert sync_user_template(rpd=True) == []
    assert active.read_bytes() == b"new-active"


def test_sync_user_template_updates_when_source_is_newer(tmp_path, monkeypatch) -> None:
    tagged = tmp_path / "templates" / "tagged"
    editable = tmp_path / "templates" / "editable"
    layout = tmp_path / "Layout"
    tagged.mkdir(parents=True)
    editable.mkdir(parents=True)
    layout.mkdir(parents=True)

    source = tagged / "РПД_FGOS3_макет_с_тегами.docx"
    active = tmp_path / "templates" / "layout_Maket_RPd_FGOS_3.docx"
    layout_dest = layout / "Maket_RPd_FGOS_3.docx"
    canon = tagged / "Maket_RPd_FGOS_3_tagged.docx"

    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_bytes(b"old-active")
    layout_dest.write_bytes(b"old-layout")
    canon.write_bytes(b"old-canon")

    time.sleep(0.02)
    source.write_bytes(b"fresh-source")

    monkeypatch.setattr("app.services.editable_template_sync._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.services.editable_template_sync.RPD_TAGGED_USER", source)
    monkeypatch.setattr(
        "app.services.editable_template_sync.RPD_EDITABLE",
        editable / "РПД_FGOS3_макет_с_тегами.docx",
    )
    monkeypatch.setattr("app.services.editable_template_sync.RPD_TAGGED_CANON", canon)
    monkeypatch.setattr("app.services.editable_template_sync.ACTIVE_RPD", active)
    monkeypatch.setattr("app.services.editable_template_sync.LAYOUT_RPD", layout_dest)

    assert sync_user_template(rpd=True) == ["rpd"]
    assert active.read_bytes() == b"fresh-source"
    assert layout_dest.read_bytes() == b"fresh-source"
