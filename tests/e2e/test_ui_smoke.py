"""Playwright smoke-тесты основных страниц UI."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.playwright]


def _assert_page_loaded(page, url: str) -> None:
    response = page.goto(url)
    assert response is not None and response.ok
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("header.app-header", state="attached", timeout=15_000)


def test_workspace_shell(page, e2e_base_url: str) -> None:
    _assert_page_loaded(page, f"{e2e_base_url}/")
    assert "Syllabus" in page.title()
    page.wait_for_selector("#navTree", state="attached", timeout=15_000)


def test_validation_shell(page, e2e_base_url: str) -> None:
    _assert_page_loaded(page, f"{e2e_base_url}/validation")
    page.wait_for_selector("#appRibbon", state="attached", timeout=15_000)
    assert page.locator("script[src*='validation_page.js']").count() >= 1


def test_reference_shell(page, e2e_base_url: str) -> None:
    _assert_page_loaded(page, f"{e2e_base_url}/reference")
    page.wait_for_selector(".layout-ref", state="attached", timeout=15_000)
    assert "справоч" in page.title().lower()


def test_editor_shell(page, e2e_base_url: str) -> None:
    _assert_page_loaded(page, f"{e2e_base_url}/editor")
    page.wait_for_selector("#app", state="attached", timeout=15_000)
    assert "редактор" in page.title().lower()
