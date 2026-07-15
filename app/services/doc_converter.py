"""Конвертация .doc → .docx для загрузки РПД/ФОС (Word или LibreOffice)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

WD_FORMAT_XML_DOCUMENT = 16


def _libreoffice_paths() -> list[Path]:
    env = os.getenv("LIBREOFFICE_PATH", "").strip()
    paths: list[Path] = []
    if env:
        paths.append(Path(env))
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        paths.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    return paths


def _find_libreoffice() -> Path | None:
    for candidate in _libreoffice_paths():
        if candidate.is_file():
            return candidate
    found = shutil.which("soffice")
    return Path(found) if found else None


def _convert_with_libreoffice(source: Path, target_dir: Path) -> Path:
    soffice = _find_libreoffice()
    if soffice is None:
        raise RuntimeError(
            "LibreOffice не найден. Установите LibreOffice или Microsoft Word, "
            "либо задайте LIBREOFFICE_PATH."
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(soffice),
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(target_dir),
        str(source),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"LibreOffice: {detail or 'ошибка конвертации'}")
    converted = target_dir / f"{source.stem}.docx"
    if not converted.is_file():
        raise RuntimeError("LibreOffice не создал .docx")
    return converted


def _convert_with_word_com(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    ps = rf"""
$ErrorActionPreference = 'Stop'
$src = '{source.as_posix().replace("'", "''")}'
$dst = '{target.as_posix().replace("'", "''")}'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {{
  $doc = $word.Documents.Open($src)
  $format = [ref]16
  $doc.SaveAs([ref]$dst, $format)
  $doc.Close()
}} finally {{
  $word.Quit()
  [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}}
"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0 or not target.is_file():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            detail
            or "Microsoft Word не смог конвертировать .doc. Проверьте, что Word установлен."
        )


def convert_doc_file_to_docx(source: Path, target: Path) -> Path:
    """Сконвертировать один .doc в .docx."""
    if source.suffix.lower() != ".doc":
        raise ValueError("Ожидается файл .doc")
    if _find_libreoffice() is not None:
        converted = _convert_with_libreoffice(source, target.parent)
        if converted.resolve() != target.resolve():
            shutil.move(str(converted), str(target))
        return target
    if os.name == "nt":
        _convert_with_word_com(source, target)
        return target
    raise RuntimeError(
        "Конвертация .doc недоступна: установите LibreOffice или используйте Windows с Word."
    )


def convert_doc_bytes_to_docx(content: bytes, filename: str = "upload.doc") -> tuple[bytes, str]:
    """Сконвертировать содержимое .doc в .docx (bytes, новое имя файла)."""
    suffix = Path(filename).suffix.lower()
    if suffix != ".doc":
        raise ValueError("Ожидается .doc")
    out_name = f"{Path(filename).stem}.docx"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / Path(filename).name
        dst = Path(tmp) / out_name
        src.write_bytes(content)
        convert_doc_file_to_docx(src, dst)
        return dst.read_bytes(), out_name


class DocBatchConverter:
    """Пакетная конвертация .doc через один экземпляр Word (быстрее для папки)."""

    def __init__(self) -> None:
        self._word = None
        self._use_libreoffice = _find_libreoffice() is not None
        self._tmp_root: Path | None = None

    def __enter__(self) -> DocBatchConverter:
        if not self._use_libreoffice and os.name == "nt":
            try:
                import win32com.client  # type: ignore

                self._word = win32com.client.Dispatch("Word.Application")
                self._word.Visible = False
            except Exception:
                self._word = None
        if self._tmp_root is None:
            self._tmp_root = Path(tempfile.mkdtemp(prefix="doc_batch_"))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._word is not None:
            self._word.Quit()
            self._word = None
        if self._tmp_root and self._tmp_root.exists():
            shutil.rmtree(self._tmp_root, ignore_errors=True)
            self._tmp_root = None

    def to_docx_bytes(self, content: bytes, filename: str) -> tuple[bytes, str]:
        if Path(filename).suffix.lower() != ".doc":
            raise ValueError("Ожидается .doc")
        assert self._tmp_root is not None
        src = self._tmp_root / Path(filename).name
        dst = self._tmp_root / f"{Path(filename).stem}.docx"
        src.write_bytes(content)
        if self._word is not None:
            doc = self._word.Documents.Open(str(src))
            doc.SaveAs(str(dst), WD_FORMAT_XML_DOCUMENT)
            doc.Close()
        elif self._use_libreoffice:
            converted = _convert_with_libreoffice(src, self._tmp_root)
            if converted != dst:
                shutil.move(str(converted), str(dst))
        elif os.name == "nt":
            _convert_with_word_com(src, dst)
        else:
            raise RuntimeError("Конвертация .doc недоступна на этом сервере.")
        return dst.read_bytes(), dst.name


@contextmanager
def doc_batch_converter():
    converter = DocBatchConverter()
    with converter:
        yield converter
