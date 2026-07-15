"""Тесты app.utils.text."""

from app.utils.text import DEFAULT_PLAIN_TEXT_LIMIT, html_to_plain_text, section_plain_text


def test_html_to_plain_text_full() -> None:
    html = "<p>УК-4.1</p><table><tr><td>УК-4.2</td></tr></table>"
    text = html_to_plain_text(html)
    assert "УК-4.1" in text
    assert "УК-4.2" in text


def test_section_plain_text_truncates() -> None:
    html = "<p>" + ("x" * 2000) + "</p>"
    text = section_plain_text(html)
    assert len(text) == DEFAULT_PLAIN_TEXT_LIMIT


def test_html_to_plain_text_custom_limit() -> None:
    assert html_to_plain_text("abcdef", limit=3) == "abc"
