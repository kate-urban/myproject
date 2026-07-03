"""Проверка экспорта через API (как в браузере)."""
import asyncio
import json
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SAMPLE = Path("samples/B1_O_01_07_Proektnaya_deyatelnost_k55.docx")
BASE = "http://localhost:8000/api/v1"


def http(method: str, url: str, data: bytes | None = None, headers: dict | None = None):
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=120) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def main() -> None:
    status, _, body = http("GET", f"{BASE}/templates/")
    print("templates status", status)
    if status != 200:
        print(body.decode("utf-8", errors="replace")[:500])
        return
    templates = json.loads(body.decode("utf-8"))
    template_id = next(t["id"] for t in templates if "РПД" in t["name"])
    print("template_id", template_id)

    boundary = uuid.uuid4().hex
    file_bytes = SAMPLE.read_bytes()
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{SAMPLE.name}"\r\n'
        f"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    ]
    payload = b"".join([parts[0].encode("utf-8"), file_bytes, f"\r\n--{boundary}--\r\n".encode("utf-8")])

    status, _, body = http(
        "POST",
        f"{BASE}/upload/",
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    print("upload status", status)
    if status != 200:
        print(body.decode("utf-8", errors="replace")[:500])
        return
    doc = json.loads(body.decode("utf-8"))
    doc_id = doc["id"]
    sections = doc["sections"]
    export_payload = json.dumps(
        {"sections": [{"id": s["id"], "content": s.get("content") or ""} for s in sections]}
    ).encode("utf-8")
    print("doc_id", doc_id, "sections", len(sections))

    status, headers, body = http(
        "POST",
        f"{BASE}/export/{doc_id}/?template_id={template_id}",
        data=export_payload,
        headers={"Content-Type": "application/json"},
    )
    print("export POST status", status)
    if status != 200:
        print("ERROR:", body.decode("utf-8", errors="replace")[:1000])
        return
    print("bytes", len(body), "injected", headers.get("X-Sections-Injected"))


if __name__ == "__main__":
    main()
