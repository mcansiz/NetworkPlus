"""DHCP sunucu surecini yonetir (ADR 0010): baslat, olaylari oku, komut gonder, durdur.

Surec: platform/dhcp_daemon.py (JSON satirlari). Windows'ta normal surec + gerekirse
guvenlik duvari kurali; Linux'ta port 67 icin pkexec (kok degilse).
Uygulama kapaninca stdin kapanir ve sunucu kendiliginden durur.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

from PyQt5.QtCore import QObject, QProcess, pyqtSignal

from ..core.dhcp.leases import DhcpConfig
from ..core.i18n import tr
from ..paths import work_dir

DAEMON = Path(__file__).resolve().parents[1] / "platform" / "dhcp_daemon.py"
SRC_DIR = Path(__file__).resolve().parents[2]
FIREWALL_RULE = "networkPlus DHCP"


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)[:60] or "adapter"


def leases_path(interface: str) -> Path:
    return work_dir("dhcp") / f"{_safe(interface)}-leases.json"


def ensure_windows_firewall(elevated: bool) -> tuple[bool, str]:
    """Gelen UDP 67 icin kural (yoksa ekle). Yonetici degilse UAC ile."""
    import subprocess
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    q = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE}"],
                       capture_output=True, creationflags=no_window)
    if q.returncode == 0:
        return True, ""
    add = ["advfirewall", "firewall", "add", "rule", f"name={FIREWALL_RULE}", "dir=in", "action=allow",
           "protocol=UDP", "localport=67"]
    if elevated:
        r = subprocess.run(["netsh", *add], capture_output=True, creationflags=no_window)
    else:
        from ..platform.windows.apply import ps
        cmd = f"$p = Start-Process netsh -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList {ps(subprocess.list2cmdline(add))}; exit $p.ExitCode"
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, creationflags=no_window)
    if r.returncode != 0:
        return False, tr("Güvenlik duvarı kuralı eklenemedi (UDP 67); istemciler sunucuya ulaşamayabilir.")
    return True, ""


class DhcpService(QObject):
    started = pyqtSignal(dict)
    stopped = pyqtSignal(str)            # neden / hata metni ('' = normal)
    # 'event' DEGIL: QObject.event() sanal metodunu golgeler, Qt her olayda sinyali cagirmaya calisir.
    message = pyqtSignal(dict)           # packet / lease_event / leases / log / error

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self.config: DhcpConfig | None = None
        self._buffer = b""
        self._error = ""

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.NotRunning

    def start(self, cfg: DhcpConfig) -> None:
        if self.running:
            return
        self.config = cfg
        self._buffer, self._error = b"", ""
        wd = work_dir("dhcp")
        cfg_path = wd / f"{_safe(cfg.interface)}-config.json"
        cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        from ..platform.selfexec import DHCP_DAEMON_FLAG, command_for
        head = command_for(DAEMON, DHCP_DAEMON_FLAG)         # python betik.py | paketli exe --bayrak
        args = head[1:] + ["--src", str(SRC_DIR), "--config", str(cfg_path),
                           "--leases", str(leases_path(cfg.interface))]
        program, argv = head[0], args
        if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() != 0:
            prefix = shlex.split(os.environ.get("NETWORKPLUS_ELEVATE", "pkexec"))
            program, argv = prefix[0], prefix[1:] + [head[0]] + args
        if self.proc is not None:
            self.proc.deleteLater()
        self.proc = QProcess(self)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.readyReadStandardError.connect(self._read_err)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._on_error)
        self.proc.start(program, argv)

    def stop(self) -> None:
        if not self.running:
            return
        self.send({"cmd": "stop"})
        self.proc.closeWriteChannel()             # stdin EOF -> sunucu durur (kok surec de)
        if not self.proc.waitForFinished(5000):
            self.proc.kill()
            self.proc.waitForFinished(2000)

    def send(self, obj: dict) -> None:
        if self.running:
            self.proc.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def set_reservations(self, items: dict) -> None:
        self.send({"cmd": "reservations", "items": items})

    def delete_lease(self, mac: str) -> None:
        self.send({"cmd": "delete_lease", "mac": mac})

    # ----------------------------------------------------------------- ic
    def _read(self):
        self._buffer += bytes(self.proc.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                ev = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if ev.get("event") == "started":
                self.started.emit(ev)
            elif ev.get("event") == "error" and ev.get("code") in ("bind", "permission", "config"):
                self._error = self._describe_error(ev)
            self.message.emit(ev)

    def _read_err(self):
        text = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace").strip()
        if text and not self._error:
            self._error = text[-400:]

    def _describe_error(self, ev: dict) -> str:
        code = ev.get("code")
        if code == "bind":
            return tr("Port 67 kullanılamıyor: başka bir DHCP sunucusu (ör. İnternet paylaşımı/ICS, "
                      "NetworkManager paylaşımı, dnsmasq) bu kartı kullanıyor. ({detail})").format(detail=ev.get("detail"))
        if code == "permission":
            return tr("Port 67 için yetki yok: {detail}").format(detail=ev.get("detail"))
        return tr("Ayarlar geçersiz: {detail}").format(detail=ev.get("detail"))

    def _fail(self, message: str):
        if not self._error:
            self._error = message

    def _on_error(self, err):
        self._fail(self.proc.errorString())
        if err == QProcess.FailedToStart:            # finished() hic gelmez
            self.stopped.emit(self._error)

    def _finished(self, code: int = 0, _status=None):
        if code not in (0, None) and not self._error:
            self._error = tr("Sunucu süreci beklenmedik şekilde kapandı (kod {code}).").format(code=code)
        self.stopped.emit(self._error)
