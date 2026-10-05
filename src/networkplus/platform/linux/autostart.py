"""Linux: oturumla baslatma (XDG autostart .desktop).

'admin' kipi YOK: grafik arayuzu kok olarak calistirmak guvenli degil; Linux'ta her
Uygula pkexec ile bir kez yetki ister (ADR 0005).
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from ...core.i18n import tr
from ..selfexec import is_packaged, self_command

ICON = Path(__file__).resolve().parents[2] / "resources" / "networkplus.png"   # tools/make_app_icon.py


def desktop_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "networkplus.desktop"


def icon_path() -> Path | None:
    """Masaustu dosyasinin gosterecegi simge. Tek dosya pakette kaynak simge gecici acilma
    klasorundedir (cikista silinir), AppImage'da baglama noktasindadir -> kalici bir yere kopyalanir."""
    if not ICON.exists():
        return None
    if not is_packaged():
        return ICON
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    target = Path(base) / "icons" / "networkplus.png"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ICON.read_bytes())
    except OSError:
        return None
    return target


def desktop_entry() -> str:
    argv = self_command()
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=networkPlus",
        "Comment=Ağ bağdaştırıcısı diyagramı (tepside)",  # notr
        f"Exec={shlex.join(argv + ['--tray'])}",
        "X-GNOME-Autostart-enabled=true",
        "Terminal=false",
        *([f"Icon={icon}"] if (icon := icon_path()) else []),
        "",
    ])


def get_mode() -> str:
    return "user" if desktop_path().exists() else "off"


def set_mode(mode: str) -> tuple[bool, str]:
    if mode == "admin":
        return False, tr("Linux'ta yönetici olarak otomatik başlatma desteklenmez.")
    path = desktop_path()
    if mode == "user":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_entry(), encoding="utf-8")
    elif path.exists():
        path.unlink()
    return get_mode() == mode, ""
