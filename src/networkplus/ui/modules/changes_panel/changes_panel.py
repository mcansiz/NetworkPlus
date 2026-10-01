"""Bekleyen degisiklikler modulu: yerlesim changes_panel.ui'da, davranis burada."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidgetItem, QWidget

from ...uiloader import load_ui, require
from ....core.changes import ChangeSet, describe, validate
from ....core.i18n import tr
from ....core.model import Severity, Topology

KEY_ROLE = Qt.UserRole


class ChangesPanel(QWidget):
    applyRequested = pyqtSignal()
    removeRequested = pyqtSignal(list)      # [(kind, target), ...]
    clearRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "listChanges", "btnApply", "btnRemove", "btnClear", "lblInfo")
        self.btnApply.clicked.connect(self.applyRequested)
        self.btnClear.clicked.connect(self.clearRequested)
        self.btnRemove.clicked.connect(self._remove_selected)
        self._apply_block_reason = ""
        self.show_changes(ChangeSet(), None)

    def set_apply_block(self, reason: str):
        """Bos degilse Uygula devre disi ve neden ipucunda."""
        self._apply_block_reason = reason
        self._sync_buttons()

    def show_changes(self, changes: ChangeSet, topo: Topology | None):
        self.listChanges.clear()
        errors = 0
        for c in changes:
            text = describe(c, topo) if topo else c.kind.value
            issues = validate(c, topo) if topo else []
            it = QListWidgetItem(text)
            it.setData(KEY_ROLE, c.key)
            bad = [i for i in issues if i.severity == Severity.ERROR]
            warn = [i for i in issues if i.severity == Severity.WARNING]
            if bad:
                errors += 1
                it.setText(f"✖ {text}")
            elif warn:
                it.setText(f"⚠ {text}")
            it.setToolTip("\n".join(i.message for i in issues))
            self.listChanges.addItem(it)
        self._count = len(changes)
        self._errors = errors
        self._sync_buttons()

    def _sync_buttons(self):
        count = getattr(self, "_count", 0)
        self.btnApply.setText(tr("Uygula ({count})…").format(count=count) if count else tr("Uygula…"))
        self.btnApply.setEnabled(count > 0 and not self._apply_block_reason)
        self.btnApply.setToolTip(self._apply_block_reason or tr("Planı gözden geçir ve tek yönetici onayıyla uygula"))
        self.btnRemove.setEnabled(count > 0)
        self.btnClear.setEnabled(count > 0)
        if not count:
            info = tr("Değişiklik yok. Özellikler panelinde düzenleyip “Kuyruğa ekle”ye basın ya da diyagramda "
                      "sürükleyerek ilişki kurun.")
        elif self._apply_block_reason:
            info = self._apply_block_reason
        elif getattr(self, "_errors", 0):
            info = tr("{count} değişiklik hatalı (✖); düzeltmeden uygulanamaz.").format(count=self._errors)
        else:
            info = tr("Uygula: plan gösterilir, yönetici izni bir kez istenir; bağlantıyı etkileyen değişikliklerde "
                      "30 sn içinde onaylamazsanız geri alınır.")
        self.lblInfo.setText(info)

    def _remove_selected(self):
        keys = [tuple(it.data(KEY_ROLE)) for it in self.listChanges.selectedItems()]
        if keys:
            self.removeRequested.emit(keys)
