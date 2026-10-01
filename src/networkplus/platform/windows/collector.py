"""Windows toplayicisi: ps/snapshot.ps1'i calistirir (SALT OKUNUR, yetki istemez)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..base import Collector, CollectError
from .normalize import normalize

SCRIPT = Path(__file__).with_name("ps") / "snapshot.ps1"
TIMEOUT_S = 60


class WindowsCollector(Collector):
    name = "windows"

    def collect_raw(self) -> dict:
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise CollectError("powershell.exe bulunamadi") from exc
        except subprocess.TimeoutExpired as exc:
            raise CollectError(f"Ag anlik goruntusu {TIMEOUT_S} sn icinde tamamlanmadi") from exc
        out = proc.stdout.decode("utf-8-sig", errors="replace").strip()
        if proc.returncode != 0 or not out:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise CollectError(f"snapshot.ps1 basarisiz (kod {proc.returncode}): {err[:500]}")
        try:
            return json.loads(out.splitlines()[-1])
        except ValueError as exc:
            raise CollectError(f"snapshot.ps1 gecersiz JSON dondurdu: {exc}") from exc

    def normalize(self, raw: dict) -> dict:
        return normalize(raw)
