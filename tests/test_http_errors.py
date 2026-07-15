from app.utils.http_errors import public_error_message


def test_public_error_message_hides_internals() -> None:
    msg = public_error_message(RuntimeError("secret db password"), log=False)
    assert msg == "Внутренняя ошибка сервера"
    assert "password" not in msg
