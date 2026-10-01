"""Restart the local API if it stops. No network service and no paid provider."""

from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
BACKEND = ROOT / "backend"
HEALTH = "http://127.0.0.1:8000/config/thresholds"


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=4) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> None:
    process: subprocess.Popen[bytes] | None = None
    while True:
        if not healthy():
            if process is None or process.poll() is not None:
                process = subprocess.Popen(
                    [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                    cwd=BACKEND,
                )
        time.sleep(20)


if __name__ == "__main__":
    main()
