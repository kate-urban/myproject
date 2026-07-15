"""Фикстуры E2E: живой сервер для Playwright."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, *, attempts: int = 60) -> None:
    probe = f"{base_url}/"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(probe, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    raise RuntimeError(f"E2E server did not respond at {probe}")


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    pytest.importorskip("playwright")
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")

    port = _free_port()
    env = os.environ.copy()
    env["AUTH_ENABLED"] = "false"
    env["PLANS_AUTO_IMPORT"] = "false"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url)
    except RuntimeError:
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        proc.kill()
        pytest.fail(f"E2E server failed to start.\n{stderr}")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
