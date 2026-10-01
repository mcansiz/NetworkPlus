"""Kayitli snapshot JSON'unu yukler (test, demo, baska makineden alinan goruntu).

Dosya normalize ("format": "normalized") ya da ham platform ciktisi olabilir;
ham ise platformun normalizasyonu uygulanir.
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import Collector, CollectError


def normalize_any(data: dict) -> dict:
    if data.get("format") == "normalized":
        return data
    platform = data.get("platform")
    if platform == "windows":
        from .windows.normalize import normalize
    elif platform == "linux":
        from .linux.normalize import normalize
    else:
        raise CollectError(f"Bilinmeyen snapshot platformu: {platform!r}")
    return normalize(data)


class FileCollector(Collector):
    name = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def collect_raw(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise CollectError(f"{self.path}: {exc}") from exc

    def normalize(self, raw: dict) -> dict:
        return normalize_any(raw)
