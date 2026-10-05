"""Calisma dosyalarinin yeri (ai_rules/10: Windows TEMP kullanilmaz).

Kaynaktan calisirken her sey proje icindeki `.tmp/` altindadir (git'e girmez):
  .tmp/apply/     Uygula isinin betik + sonuc dosyalari
  .tmp/test/      test ciktilari (PNG vb.)
  .tmp/shots/     gelistirici ekran goruntuleri
Paketlenmis (PyInstaller) uygulamada proje klasoru yoktur: %LOCALAPPDATA%\\networkPlus
(Linux/macOS: ~/.cache/networkplus). AppImage'da kaynak agaci salt okunur baglama
noktasindadir; o da ~/.cache/networkplus kullanir. NETWORKPLUS_WORKDIR ile degistirilebilir.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def work_root() -> Path:
    override = os.environ.get("NETWORKPLUS_WORKDIR")
    if override:
        root = Path(override)
    elif (not getattr(sys, "frozen", False) and not os.environ.get("APPIMAGE")
          and (PROJECT_ROOT / "main.py").exists()):
        root = PROJECT_ROOT / ".tmp"
    elif sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "networkPlus"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "networkplus"
    root.mkdir(parents=True, exist_ok=True)
    return root


def work_dir(kind: str) -> Path:
    path = work_root() / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_job_dir(prefix: str = "apply-") -> Path:
    """Uygula isi icin benzersiz klasor (.tmp/apply/apply-XXXX)."""
    return Path(tempfile.mkdtemp(prefix=prefix, dir=work_dir("apply")))
