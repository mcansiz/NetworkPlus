"""Arayuz duman testi (offscreen): tum .ui dosyalari yuklenir, fixture ile ana
pencere acilir, her dugum ve kenar secilip inspector doldurulur.

Designer'da bir objectName degisirse burada `require()` hatasi olarak yakalanir.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QEvent, QEventLoop, Qt, QTimer   # noqa: E402
from PyQt5.QtWidgets import QApplication                  # noqa: E402

from networkplus.platform.filesource import FileCollector  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
UI_FILES = sorted((ROOT / "src" / "networkplus" / "ui").rglob("*.ui"))

_app = QApplication.instance() or QApplication([])
# Testler kullanicinin gercek uygulama ayarlarina (QSettings) yazmasin.
_app.setOrganizationName("networkPlus-test")
_app.setApplicationName("networkPlus-test")


def dispose(win):
    """Pencereyi kapat ve C++ nesnesini HEMEN sil. Kapanmis pencere cop toplayiciya kalirsa
    baska bir Qt cagrisinin ortasinda yok edilip sureci cokertiyor (bkz. worklog: DHCP / cokme)."""
    win.close()
    win.deleteLater()
    _app.sendPostedEvents(None, QEvent.DeferredDelete)


def wait_loaded(win, timeout_ms=15000):
    loop = QEventLoop()
    win.when_loaded(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    win.refresh()
    loop.exec_()


class UiSmoke(unittest.TestCase):
    def test_every_module_has_ui_file(self):
        modules = [p for p in (ROOT / "src" / "networkplus" / "ui" / "modules").iterdir() if p.is_dir()
                   and not p.name.startswith("__")]
        for mod in modules:
            with self.subTest(module=mod.name):
                self.assertTrue(list(mod.glob("*.ui")), f"{mod.name} modulunun .ui dosyasi yok")

    def _open(self, fixture: str):
        from networkplus.ui.modules.main_window.main_window import MainWindow
        win = MainWindow(FileCollector(FIXTURES / fixture))
        win.resize(1400, 850)
        win.show()
        wait_loaded(win)
        self.assertIsNotNone(win.topology, "topoloji yuklenmedi")
        return win

    def test_main_window_with_fixtures(self):
        for fixture in ("win-host.raw.json", "linux-synthetic.raw.json"):
            with self.subTest(fixture=fixture):
                win = self._open(fixture)
                topo = win.topology
                visible = {n.id for n in topo.visible_nodes()}
                self.assertEqual(set(win.diagram.node_items), visible)
                for nid in topo.nodes:
                    win._on_list_activated(nid)          # gizliyse gorunur yapar
                    self.assertIn(win.inspector.stack.currentIndex(), (1, 2))
                for eid in win.diagram.edge_items:
                    win.diagram.select(eid)
                    self.assertEqual(win.inspector.stack.currentIndex(), 2)
                win.actShowHidden.setChecked(False)
                win.diagram.relayout()
                dispose(win)

    def test_export_png(self):
        win = self._open("win-host.raw.json")
        from networkplus.paths import work_dir
        out = work_dir("test") / "networkplus-smoke.png"      # proje/.tmp (TEMP degil)
        self.assertTrue(win.diagram.export_png(str(out)))
        self.assertGreater(out.stat().st_size, 1000)
        dispose(win)


class FakeJob:
    """Gercek betik YERINE: hicbir komut calistirmaz. run() karar gelene kadar bekler."""

    def __init__(self, script, fail_step=False, confirm_seconds=30):
        self.script = script
        self.decision = None
        self.fail_step = fail_step
        self.confirm_seconds = confirm_seconds

    def applied(self):
        return {"phase": "applied", "confirm_seconds": self.confirm_seconds,
                "steps": [{"id": 1, "title": "x", "ok": not self.fail_step,
                           "error": "sahte hata" if self.fail_step else None}]}

    def run(self):
        import time
        if self.confirm_seconds <= 0:          # gercek betikler gibi: onay yoksa hemen 'keep'
            return {"phase": "final", "decision": "keep", "rollback": []}
        deadline = time.monotonic() + max(self.confirm_seconds, 0) + 2
        while self.decision is None and time.monotonic() < deadline:
            time.sleep(0.02)
        decision = self.decision or "timeout"
        return {"phase": "final", "decision": decision,
                "rollback": [] if decision == "keep" else [{"id": 1, "title": "geri", "ok": True}]}

    def keep(self):
        self.decision = "keep"

    def revert(self):
        self.decision = "revert"


def spin_until(predicate, timeout_ms=8000):
    import time
    end = time.monotonic() + timeout_ms / 1000
    while not predicate() and time.monotonic() < end:
        _app.processEvents()
        time.sleep(0.01)
    return predicate()


class ChangeFlow(unittest.TestCase):
    """M2 akisi: form -> kuyruk -> diyagram isareti -> Uygula penceresi (sahte is)."""

    def setUp(self):
        from PyQt5.QtCore import QSettings
        QSettings().clear()          # testler birbirinin ayarini (ör. onay kapali) devralmasin
        from networkplus.ui.modules.main_window.main_window import MainWindow
        self.win = MainWindow(FileCollector(FIXTURES / "win-host.raw.json"))
        self.win.show()
        wait_loaded(self.win)
        self.id = {n.label: n.id for n in self.win.topology.nodes.values()}

    def tearDown(self):
        # Uygulama isi ve ardindan baslayan yenileme bitmeden kapatma (bkz. worklog: cokme).
        w = self.win
        spin_until(lambda: not w.runner.busy and not (w._thread and w._thread.isRunning()), 10000)
        _app.processEvents()
        dispose(w)

    def test_form_queue_static_ip(self):
        w = self.win
        eth = self.id["ETH"]
        w.diagram.select(eth)
        insp = w.inspector
        self.assertEqual(insp.cmbIpv4Mode.currentIndex(), 1)          # ETH statik
        self.assertEqual(insp.edIpAddress.text(), "192.168.1.2")
        self.assertEqual(insp.form_changes()[0], [])                  # dokunulmamis form = degisiklik yok
        insp.edIpAddress.setText("192.168.1.20")
        insp.btnQueue.click()
        self.assertEqual(len(w.changes), 1)
        self.assertTrue(w.diagram.node_items[eth].pending)
        self.assertEqual(w.changesPanel.listChanges.count(), 1)
        # Dosyadan goruntulerken Uygula engelli
        self.assertFalse(w.changesPanel.btnApply.isEnabled())
        # Formu eski degere dondurup tekrar eklemek kuyruktan cikarir
        insp.edIpAddress.setText("192.168.1.2")
        insp.btnQueue.click()
        self.assertEqual(len(w.changes), 0)

    def test_invalid_form_not_queued(self):
        w = self.win
        w.diagram.select(self.id["ETH"])
        w.inspector.edGateway.setText("10.9.9.9")                      # alt ag disi
        w.inspector.btnQueue.click()
        self.assertEqual(len(w.changes), 0)
        self.assertIn("Düzeltin", w.inspector.lblPending.text())

    def test_every_adapter_form_is_clean(self):
        """Hicbir bagdastiricinin formu, dokunulmadan degisiklik uretmemeli."""
        for node in self.win.topology.nodes.values():
            if not node.is_adapter:
                continue
            with self.subTest(adapter=node.label):
                self.win.inspector.show_node(node.id)
                self.assertEqual(self.win.inspector.form_changes()[0], [])

    # ------------------------------------------------ dogrudan uygulama (pencere yok)
    def _fake_backend(self):
        from PyQt5.QtWidgets import QApplication, QDialog
        jobs = []
        self.win._apply_support = lambda: (True, "")
        self.win._create_job = lambda plan, secs: jobs.append(FakeJob("script", confirm_seconds=secs)) or jobs[-1]
        dialogs = lambda: [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()]  # noqa: E731
        return jobs, dialogs

    def test_power_button_applies_without_dialog(self):
        w = self.win
        jobs, dialogs = self._fake_backend()
        w._toggle_power(self.id["ETH"])               # ETH bagli degil -> riskli degil -> onaysiz
        self.assertTrue(spin_until(lambda: not w.runner.busy and w.confirmBar.mode == "info"))
        self.assertEqual(jobs[0].confirm_seconds, 0)
        self.assertEqual(dialogs(), [])                # onay penceresi YOK (kullanici istegi)
        self.assertEqual(len(w.changes), 0)            # kuyruga girmedi

    def test_risky_change_uses_confirm_bar(self):
        from networkplus.core.changes import Change, ChangeKind
        w = self.win
        jobs, dialogs = self._fake_backend()
        w.apply_now([Change(ChangeKind.MTU, self.id["Wi-Fi"], {"mtu": 1400})])   # internet karti
        self.assertTrue(spin_until(lambda: w.confirmBar.mode == "confirm"))
        self.assertEqual(jobs[0].confirm_seconds, 30)
        self.assertEqual(dialogs(), [])
        w.confirmBar.btnKeep.click()
        self.assertTrue(spin_until(lambda: not w.runner.busy and w.confirmBar.mode == "info"))

    def test_risky_confirm_can_be_disabled(self):
        from networkplus.core.changes import Change, ChangeKind
        w = self.win
        jobs, _ = self._fake_backend()
        w.actConfirmRisky.setChecked(False)
        w.apply_now([Change(ChangeKind.MTU, self.id["Wi-Fi"], {"mtu": 1400})])
        self.assertTrue(spin_until(lambda: not w.runner.busy))
        self.assertEqual(jobs[0].confirm_seconds, 0)

    def test_invalid_change_not_applied(self):
        from networkplus.core.changes import Change, ChangeKind
        w = self.win
        jobs, _ = self._fake_backend()
        self.assertFalse(w.apply_now([Change(ChangeKind.MTU, self.id["ETH"], {"mtu": 10})]))
        self.assertEqual(jobs, [])
        self.assertEqual(w.confirmBar.mode, "error")

    def test_show_window_keeps_maximized(self):
        """Kullanici: etkinlestire basinca arayuz kuculuyordu (showNormal)."""
        w = self.win
        w.showMaximized()
        _app.processEvents()
        w.show_window()
        _app.processEvents()
        self.assertTrue(w.windowState() & Qt.WindowMaximized)

    def test_default_layout_and_remembered(self):
        """Varsayilan: solda Bagdastiricilar + Ozellikler (ust/alt), sagda DHCP. Kullanici
        yerlesimi kapanis beklenmeden kaydedilir ve yeni pencerede geri gelir."""
        w = self.win
        self.assertEqual(w.dockWidgetArea(w.dockAdapters), Qt.LeftDockWidgetArea)
        self.assertEqual(w.dockWidgetArea(w.dockInspector), Qt.LeftDockWidgetArea)
        self.assertEqual(w.dockWidgetArea(w.dockDhcp), Qt.RightDockWidgetArea)
        self.assertLess(w.dockAdapters.y(), w.dockInspector.y())             # ust / alt
        self.assertFalse(w.tabifiedDockWidgets(w.dockInspector))
        w.addDockWidget(Qt.RightDockWidgetArea, w.dockInspector)              # kullanici tasidi
        self.assertTrue(spin_until(lambda: not w._layout_timer.isActive(), 3000))
        from networkplus.ui.modules.main_window.main_window import MainWindow
        w2 = MainWindow(FileCollector(FIXTURES / "win-host.raw.json"))       # kapanis OLMADAN
        try:
            self.assertEqual(w2.dockWidgetArea(w2.dockInspector), Qt.RightDockWidgetArea)
            w2.actResetLayout.trigger()
            self.assertEqual(w2.dockWidgetArea(w2.dockInspector), Qt.LeftDockWidgetArea)
        finally:
            dispose(w2)

    def test_settings_saved_immediately_and_changes_menu(self):
        """Ayar kapanis beklenmeden yazilir; Degisiklikler menusu yalniz toplu kipte gorunur (bos kalmaz)."""
        from PyQt5.QtCore import QSettings
        w = self.win
        self.assertFalse(w.menuChanges.menuAction().isVisible())
        w.actConfirmRisky.setChecked(False)
        w.actAutoRefresh.setChecked(True)
        self.assertFalse(QSettings().value("apply/confirmRisky", True, type=bool))
        self.assertTrue(QSettings().value("view/autoRefresh", False, type=bool))
        w.actQueueMode.setChecked(True)
        self.assertTrue(w.menuChanges.menuAction().isVisible())
        self.assertTrue(QSettings().value("apply/queueMode", False, type=bool))
        w.actQueueMode.setChecked(False)
        w.actAutoRefresh.setChecked(False)

    def test_adapter_list_two_lines_and_queue_mode(self):
        w = self.win
        item = w.adapterList._items[self.id["Wi-Fi"]]
        self.assertEqual(item.text(0), "Wi-Fi\n10.20.30.57")
        self.assertTrue(w.inspector.btnQueue.isHidden())          # varsayilan: dogrudan
        w.actQueueMode.setChecked(True)
        self.assertFalse(w.inspector.btnQueue.isHidden())
        w.actQueueMode.setChecked(False)

    def test_undo_redo(self):
        w = self.win
        eth = self.id["ETH"]
        w.queue(w._ics_change(self.id["Wi-Fi"], eth))
        from networkplus.core.changes import Change, ChangeKind
        w.queue(Change(ChangeKind.MTU, eth, {"mtu": 1400}))
        self.assertEqual(len(w.changes), 2)
        w.actUndo.trigger()
        self.assertEqual(len(w.changes), 1)
        self.assertEqual(len(w.diagram._preview_items), 1)     # ICS hala kuyrukta
        w.actUndo.trigger()
        self.assertEqual(len(w.changes), 0)
        self.assertFalse(w.actUndo.isEnabled())
        w.actRedo.trigger()
        w.actRedo.trigger()
        self.assertEqual(len(w.changes), 2)
        w._clear_changes()
        self.assertEqual(len(w.changes), 0)
        w.actUndo.trigger()                                     # "Tumunu at" da geri alinir
        self.assertEqual(len(w.changes), 2)

    def test_ics_preview_edge(self):
        w = self.win
        w.queue(w._ics_change(self.id["Wi-Fi"], self.id["ETH"]))
        self.assertEqual(len(w.diagram._preview_items), 1)
        w.diagram.select(self.id["ETH"])
        self.assertEqual(w.inspector.cmbShareFrom.currentData(), self.id["Wi-Fi"])

    def _dialog(self, change=None, **job_kwargs):
        from networkplus.core.changes import build_plan
        from networkplus.platform import render_apply_script
        from networkplus.ui.modules.apply_dialog.apply_dialog import ApplyDialog
        w = self.win
        w.queue(change or w._ics_change(self.id["Wi-Fi"], self.id["ETH"]))
        plan = build_plan(w.changes, w.topology)
        script = render_apply_script(plan, w.topology)
        jobs = []

        def factory(confirm_seconds):
            # Testin istedigi sure (ör. 1 sn) yoksa pencerenin sectigi sure.
            job_kwargs.setdefault("confirm_seconds", confirm_seconds)
            jobs.append(FakeJob(script, **job_kwargs))
            return jobs[0]
        dlg = ApplyDialog(plan, w.topology, script, factory, w)
        dlg.show()
        return dlg, jobs

    def test_low_risk_change_skips_confirmation(self):
        """Kablosu takili olmayan ETH'yi DHCP'ye almak: onay beklenmez (kullanici geri bildirimi)."""
        from networkplus.core.changes import Change, ChangeKind
        dlg, jobs = self._dialog(Change(ChangeKind.IPV4, self.id["ETH"], {"mode": "dhcp"}))
        self.assertFalse(dlg.chkConfirm.isChecked())
        dlg.btnApply.click()
        self.assertTrue(spin_until(lambda: dlg.state == "done"))
        self.assertEqual(dlg.outcome, "kept")
        self.assertEqual(jobs[0].confirm_seconds, 0)
        dlg.close()

    def test_risky_change_asks_confirmation(self):
        from networkplus.core.changes import Change, ChangeKind
        dlg, _ = self._dialog(Change(ChangeKind.MTU, self.id["Wi-Fi"], {"mtu": 1400}))
        self.assertTrue(dlg.chkConfirm.isChecked())
        self.assertIn("Wi-Fi", dlg.lblConfirmReason.text())
        dlg.close()

    def test_static_mode_fills_mask_and_cidr(self):
        insp = self.win.inspector
        self.win.diagram.select(self.id["Ethernet 3"])
        insp.cmbIpv4Mode.setCurrentIndex(1)
        insp.edMask.clear()
        insp._on_mode_chosen(1)
        self.assertEqual(insp.edMask.text(), "255.255.255.0")
        insp.edIpAddress.setText("10.20.30.40/16")
        insp._on_ip_finished()
        self.assertEqual((insp.edIpAddress.text(), insp.edMask.text()), ("10.20.30.40", "255.255.0.0"))
        insp.edMask.setText("24")
        insp._on_mask_finished()
        self.assertEqual(insp.edMask.text(), "255.255.255.0")
        self.assertIn("10.20.30.1", insp.edGateway.placeholderText())
        self.assertEqual(insp.edGateway.text(), "")          # ag gecidi otomatik YAZILMAZ

    def test_apply_keep(self):
        dlg, jobs = self._dialog()
        self.assertTrue(dlg.btnApply.isEnabled())
        dlg.btnApply.click()
        self.assertTrue(spin_until(lambda: dlg.state == "confirm"))
        self.assertIn("uygulandı", dlg._step_items[0].text(1))
        dlg.btnKeep.click()
        self.assertTrue(spin_until(lambda: dlg.state == "done"))
        self.assertEqual(dlg.outcome, "kept")
        self.assertIn("Enable-Sharing", jobs[0].script)
        dlg.close()

    def test_apply_revert_and_timeout(self):
        dlg, _ = self._dialog(fail_step=True)
        dlg.btnApply.click()
        self.assertTrue(spin_until(lambda: dlg.state == "confirm"))
        self.assertIn("başarısız", dlg.lblHeadline.text())
        dlg.btnRevert.click()
        self.assertTrue(spin_until(lambda: dlg.state == "done"))
        self.assertEqual(dlg.outcome, "reverted")
        dlg.close()

        dlg, _ = self._dialog(confirm_seconds=1)
        dlg.btnApply.click()
        self.assertTrue(spin_until(lambda: dlg.state == "done", 10000))
        self.assertEqual(dlg.outcome, "reverted")
        self.assertIn("süre doldu", dlg.lblHeadline.text())
        dlg.close()

    def test_dialog_cannot_close_while_confirming(self):
        dlg, jobs = self._dialog()
        dlg.btnApply.click()
        self.assertTrue(spin_until(lambda: dlg.state == "confirm"))
        dlg.reject()
        self.assertTrue(dlg.isVisible())
        jobs[0].keep()
        self.assertTrue(spin_until(lambda: dlg.state == "done"))
        dlg.close()


if __name__ == "__main__":
    unittest.main()
