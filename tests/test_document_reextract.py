from app.services.document_reextract import build_docx_bytes_from_sections


def test_build_docx_bytes_from_sections():
    data = build_docx_bytes_from_sections([
        ("1.3 Объем дисциплины", "<table><tr><td>Часы</td><td>100</td></tr></table>"),
        ("3.5 Самостоятельная работа", "<p>50</p>"),
    ])
    assert isinstance(data, bytes)
    assert len(data) > 1000
    assert data[:2] == b"PK"
