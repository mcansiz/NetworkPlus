"""Uygula penceresi: plan -> tek UAC -> koru / geri al (ADR 0003, 0004).

Durumlar: review -> running (UAC + uygulama) -> confirm (geri sayim) -> done.
Geri sayim bittiginde geri almayi uygulama degil yukseltilmis betik yapar;
bu pencere yalnizca karari (keep/revert bayragi) iletir ve sonucu gosterir.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QDialog, QFileDialog, QHeaderView, QTreeWidgetItem

from ...theme import GREEN, RED, SEVERITY_COLOR
from ...uiloader import load_ui, require
from ....core.changes import Plan, describe, needs_confirmation
from ....core.i18n import tr

CONFIRM_SECONDS = 30
from ....core.model import Severity, Topology

ICON = {Severity.ERROR: "✖", Severity.WARNING: "⚠", Severity.INFO: "ℹ"}


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


class ApplyDialog(QDialog):
    """outcome: 'kept' | 'reverted' | 'failed' | 'cancelled'"""

    def __init__(self, plan: Plan, topo: Topology, script: str, job_factory, parent=None,
                 script_suffix: str = ".ps1", elevated: bool = False):
        """job_factory(confirm_seconds) -> is. elevated: uygulama zaten yonetici (UAC sorulmaz)."""
        super().__init__(parent)
        self.script_suffix = script_suffix
        self.elevated = elevated
        load_ui(self, __file__)
        require(self, "lblHeadline", "treePlan", "btnShowScript", "btnSaveScript", "txtScript",
                "lblStatus", "barCountdown", "btnRevert", "btnKeep", "btnApply", "btnClose",
                "chkConfirm", "lblConfirmReason")
        self.plan, self.topo, self.script = plan, topo, script
        self.job_factory = job_factory
        risky, reason = needs_confirmation(plan, topo)
        self.chkConfirm.setChecked(risky)
        self.lblConfirmReason.setText((tr("Önerilen: onay iste — {reason}") if risky
                                       else tr("Önerilen: onaysız — {reason}")).format(reason=reason))
        self.chkConfirm.toggled.connect(lambda _: self._set_state(self.state))
        self.job = None
        self.thread: ApplyThread | None = None
        self.state = "review"
        self.outcome = "cancelled"
        self._remaining = 0
        self._step_items: list[QTreeWidgetItem] = []

        self.txtScript.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.txtScript.setPlainText(script)
        self.txtScript.setVisible(False)
        self.btnShowScript.toggled.connect(self.txtScript.setVisible)
        self.btnSaveScript.clicked.connect(self._save_script)
        self.btnApply.clicked.connect(self._start)
        self.btnKeep.clicked.connect(self._keep)
        self.btnRevert.clicked.connect(self._revert)
        self.btnClose.clicked.connect(self.accept)
        header = self.treePlan.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._check_applied)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._countdown)

        self._fill_plan()
        self._set_state("review")

    # ----------------------------------------------------------------- plan
    def _fill_plan(self):
        self.treePlan.clear()
        for item in self.plan.items:
            it = QTreeWidgetItem(self.treePlan, [item.title, tr("bekliyor")])
            for issue in item.issues:
                child = QTreeWidgetItem(it, [f"{ICON[issue.severity]} {issue.message}", ""])
                child.setForeground(0, SEVERITY_COLOR[issue.severity])
                child.setToolTip(0, issue.message)
            it.setExpanded(bool(item.issues))
            self._step_items.append(it)
        if self.plan.rollback:
            rb = QTreeWidgetItem(self.treePlan, [tr("Onaylamazsanız geri alınacak (şu anki ayarlar)"), ""])
            for c in self.plan.rollback:
                QTreeWidgetItem(rb, [describe(c, self.topo), ""])
            rb.setExpanded(False)

    def _set_state(self, state: str):
        self.state = state
        review, running, confirm, done = (state == s for s in ("review", "running", "confirm", "done"))
        self.btnApply.setVisible(review)
        self.btnApply.setEnabled(review and not self.plan.blocked)
        self.btnKeep.setVisible(confirm)
        self.btnRevert.setVisible(confirm)
        self.btnClose.setVisible(review or done)
        self.btnClose.setText(tr("Vazgeç") if review else tr("Kapat"))
        self.barCountdown.setVisible(confirm)
        self.chkConfirm.setEnabled(review)
        if review:
            n = len(self.plan.items)
            if self.plan.blocked:
                self.lblHeadline.setText(tr("<b>{count} adımlık plan uygulanamaz:</b> ✖ işaretli hataları düzeltin.").format(count=n))
            else:
                ask = "" if self.elevated else tr("Uygula'ya basınca yönetici izni istenir (Windows: UAC, Linux: parola).") + " "
                after = (tr("Sonra değişiklikleri <b>30 saniye</b> içinde onaylamazsanız hepsi otomatik geri alınır.")
                         if self.chkConfirm.isChecked() else tr("Onay beklenmeden hemen tamamlanır."))
                self.lblHeadline.setText(tr("<b>{count} adım uygulanacak.</b>").format(count=n) + f" {ask}{after}")
            self.lblStatus.setText("")
            self.btnApply.setDefault(True)
            self.btnApply.setFocus()

    # ----------------------------------------------------------------- akis
    def _start(self):
        try:
            self.job = self.job_factory(CONFIRM_SECONDS if self.chkConfirm.isChecked() else 0)
        except Exception as exc:        # noqa: BLE001
            self._finish_failed(str(exc))
            return
        self._set_state("running")
        self.lblHeadline.setText(tr("<b>Uygulanıyor…</b>"))
        self.lblStatus.setText("" if self.elevated else
                               tr("Yönetici izni bekleniyor — açılan izin penceresini onaylayın (Windows: UAC, Linux: parola)."))
        self.thread = ApplyThread(self.job, self)
        self.thread.succeeded.connect(self._finished)
        self.thread.failed.connect(self._finish_failed)
        self.thread.start()
        self._poll.start()

    def _check_applied(self):
        if self.state != "running" or self.job is None:
            return
        applied = self.job.applied()
        if applied is None:
            return
        steps = applied.get("steps") or []
        if isinstance(steps, dict):
            steps = [steps]
        failures = 0
        for st in steps:
            idx = int(st.get("id", 0)) - 1
            if 0 <= idx < len(self._step_items):
                it = self._step_items[idx]
                for w in st.get("warnings") or []:          # yok sayilabilir hatalar (ör. DHCP yaniti yok)
                    child = QTreeWidgetItem(it, [f"⚠ {w}", ""])
                    child.setForeground(0, SEVERITY_COLOR[Severity.WARNING])
                    child.setToolTip(0, w)
                    it.setExpanded(True)
                if st.get("ok"):
                    it.setText(1, tr("✔ uygulandı (uyarılı)") if st.get("warnings") else tr("✔ uygulandı"))
                    it.setForeground(1, GREEN)
                else:
                    failures += 1
                    it.setText(1, tr("✖ hata"))
                    it.setForeground(1, RED)
                    it.setToolTip(1, st.get("error") or "")
                    QTreeWidgetItem(it, [f"✖ {st.get('error')}", ""]).setForeground(0, RED)
                    it.setExpanded(True)
        self._remaining = int(applied.get("confirm_seconds") or 0)
        if not self.plan.rollback or self._remaining <= 0:
            self.lblStatus.setText(tr("Tamamlanıyor…"))
            return
        self._set_state("confirm")
        self.barCountdown.setMaximum(self._remaining)
        self.barCountdown.setValue(self._remaining)
        if failures:
            self.lblHeadline.setText(tr("<b>{count} adım başarısız oldu.</b> Ayarları eski hâline "
                                        "döndürmek için <b>Geri al</b> önerilir.").format(count=failures))
        else:
            self.lblHeadline.setText(tr("<b>Değişiklikler uygulandı.</b> Ağınız beklediğiniz gibi çalışıyorsa "
                                        "<b>Değişiklikleri koru</b>'ya basın."))
        self.lblStatus.setText(tr("Süre içinde yanıt vermezseniz (ör. bağlantı koptuysa) tüm değişiklikler "
                                  "otomatik geri alınır."))
        self._tick.start()

    def _countdown(self):
        self._remaining -= 1
        self.barCountdown.setValue(max(0, self._remaining))
        if self._remaining <= 0:
            self._tick.stop()
            self.btnKeep.setEnabled(False)
            self.btnRevert.setEnabled(False)
            self.lblStatus.setText(tr("Süre doldu — değişiklikler geri alınıyor…"))

    def _keep(self):
        self._tick.stop()
        self.job.keep()
        self.btnKeep.setEnabled(False)
        self.btnRevert.setEnabled(False)
        self.lblStatus.setText(tr("Onaylandı, tamamlanıyor…"))

    def _revert(self):
        self._tick.stop()
        self.job.revert()
        self.btnKeep.setEnabled(False)
        self.btnRevert.setEnabled(False)
        self.lblStatus.setText(tr("Geri alınıyor…"))

    def _join_thread(self):
        # Sinyal run() donmeden gelir; QThread nesnesi calisirken yok edilirse surec coker
        # (testte yakalandi: segfault). Sonucu isledikten sonra is parcacigini bekle.
        if self.thread is not None:
            self.thread.wait(5000)

    def done(self, code):
        if self.state in ("running", "confirm"):
            return
        self._join_thread()
        super().done(code)

    def _finished(self, final: dict):
        self._join_thread()
        self._poll.stop()
        self._check_applied_final()
        self._tick.stop()
        decision = final.get("decision")
        rolled = final.get("rollback") or []
        if isinstance(rolled, dict):
            rolled = [rolled]
        bad = [r for r in rolled if not r.get("ok")]
        if rolled:
            header = QTreeWidgetItem(self.treePlan, [tr("Geri alma sonucu"), ""])
            for r in rolled:
                child = QTreeWidgetItem(header, [r.get("title") or "", "✔" if r.get("ok") else tr("✖ hata")])
                child.setForeground(1, GREEN if r.get("ok") else RED)
                for msg in ([r["error"]] if r.get("error") else []) + list(r.get("warnings") or []):
                    QTreeWidgetItem(child, [msg, ""]).setToolTip(0, msg)
            header.setExpanded(True)
        self._set_state("done")
        if decision == "keep":
            self.outcome = "kept"
            self.lblHeadline.setText(tr("<b>Değişiklikler kalıcı olarak uygulandı.</b>"))
            self.lblStatus.setText(tr("Diyagram yenileniyor."))
        else:
            self.outcome = "reverted"
            self.lblHeadline.setText(tr("<b>Değişiklikler geri alındı</b> (süre doldu).") if decision == "timeout"
                                     else tr("<b>Değişiklikler geri alındı</b> (isteğiniz üzerine)."))
            if bad:
                self.lblStatus.setText(tr("Bazı geri alma adımları başarısız: {details}").format(
                    details="; ".join(f"{r.get('title')}: {r.get('error')}" for r in bad)))
            else:
                self.lblStatus.setText(tr("Ayarlar uygulama öncesi hâline döndü. Bekleyen değişiklikler kuyrukta duruyor."))

    def _check_applied_final(self):
        if self.state == "running":
            self._check_applied()

    def _finish_failed(self, message: str):
        self._join_thread()
        self._poll.stop()
        self._tick.stop()
        self._set_state("done")
        self.outcome = "failed"
        self.lblHeadline.setText(tr("<b>Uygulanamadı.</b>"))
        self.lblStatus.setText(message)

    # ----------------------------------------------------------------- diger
    def _save_script(self):
        ps1 = self.script_suffix == ".ps1"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Betiği kaydet"), f"networkplus-apply{self.script_suffix}",
            "PowerShell (*.ps1)" if ps1 else tr("Kabuk betiği (*.sh)"))
        if path:
            # PS 5.1 BOM'suz UTF-8'i ANSI okur; sh BOM'u sevmez.
            Path(path).write_text(self.script, encoding="utf-8-sig" if ps1 else "utf-8")

    def reject(self):
        # Uygulama/onay suresince pencere kapatilamaz (karar betikte bekleniyor).
        if self.state in ("running", "confirm"):
            return
        super().reject()

    def closeEvent(self, event):
        if self.state in ("running", "confirm"):
            event.ignore()
            return
        self._join_thread()
        super().closeEvent(event)
