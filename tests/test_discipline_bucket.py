"""Тесты классификации дисциплин УП."""

from app.utils.discipline_bucket import classify_discipline_bucket


def test_practice_by_object_type() -> None:
    assert (
        classify_discipline_bucket(code="Б1.О.01", name="Практика", object_type="3")
        == "practices"
    )


def test_practice_by_code_marker() -> None:
    assert classify_discipline_bucket(code="Б2.О.01(П)", name="Уч. практика") == "practices"


def test_gia_by_code() -> None:
    assert classify_discipline_bucket(code="Б3.В.01", name="ВКР") == "gia"


def test_regular_discipline() -> None:
    assert classify_discipline_bucket(code="Б1.О.01.07", name="Экология") == "disciplines"
