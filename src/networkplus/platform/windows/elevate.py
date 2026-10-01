"""Windows yetki durumu ve 'yonetici olarak yeniden baslat' (ADR 0004).

Uygulama varsayilan olarak yetkisiz calisir; her Uygula'da bir UAC istenir.
Sik degisiklik yapan kullanici uygulamayi yonetici olarak yeniden baslatabilir;
o zaman Uygula UAC sormadan calisir.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_as_admin(argv: list[str] | None = None) -> bool:
    """Ayni uygulamayi 'runas' ile yeniden baslatir. UAC reddedilirse False."""
    args = list(sys.argv if argv is None else argv)
    if getattr(sys, "frozen", False):               # PyInstaller paketi
        exe, params = sys.executable, args[1:]
    else:
        exe, params = sys.executable, args
    # ShellExecuteW > 32 = basarili; kullanici UAC'i reddederse 5 (erisim engellendi).
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, subprocess.list2cmdline(params), None, 1)
    return rc > 32
