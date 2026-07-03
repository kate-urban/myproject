"""Тесты сообщений привязки документов."""

from app.utils.link_messages import format_link_reason


def test_discipline_not_in_plan_message() -> None:
    msg = format_link_reason("discipline_not_in_plan", discipline_code="Б1.О.13")
    assert "Б1.О.13" in msg
    assert "учебном плане" in msg
