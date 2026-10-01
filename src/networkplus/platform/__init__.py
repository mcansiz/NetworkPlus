"""Isletim sistemine dokunan TEK katman (ai_rules/30)."""

from __future__ import annotations

import os
import sys

from .base import Collector, CollectError
from ..core.i18n import tr


def get_collector(snapshot_file: str | None = None) -> Collector:
    if snapshot_file:
        from .filesource import FileCollector
        return FileCollector(snapshot_file)
    if sys.platform == "win32":
        from .windows.collector import WindowsCollector
        return WindowsCollector()
    if sys.platform.startswith("linux"):
        from .linux.collector import LinuxCollector
        return LinuxCollector()
    raise CollectError(f"Desteklenmeyen platform: {sys.platform}")


def apply_support(topo, collector: Collector) -> tuple[bool, str]:
    """Bu topolojiye degisiklik uygulanabilir mi? (False, neden) ya da (True, "")."""
    from .filesource import FileCollector
    if isinstance(collector, FileCollector):
        return False, tr("Kayıtlı bir anlık görüntü görüntüleniyor; değişiklikler yalnız canlı sisteme "
                         "uygulanabilir (Dosya › Canlı sisteme dön).")
    if topo.platform == "windows" and sys.platform == "win32":
        return True, ""
    if topo.platform == "linux" and sys.platform.startswith("linux"):
        import shutil
        if not shutil.which("nmcli"):     # systemd-networkd / ifupdown kullanan dagitimlar
            return False, tr("NetworkManager (nmcli) bulunamadı; bu sistemde değişiklik uygulanamıyor.")
        return True, ""
    return False, tr("Bu platformda değişiklik uygulanamıyor: {platform}").format(platform=topo.platform)


class ApplyBundle:
    """Bir planin uygulanmasi icin gerekenler: onizleme metni + is uretici."""

    def __init__(self, preview: str, suffix: str, factory):
        self.preview = preview
        self.suffix = suffix          # kaydetme uzantisi: .ps1 / .sh
        self._factory = factory

    def create_job(self, confirm_seconds: int):
        """confirm_seconds = 0: onay beklenmez, uygulama biter bitmez tamamlanir."""
        return self._factory(confirm_seconds)


def prepare_apply(plan, topo) -> ApplyBundle:
    if topo.platform == "linux":
        from .linux.apply import LinuxApplyJob, build_payload, render_preview
        payload = build_payload(plan, topo)
        return ApplyBundle(render_preview(payload), ".sh",
                           lambda secs: LinuxApplyJob({**payload, "confirm_seconds": int(secs)}))
    from .windows.apply import WindowsApplyJob
    script = render_apply_script(plan, topo)
    return ApplyBundle(script, ".ps1", lambda secs: WindowsApplyJob(script, secs))


def elevation_state() -> tuple[bool, bool]:
    """(yonetici mi, yonetici olarak yeniden baslatilabilir mi)."""
    if sys.platform == "win32":
        from .windows.elevate import is_admin
        admin = is_admin()
        return admin, not admin
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0, False
    return False, False


def _autostart_module():
    if sys.platform == "win32":
        from .windows import autostart
        return autostart
    if sys.platform.startswith("linux"):
        from .linux import autostart
        return autostart
    return None


def autostart_modes() -> list[str]:
    """Bu platformda sunulan kipler: off / user / admin."""
    if sys.platform == "win32":
        return ["off", "user", "admin"]
    return ["off", "user"] if _autostart_module() else []


def autostart_mode() -> str:
    mod = _autostart_module()
    return mod.get_mode() if mod else "off"


def set_autostart_mode(mode: str) -> tuple[bool, str]:
    mod = _autostart_module()
    return mod.set_mode(mode) if mod else (False, "Bu platformda desteklenmiyor.")


def try_elevate_via_task() -> bool:
    """Windows: yonetici gorevi kuruluysa calistir (UAC'siz yonetici kopya baslar)."""
    if sys.platform != "win32":
        return False
    from .windows import autostart
    from .windows.elevate import is_admin
    if is_admin() or not autostart.task_exists():
        return False
    return autostart.run_admin_task()


def relaunch_as_admin() -> bool:
    if sys.platform != "win32":
        return False
    from .windows.elevate import relaunch_as_admin as _relaunch
    return _relaunch()


def render_apply_script(plan, topo) -> str:
    """Planin uygulama betigi / onizlemesi (Windows: calisan .ps1; Linux: okunur komut listesi)."""
    from ..core.changes import describe
    if topo.platform == "linux":
        from .linux.apply import build_payload, render_preview
        return render_preview(build_payload(plan, topo))
    from .windows.apply import render_script
    return render_script(plan.changes, [i.title for i in plan.items],
                         plan.rollback, [describe(c, topo) for c in plan.rollback])


__all__ = ["Collector", "CollectError", "get_collector", "apply_support",
           "prepare_apply", "render_apply_script", "ApplyBundle", "elevation_state",
           "relaunch_as_admin", "autostart_modes", "autostart_mode", "set_autostart_mode",
           "try_elevate_via_task"]


APP_USER_MODEL_ID = "networkPlus.networkPlus"


def set_app_identity() -> None:
    """Windows: surece kendi AppUserModelID'sini ver. Yoksa gorev cubugu dugmesi python.exe'nin
    simgesini ve grubunu kullanir; pencere simgesi de her zaman gorunmez. Diger sistemlerde bos."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def system_prefers_dark() -> bool | None:
    """Isletim sisteminin acik/koyu tercihi (salt okunur). None = bilinmiyor (acik varsayilir).

    Windows: kayit defteri HKCU / Themes / Personalize, AppsUseLightTheme (0 = koyu).
    Linux: gsettings color-scheme (GNOME) ya da GTK tema adinda 'dark' (Cinnamon/Mint).
    """
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        except OSError:
            return None
    if sys.platform.startswith("linux"):
        import shutil
        import subprocess
        if not shutil.which("gsettings"):
            return None
        answered = False
        for schema, key in (("org.gnome.desktop.interface", "color-scheme"),
                            ("org.cinnamon.desktop.interface", "gtk-theme"),
                            ("org.gnome.desktop.interface", "gtk-theme")):
            try:
                out = subprocess.run(["gsettings", "get", schema, key], capture_output=True,
                                     text=True, timeout=2).stdout.strip().lower()
            except (OSError, subprocess.TimeoutExpired):
                continue
            if out:
                answered = True
                if "dark" in out:
                    return True
        return False if answered else None
    return None
