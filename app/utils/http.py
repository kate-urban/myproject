"""HTTP helpers."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


def attachment_disposition(filename: str) -> dict[str, str]:
    """Build Content-Disposition safe for non-ASCII filenames (RFC 5987)."""
    try:
        filename.encode("latin-1")
        return {"Content-Disposition": f'attachment; filename="{filename}"'}
    except UnicodeEncodeError:
        suffix = Path(filename).suffix or ""
        ascii_name = f"download{suffix}"
        quoted = quote(filename, safe="")
        return {
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
            )
        }
