"""Diyagram ustundeki ince durum seridi (pencere acmaz, calismayi engellemez).

Kipler:
  busy    — "Uygulanıyor…" (dugme yok)
  confirm — riskli degisiklik uygulandi: geri sayim + Koru / Geri al; karar gelmezse
            betik kendisi geri alir (bu serit yalniz karari iletir)
  info    — sonuc bilgisi; birkac saniye sonra kendiliginden kapanir
  error   — hata; istege bagli "Geri al" (basarili adimlari geri alir)
"""

from __future__ import annotations

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QFrame

from ...theme import AMBER, BLUE, GREEN, RED
from ...uiloader import load_ui, require
from ....core.i18n import tr

INFO_HIDE_MS = 6000


class ConfirmBar(QFrame):
    keepClicked = pyqtSignal()
    revertClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "lblIcon", "lblMessage", "lblCountdown", "btnKeep", "btnRevert", "btnClose")
        self.btnKeep.clicked.connect(self._keep)
        self.btnRevert.clicked.connect(self._revert)
        self.btnClose.clicked.connect(self.hide)
        self._remaining = 0
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._countdown)
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self.hide)
        self.mode = "hidden"
        self.hide()

    # ----------------------------------------------------------------- kipler
    def _show(self, mode: str, icon: str, color, message: str, keep=False, revert=False, close=True):
        self.mode = mode
        self._tick.stop()
        self._auto_hide.stop()
        self.lblIcon.setText(icon)
        self.lblIcon.setStyleSheet(f"color: {color.name()}; font-weight: bold;")
        self.setStyleSheet(f"ConfirmBar {{ border: 1px solid {color.name()}; border-radius: 4px; }}")
        self.lblMessage.setText(message)
        self.lblCountdown.setText("")
        self.btnKeep.setVisible(keep)
        self.btnRevert.setVisible(revert)
        self.btnKeep.setEnabled(True)
        self.btnRevert.setEnabled(True)
        self.btnClose.setVisible(close)
        self.show()

    def show_busy(self, message: str):
        self._show("busy", "⏳", BLUE, message, close=False)

    def show_confirm(self, seconds: int, message: str):
        self._show("confirm", "⚠", AMBER, message, keep=True, revert=True, close=False)
        self._remaining = seconds
        self._render_countdown()
        self._tick.start()

    def show_info(self, message: str):
        self._show("info", "✔", GREEN, message)
        self._auto_hide.start(INFO_HIDE_MS)

    def show_error(self, message: str, can_revert: bool = False):
        self._show("error", "✖", RED, message, revert=can_revert)

    # ----------------------------------------------------------------- olaylar
    def _render_countdown(self):
        self.lblCountdown.setText(tr("{seconds} sn").format(seconds=max(0, self._remaining)))

    def _countdown(self):
        self._remaining -= 1
        self._render_countdown()
        if self._remaining <= 0:
            self._tick.stop()
            self.btnKeep.setEnabled(False)
            self.btnRevert.setEnabled(False)
            self.lblMessage.setText(tr("Süre doldu — değişiklikler geri alınıyor…"))

    def _keep(self):
        self._tick.stop()
        self.btnKeep.setEnabled(False)
        self.btnRevert.setEnabled(False)
        self.keepClicked.emit()

    def _revert(self):
        self._tick.stop()
        self.btnKeep.setEnabled(False)
        self.btnRevert.setEnabled(False)
        self.revertClicked.emit()


__all__ = ["ConfirmBar"]
