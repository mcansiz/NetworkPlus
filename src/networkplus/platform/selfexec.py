"""Yardimci surecler (Linux uygulayici, DHCP sunucusu) nasil baslatilir.

Kaynaktan calisirken: `python <betik.py> ...`. PyInstaller tek dosya paketinde ayri Python ve
.py dosyasi YOKTUR; ayni exe gizli bir bayrakla o rolde calisir (`main.py` en basta dagitir,
Qt acilmadan). pkexec de exe'yi kok olarak bu bayrakla calistirir.

AppImage (ADR 0013): icerideki Python ve .py dosyalari kullanicinin FUSE baglama noktasindadir;
kok kullanici oraya ERISEMEZ ve uygulama kapaninca baglama kalkar. Bu yuzden yardimci roller,
yeniden baslatma ve otomatik baslatma `.AppImage` dosyasinin kendisini cagirir (runtime yolu
APPIMAGE ortam degiskenine yazar; AppRun -> main.py ayni bayraklari dagitir).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

LINUX_HELPER_FLAG = "--np-linux-helper"
DHCP_DAEMON_FLAG = "--np-dhcp-daemon"
MAIN = Path(__file__).resolve().parents[3] / "main.py"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def appimage_path() -> str | None:
    """AppImage icinden calisiyorsa .AppImage dosyasinin yolu, degilse None."""
    return os.environ.get("APPIMAGE") or None


def is_packaged() -> bool:
    """Paketli mi (PyInstaller ya da AppImage): kaynak agaci yazilamaz/kalici degil."""
    return is_frozen() or appimage_path() is not None


def self_command() -> list[str]:
    """Uygulamanin kendisini yeniden baslatacak argv basi."""
    if is_frozen():
        return [sys.executable]
    if appimage_path():
        return [appimage_path()]
    return [sys.executable, str(MAIN)]


def command_for(script: Path, flag: str) -> list[str]:
    """Betigi calistiracak argv basi (arkasina betigin kendi argumanlari eklenir)."""
    if is_packaged():
        return [*self_command(), flag]
    python = sys.executable or shutil.which("python3") or "/usr/bin/python3"
    return [python, str(script)]


def dispatch(argv: list[str]) -> int | None:
    """Paketli exe bir yardimci rolunde mi cagrildi? Oyleyse calistir ve cikis kodunu dondur."""
    if len(argv) < 2:
        return None
    if argv[1] == DHCP_DAEMON_FLAG:
        from .dhcp_daemon import main as daemon_main
        return daemon_main(argv[2:])
    if argv[1] == LINUX_HELPER_FLAG:
        from .linux.helper import main as helper_main
        return helper_main([argv[0], *argv[2:]])
    return None
