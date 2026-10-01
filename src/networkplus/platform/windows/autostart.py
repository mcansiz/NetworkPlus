"""Windows: sistemle baslatma ve acilista UAC'siz yonetici yetkisi.

Kipler:
  off   — baslatma yok
  user  — HKCU\\...\\Run degeri (yonetici gerekmez; uygulama yetkisiz acilir)
  admin — Gorev Zamanlayici: oturum acilisinda 'en yuksek yetki' ile.
          Gorevi KURMAK bir kez UAC ister; sonra hic sormaz. Kullanici uygulamayi
          elle acinca da (app.py) gorev tetiklenir ve uygulama UAC'siz yonetici olur.

Neden Run anahtari degil: Run ile yuksek yetkili baslatma her acilista UAC sorar;
UAC'siz yuksek yetkinin desteklenen yolu Gorev Zamanlayici'dir (RunLevel Highest).
Gorev ayarlari: pilde de baslar, sure siniri yok, ikinci kopya baslatilmaz.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

from .apply import ps
from ...core.i18n import tr

TASK_NAME = "networkPlus"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "networkPlus"
MAIN = Path(__file__).resolve().parents[4] / "main.py"     # depo koku/main.py
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def launch_command(tray: bool = True) -> tuple[str, list[str]]:
    """(calistirilabilir, argumanlar). Konsol penceresi acilmasin diye pythonw tercih edilir."""
    extra = ["--tray"] if tray else []
    if getattr(sys, "frozen", False):
        return sys.executable, extra
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe), [str(MAIN), *extra]


def current_user() -> str:
    return f"{os.environ.get('USERDOMAIN', '.')}\\{os.environ.get('USERNAME', '')}"


# --------------------------------------------------------------------------- durum

def _run_value() -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except OSError:
        return None


def task_exists() -> bool:
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, creationflags=_NO_WINDOW)
    return r.returncode == 0


def get_mode() -> str:
    if task_exists():
        return "admin"
    return "user" if _run_value() else "off"


# --------------------------------------------------------------------------- degistirme

def _set_run_value(enabled: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            exe, args = launch_command(tray=True)
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline([exe, *args]))
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def register_task_script() -> str:
    exe, args = launch_command(tray=True)
    user = current_user()
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$a = New-ScheduledTaskAction -Execute {ps(exe)} -Argument {ps(subprocess.list2cmdline(args))} "
        f"-WorkingDirectory {ps(str(MAIN.parent))}",
        f"$t = New-ScheduledTaskTrigger -AtLogOn -User {ps(user)}",
        "$t.Delay = 'PT10S'   # tepsi (explorer) hazir olsun",
        f"$p = New-ScheduledTaskPrincipal -UserId {ps(user)} -LogonType Interactive -RunLevel Highest",
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew",
        f"Register-ScheduledTask -TaskName {ps(TASK_NAME)} -Action $a -Trigger $t -Principal $p "
        "-Settings $s -Description 'networkPlus: oturum acilisinda yonetici olarak tepside baslat' -Force | Out-Null",
    ])


def unregister_task_script() -> str:
    return (f"$ErrorActionPreference = 'Stop'\n"
            f"if (Get-ScheduledTask -TaskName {ps(TASK_NAME)} -ErrorAction SilentlyContinue) "
            f"{{ Unregister-ScheduledTask -TaskName {ps(TASK_NAME)} -Confirm:$false }}")


def _run_elevated(script: str) -> tuple[bool, str]:
    """PowerShell betigini yonetici olarak calistir (zaten yoneticiyse UAC'siz)."""
    from .elevate import is_admin
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    if is_admin():
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    else:
        inner = f"-NoProfile -NonInteractive -EncodedCommand {encoded}"
        outer = (f"$p = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru "
                 f"-ArgumentList {ps(inner)}; exit $p.ExitCode")
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
               base64.b64encode(outer.encode("utf-16-le")).decode("ascii")]
    r = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW, timeout=120)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip()
        return False, err[:300] or tr("Yönetici izni verilmedi.")
    return True, ""


def set_mode(mode: str) -> tuple[bool, str]:
    if mode not in ("off", "user", "admin"):
        return False, f"bilinmeyen kip: {mode}"
    if mode == "admin":
        ok, err = _run_elevated(register_task_script())
        if not ok:
            return False, tr("Görev kurulamadı: {error}").format(error=err)
        _set_run_value(False)
    else:
        if task_exists():
            ok, err = _run_elevated(unregister_task_script())
            if not ok:
                return False, tr("Yönetici görevi kaldırılamadı: {error}").format(error=err)
        _set_run_value(mode == "user")
    actual = get_mode()
    return actual == mode, "" if actual == mode else f"Beklenen {mode}, bulunan {actual}"


def run_admin_task() -> bool:
    """Yonetici gorevini simdi calistir: uygulama UAC'siz yonetici olarak baslar."""
    r = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, creationflags=_NO_WINDOW)
    return r.returncode == 0
