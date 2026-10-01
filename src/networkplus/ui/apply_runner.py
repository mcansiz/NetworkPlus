"""Degisiklikleri PENCERESIZ uygular (kullanici: "onay formu olmasin, direkt uygulansin").

Akis: is (Windows .ps1 / Linux helper) arka plan is parcaciginda calisir; applied.json
gelince, onay suresi verilmisse `needConfirm` yayilir (arayuz ince seritte Koru / Geri al
gosterir; karar gelmezse betik KENDISI geri alir), sonra `finished`.
Bu nesne arayuz cizmez; ConfirmBar ve MainWindow sinyallerle baglanir.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal


class ApplyThread(QThread):
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job

    def run(self):
        try:
            self.succeeded.emit(self.job.run())
        except Exception as exc:        # noqa: BLE001 - kullaniciya gosterilir
            self.failed.emit(str(exc))


class ApplyRunner(QObject):
    applied = pyqtSignal(list)              # adim sonuclari (applied.json)
    needConfirm = pyqtSignal(int)           # onay suresi (sn)
    finished = pyqtSignal(str, list, list)  # 'kept'|'reverted'|'failed', adimlar, geri alma sonuclari
    failedToStart = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = None
        self.thread: ApplyThread | None = None
        self.context = None                 # cagiranin sakladigi bilgi (plan vb.)
        self._steps: list = []
        self._applied_seen = False
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._check_applied)

    @property
    def busy(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def run(self, job, context=None):
        self.job, self.context = job, context
        self._steps, self._applied_seen = [], False
        self.thread = ApplyThread(job, self)
        self.thread.succeeded.connect(self._on_final)
        self.thread.failed.connect(self._on_failed)
        self.thread.start()
        self._poll.start()

    def keep(self):
        if self.job is not None:
            self.job.keep()

    def revert(self):
        if self.job is not None:
            self.job.revert()

    def shutdown(self, timeout_ms: int = 10000):
        """Uygulama kapanirken: onay bekleyen is varsa GERI AL (baglanti durumu belirsizken
        cikiliyor) ve is parcacigini bekle. QThread calisirken yok edilirse surec coker
        (testte yakalandi)."""
        if self.busy:
            self.revert()
            self.thread.wait(timeout_ms)
        self._poll.stop()

    def _check_applied(self):
        if self._applied_seen or self.job is None:
            return
        data = self.job.applied()
        if data is None:
            return
        self._applied_seen = True
        steps = data.get("steps") or []
        self._steps = [steps] if isinstance(steps, dict) else list(steps)
        self.applied.emit(self._steps)
        seconds = int(data.get("confirm_seconds") or 0)
        if seconds > 0:
            self.needConfirm.emit(seconds)

    def _join(self):
        self._poll.stop()
        if self.thread is not None:
            self.thread.wait(5000)          # QThread calisirken yok edilmesin (cokme, bkz. worklog)

    def _on_final(self, final: dict):
        self._check_applied()
        self._join()
        rolled = final.get("rollback") or []
        rolled = [rolled] if isinstance(rolled, dict) else list(rolled)
        outcome = "kept" if final.get("decision") == "keep" else "reverted"
        self.finished.emit(outcome, self._steps, rolled)

    def _on_failed(self, message: str):
        self._join()
        if self._steps:
            self.finished.emit("failed", self._steps, [])
        else:
            self.failedToStart.emit(message)
