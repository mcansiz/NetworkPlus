"""Ana pencere: modulleri (diyagram, liste, inspector) birbirine baglar.

Yerlesim main_window.ui'da; moduller oraya 'promote' edilmis widget olarak
yerlesir ve her biri kendi .ui dosyasini yukler (ADR 0006).
"""

from __future__ import annotations

import json
import sys
import weakref
from pathlib import Path

from PyQt5.QtCore import QEvent, QPoint, QSettings, Qt, QTimer
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox, QUndoCommand,
    QUndoStack,
)

from .... import __version__
from ....core.changes import (
    SUPPORTED, Change, ChangeKind, ChangeSet, HOST_TARGET, build_plan, current_ipv4, describe,
    needs_confirmation, next_bridge_name,
)
from ....app import ELEVATE_ON_START_KEY
from ....core.dhcp.guard import CLIENTS_PREFIX, apply_overlay, eligible_adapters
from ....core.model import Edge, EdgeKind, NodeKind, Status, Topology
from ....platform import (
    Collector, apply_support, autostart_mode, autostart_modes, elevation_state, get_collector,
    UnsupportedCollector, prepare_apply, relaunch_as_admin, set_autostart_mode,
)
from ....platform.filesource import FileCollector
from ...tray import TrayController, diff_notifications
from ....core.i18n import tr
from ...uiloader import load_ui, require
from ...worker import SnapshotThread
from ..apply_dialog.apply_dialog import ApplyDialog
from ...apply_runner import ApplyRunner
from ...dhcp_service import DhcpService, ensure_windows_firewall

_NOT_SHAREABLE = {NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.BRIDGE, NodeKind.CONTAINER}

AUTO_REFRESH_MS = 30_000
BACKGROUND_REFRESH_MS = 60_000      # bildirimler icin (tepsideyken de)
CONFIRM_SECONDS = 30                # riskli degisiklikte geri alma suresi
STATE_VERSION = 4                   # varsayilan yerlesim degisince artirilir (4: Ozellikler solda, DHCP sagda)
DEFAULT_SIDE_WIDTH = 410           # varsayilan yerlesimde sol ve sag panel genisligi
LAYOUT_SAVE_DELAY_MS = 800          # panel tasininca/acilip kapaninca yerlesim bu kadar sonra kaydedilir


class _QueueCommand(QUndoCommand):
    """Kuyrugun once/sonra durumu. Ilk redo(), push aninda cagrilir; durum zaten 'sonra'dir.

    Pencereye ZAYIF referans: komutun sahibi C++ QUndoStack'tir; guclu referans
    pencere <-> yigin <-> komut dongusu kurar ve cop toplayici bunu cozerken
    PyQt ayni nesneyi iki kez siler (testte access violation olarak yakalandi).
    """

    def __init__(self, win: "MainWindow", text: str, before: dict, after: dict):
        super().__init__(text)
        self._win = weakref.ref(win)
        self.before, self.after = before, after

    def _restore(self, state: dict):
        win = self._win()
        if win is not None:
            win.changes.restore(state)
            win._changes_updated()

    def undo(self):
        self._restore(self.before)

    def redo(self):
        self._restore(self.after)


class MainWindow(QMainWindow):
    def __init__(self, collector: Collector, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "diagram", "adapterList", "inspector", "changesPanel", "dockAdapters",
                "dockInspector", "dockChanges", "menuView", "actRefresh", "actAutoRefresh",
                "actShowHidden", "actRelayout", "actFit", "actOpenSnapshot", "actSaveSnapshot",
                "actExportPng", "actLive", "actAbout", "actApply", "actClearChanges",
                "actUndo", "actRedo", "actRelaunchAdmin", "actQuit", "actQuitApp", "actTrayShow",
                "menuTray", "menuAutostart", "actAutostartOff", "actAutostartUser", "actAutostartAdmin",
                "actCloseToTray", "actNotifications", "menuLanguage", "actLanguageAuto",
                "dockDiagram", "confirmBar", "actElevateOnStart", "actConfirmRisky", "actQueueMode",
                "actReviewPlan", "dockDhcp", "dhcpPanel", "mainToolBar", "actResetLayout", "menuChanges",
                "menuTheme", "actThemeAuto", "actThemeSystem", "actOpenThemesFolder")
        self.collector = collector
        self.topology: Topology | None = None
        self.changes = ChangeSet()
        # Geri al/yinele KUYRUK duzenlemelerini kapsar; uygulanmis degisiklikler
        # Uygula penceresindeki koru/geri al ile yonetilir.
        self.undo = QUndoStack(self)
        self._thread: SnapshotThread | None = None
        self._first_load_callbacks = []

        # Diyagram da tasinabilir bir panel (kullanici istegi); merkez bos ve gizli.
        self.centralWidget().hide()
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)
        self.menuView.addAction(self.dockDiagram.toggleViewAction())
        self.menuView.addAction(self.dockAdapters.toggleViewAction())
        self.menuView.addAction(self.dockInspector.toggleViewAction())
        self.menuView.addAction(self.dockChanges.toggleViewAction())
        self.menuView.addAction(self.dockDhcp.toggleViewAction())
        act_dhcp = self.dockDhcp.toggleViewAction()
        self.mainToolBar.insertAction(self.actUndo, act_dhcp)
        self.mainToolBar.insertSeparator(self.actUndo)
        self.inspector.set_changes(self.changes)
        self.lblSource = QLabel()
        self.lblErrors = QLabel()
        self.lblAdmin = QLabel()
        self.statusBar().addPermanentWidget(self.lblErrors)
        self.statusBar().addPermanentWidget(self.lblAdmin)
        self.statusBar().addPermanentWidget(self.lblSource)
        self.elevated, can_relaunch = elevation_state()
        self.lblAdmin.setText(tr("Yönetici") if self.elevated else "")
        self.lblAdmin.setToolTip(tr("Uygulama yönetici olarak çalışıyor: Uygula izin sormaz."))
        self.actRelaunchAdmin.setVisible(can_relaunch)
        self.actRelaunchAdmin.triggered.connect(self._relaunch_admin)

        self._timer = QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

        # Eylemler
        self.actRefresh.triggered.connect(self.refresh)
        self.actAutoRefresh.toggled.connect(lambda on: self._timer.start() if on else self._timer.stop())
        self.actShowHidden.toggled.connect(self._set_show_hidden)
        self.actRelayout.triggered.connect(self.diagram.relayout)
        self.actFit.triggered.connect(self.diagram.view.fit_all)
        self.actOpenSnapshot.triggered.connect(self._open_snapshot)
        self.actSaveSnapshot.triggered.connect(self._save_snapshot)
        self.actExportPng.triggered.connect(self._export_png)
        self.actLive.triggered.connect(self._go_live)
        self.actAbout.triggered.connect(self._about)

        # Moduller arasi secim senkronu
        self.diagram.nodeSelected.connect(self._on_node_selected)
        self.diagram.edgeSelected.connect(self._on_edge_selected)
        self.diagram.selectionCleared.connect(self._on_selection_cleared)
        self.adapterList.nodeActivated.connect(self._on_list_activated)
        self.adapterList.showHiddenToggled.connect(self.actShowHidden.setChecked)

        # Degisiklik kuyrugu (M2)
        self.inspector.formSubmitted.connect(self._on_form_submitted)
        self.inspector.formApplyRequested.connect(self._on_form_apply)
        self.changesPanel.applyRequested.connect(self._apply)
        self.changesPanel.removeRequested.connect(self._remove_changes)
        self.changesPanel.clearRequested.connect(self._clear_changes)
        self.actApply.triggered.connect(self._apply)
        self.actClearChanges.triggered.connect(self._clear_changes)
        self.actUndo.triggered.connect(self.undo.undo)
        self.actRedo.triggered.connect(self.undo.redo)
        self.undo.canUndoChanged.connect(self.actUndo.setEnabled)
        self.undo.canRedoChanged.connect(self.actRedo.setEnabled)
        self.undo.undoTextChanged.connect(
            lambda t: self.actUndo.setToolTip(tr("Geri al: {what}").format(what=t) if t else tr("Geri al")))
        self.undo.redoTextChanged.connect(
            lambda t: self.actRedo.setToolTip(tr("Yinele: {what}").format(what=t) if t else tr("Yinele")))
        self.actUndo.setEnabled(False)
        self.actRedo.setEnabled(False)
        self.diagram.connectRequested.connect(self._on_connect_requested)
        self.diagram.nodeContextMenu.connect(self._node_menu)
        self.diagram.edgeContextMenu.connect(self._edge_menu)
        self.diagram.nodePowerRequested.connect(self._toggle_power)
        self.diagram.nodePropertiesRequested.connect(self.show_node)

        # Dogrudan uygulama (pencere yok): serit + arka plan isi
        self.runner = ApplyRunner(self)
        self.runner.applied.connect(self._on_runner_applied)
        self.runner.needConfirm.connect(self._on_runner_confirm)
        self.runner.finished.connect(self._on_runner_finished)
        self.runner.failedToStart.connect(self._on_runner_failed)
        self.confirmBar.keepClicked.connect(self.runner.keep)
        self.confirmBar.revertClicked.connect(self._on_bar_revert)
        self.actReviewPlan.triggered.connect(self._review_plan)
        self.actQueueMode.toggled.connect(self._sync_queue_mode)
        self.actElevateOnStart.toggled.connect(
            lambda on: QSettings().setValue(ELEVATE_ON_START_KEY, on))

        # DHCP sunucusu (ADR 0010): ayri surec; panel arayuz, burada statik IP + diyagram + tepsi
        self.dhcp_service = DhcpService(self)
        # Zayif referans: panel (pencerenin cocugu) pencereyi guclu tutarsa kapanista cift silme olur.
        wself = weakref.ref(self)
        self.dhcpPanel.attach(self.dhcp_service,
                              lambda: wself()._dhcp_preflight() if wself() is not None else (True, ""))
        self.dhcpPanel.staticIpRequested.connect(self._dhcp_static_ip)
        self.dhcpPanel.refreshRequested.connect(self.refresh)
        self.dhcpPanel.clientsChanged.connect(self._dhcp_overlay_changed)

        # Sistem tepsisi, bildirimler, sistemle baslatma
        self._quitting = False
        self.tray = TrayController(self)
        self.actQuit.triggered.connect(self.quit_app)
        self.actQuitApp.triggered.connect(self.quit_app)
        self.actTrayShow.triggered.connect(self.show_window)
        self._bg_timer = QTimer(self)                  # bildirimler icin arka plan okuma
        self._bg_timer.setInterval(BACKGROUND_REFRESH_MS)
        self._bg_timer.timeout.connect(self._background_refresh)
        self.actNotifications.toggled.connect(self._sync_bg_timer)
        self.dhcpPanel.leaseNotification.connect(self._dhcp_notify)
        self._setup_autostart_menu()
        self._setup_language_menu()
        self._setup_theme_menu()

        # Kullanici yerlesimi hatirlanir (kullanici istegi 2026-10-01): yalniz kapanista degil,
        # panel tasininca/acilip kapaninca da kaydedilir; oturum kapanirken (tepsideyken) de.
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(LAYOUT_SAVE_DELAY_MS)
        self._layout_timer.timeout.connect(self._save_layout)
        for dock in self._docks():
            dock.dockLocationChanged.connect(self._schedule_layout_save)
            dock.topLevelChanged.connect(self._schedule_layout_save)
            dock.visibilityChanged.connect(self._schedule_layout_save)
        self.actResetLayout.triggered.connect(self.reset_layout)
        for act in (self.actShowHidden, self.actAutoRefresh, self.actCloseToTray, self.actNotifications,
                    self.actConfirmRisky, self.actQueueMode):
            act.toggled.connect(self._save_settings)
        app = QApplication.instance()
        app.aboutToQuit.connect(self._save_state)
        app.commitDataRequest.connect(self._on_commit_data)

        self._update_source_label()
        self._restore_state()
        self._sync_bg_timer()
        self._sync_queue_mode()
        self._changes_updated()

    # ----------------------------------------------------------------- yenileme
    def refresh(self):
        if self._thread is not None and self._thread.isRunning():
            # Okuma surerken gelen istek (ör. uygulama bitti) KAYBOLMASIN: suren okuma degisiklikten
            # once baslamis olabilir; bitince bir kez daha okunur (VM'de DHCP akisinda yakalandi).
            self._refresh_again = True
            return
        self._refresh_again = False
        self.actRefresh.setEnabled(False)
        self.statusBar().showMessage(tr("Ağ durumu okunuyor…"))
        self._thread = SnapshotThread(self.collector, self)
        self._thread.done.connect(self._on_snapshot)
        self._thread.failed.connect(self._on_failed)
        # Bagli metot (lambda degil): pencere silinince PyQt baglantiyi koparir; kuyruktaki
        # 'finished' silinmis pencereye ulasip sureci cokertmez (testte yakalandi).
        self._thread.finished.connect(self._on_refresh_finished)
        self._thread.start()

    def _on_refresh_finished(self):
        self.actRefresh.setEnabled(True)
        if getattr(self, "_refresh_again", False):
            self.refresh()

    def when_loaded(self, callback):
        """Ilk topoloji yuklenince bir kez cagrilir (ekran goruntusu, testler)."""
        self._first_load_callbacks.append(callback)

    def _on_snapshot(self, topo: Topology, seconds: float):
        previous, self.topology = self.topology, topo
        self.dhcpPanel.set_live(self._dhcp_live())
        self.dhcpPanel.set_topology(topo)
        self._apply_dhcp_overlay(topo)
        self.tray.update(topo)
        if self.actNotifications.isChecked() and not isinstance(self.collector, FileCollector):
            for title, msg, warn in diff_notifications(previous, topo):
                self.tray.notify(title, msg, warn)
        show_hidden = self.actShowHidden.isChecked()
        self.inspector.set_topology(topo)
        self.adapterList.set_topology(topo)
        self.diagram.set_topology(topo, show_hidden)

        current = self.diagram.selected_id()
        if current in topo.nodes:
            self.inspector.show_node(current)
        elif current:
            self.inspector.show_edge(current)
        else:
            self.inspector.clear()

        via = topo.nodes.get(topo.internet_via or "")
        adapters = [n for n in topo.nodes.values() if n.is_adapter]
        visible = [n for n in adapters if show_hidden or not n.hidden]
        route = tr("İnternet: {name} üzerinden").format(name=via.label) if via else tr("İnternet çıkışı yok")
        self.statusBar().showMessage(
            tr("{route} · {visible}/{total} bağdaştırıcı görünür · okuma {seconds} sn").format(
                route=route, visible=len(visible), total=len(adapters), seconds=f"{seconds:.1f}"))
        errors = topo.errors
        self.lblErrors.setText(tr("⚠ {count} bölüm okunamadı").format(count=len(errors)) if errors else "")
        self.lblErrors.setToolTip("\n".join(f"{e.get('section')}: {e.get('message')}" for e in errors))
        self._changes_updated()

        callbacks, self._first_load_callbacks = self._first_load_callbacks, []
        for cb in callbacks:
            cb()

    def _on_failed(self, message: str):
        self.statusBar().showMessage(tr("Ağ durumu okunamadı."))
        QMessageBox.warning(self, "networkPlus", tr("Ağ durumu okunamadı:") + f"\n\n{message}")

    # ----------------------------------------------------------------- secim
    def _on_node_selected(self, node_id: str):
        self.inspector.show_node(node_id)
        self.adapterList.select(node_id)

    def _on_edge_selected(self, edge_id: str):
        self.inspector.show_edge(edge_id)
        self.adapterList.select("")

    def _on_selection_cleared(self):
        self.inspector.clear()
        self.adapterList.select("")

    def _on_list_activated(self, node_id: str):
        node = self.topology.nodes.get(node_id) if self.topology else None
        if node is not None and node.hidden and not self.actShowHidden.isChecked():
            self.actShowHidden.setChecked(True)
        self.diagram.select(node_id)
        self.inspector.show_node(node_id)

    def _set_show_hidden(self, value: bool):
        self.adapterList.set_show_hidden(value)
        self.diagram.set_show_hidden(value)

    # ----------------------------------------------------------------- degisiklik kuyrugu
    def _mutate(self, text: str, fn) -> bool:
        """Kuyrugu degistiren TEK nokta: once/sonra durumunu geri al yiginina yazar."""
        before = self.changes.items()
        fn()
        after = self.changes.items()
        if before == after:
            self._changes_updated()
            return False
        self.undo.push(_QueueCommand(self, text, before, after))
        return True

    def queue(self, *changes: Change, message: str = ""):
        if not changes:
            return
        text = message or describe(changes[0], self.topology) + (
            f" (+{len(changes) - 1})" if len(changes) > 1 else "")

        def add():
            for c in changes:
                self.changes.add(c)
        self._mutate(text, add)
        self.statusBar().showMessage(tr("Kuyruğa eklendi: {what}").format(what=text), 6000)

    def _on_form_submitted(self, node_id: str, add: list, remove: list):
        def apply_form():
            for key in remove:
                self.changes.remove(tuple(key))
            for c in add:
                self.changes.add(c)
        label = self.topology.nodes[node_id].label if self.topology and node_id in self.topology.nodes else node_id
        if not self._mutate(tr("{name}: form").format(name=label), apply_form):
            self.statusBar().showMessage(tr("Formda değişiklik yok."), 4000)

    def _remove_changes(self, keys: list):
        self._mutate(tr("Kuyruktan çıkar"), lambda: [self.changes.remove(tuple(k)) for k in keys])

    def _clear_changes(self):
        self._mutate(tr("Tümünü at"), self.changes.clear)

    def _changes_updated(self):
        topo = self.topology
        self.changesPanel.show_changes(self.changes, topo)
        count = len(self.changes)
        self.dockChanges.setWindowTitle(tr("Bekleyen değişiklikler ({count})").format(count=count) if count
                                        else tr("Bekleyen değişiklikler"))
        reason = ""
        if topo is not None:
            ok, reason = apply_support(topo, self.collector)
        self.changesPanel.set_apply_block(reason)
        self.actApply.setEnabled(count > 0 and not reason)
        self.actClearChanges.setEnabled(count > 0)
        if topo is None:
            return
        targets = self.changes.targets()
        previews: list[Edge] = []
        for c in self.changes:
            if c.kind != ChangeKind.ICS:
                continue
            # Kapatilacak/degisecek mevcut paylasim da isaretlenir.
            targets |= {n.id for n in topo.nodes.values() if n.props.get("sharing")}
            if c.params.get("public") and c.params.get("private"):
                previews.append(Edge(c.params["public"], c.params["private"], EdgeKind.ICS,
                                     tr("ICS · bekliyor"), False, [tr("Kuyruktaki değişiklik")]))
        self.diagram.set_pending(targets, previews)
        self.inspector.refresh_pending()

    def _apply(self):
        """Kuyruktaki tum degisiklikleri pencere acmadan uygula."""
        if len(self.changes):
            self.apply_now(list(self.changes), from_queue=True)

    # ----------------------------------------------------------------- dogrudan uygulama
    def submit(self, *changes: Change):
        """Menuden / diyagramdan gelen degisiklik: toplu kipte kuyruga, degilse hemen uygula."""
        if self.actQueueMode.isChecked():
            self.queue(*changes)
        else:
            self.apply_now(list(changes))

    def _on_form_apply(self, node_id: str, changes: list):
        if not changes:
            self.statusBar().showMessage(tr("Formda değişiklik yok."), 4000)
            return
        self.apply_now(changes)

    def _apply_support(self) -> tuple[bool, str]:
        return apply_support(self.topology, self.collector)

    def _create_job(self, plan, confirm_seconds: int):
        """Testler bunu sahte isle degistirir."""
        return prepare_apply(plan, self.topology).create_job(confirm_seconds)

    def apply_now(self, changes: list[Change], from_queue: bool = False) -> bool:
        """Pencere ACMADAN uygula. Riskli degisiklikte (ayar aciksa) serit Koru/Geri al sorar."""
        topo = self.topology
        if topo is None or not changes:
            return False
        if self.runner.busy:
            self.confirmBar.show_error(tr("Önceki işlem sürüyor; bitince tekrar deneyin."))
            return False
        cs = ChangeSet()
        for c in changes:
            cs.add(c)
        plan = build_plan(cs, topo)
        if plan.blocked:
            first = next(i.message for it in plan.items for i in it.issues if i.severity.value == "error")
            self.confirmBar.show_error(first)
            return False
        ok, reason = self._apply_support()
        if not ok:
            self.confirmBar.show_error(reason)
            return False
        risky, why = needs_confirmation(plan, topo)
        seconds = CONFIRM_SECONDS if (risky and self.actConfirmRisky.isChecked()) else 0
        try:
            job = self._create_job(plan, seconds)
        except ValueError as exc:
            self.confirmBar.show_error(tr("Betik üretilemedi: {error}").format(error=exc))
            return False
        titles = "; ".join(i.title for i in plan.items)
        self._apply_ctx = {"plan": plan, "why": why, "titles": titles, "from_queue": from_queue,
                           "keys": [c.key for c in plan.changes]}
        self.confirmBar.show_busy(tr("Uygulanıyor: {what}").format(what=titles) + (
            "" if self.elevated else " — " + tr("yönetici izni isteniyor")))
        self.runner.run(job)
        return True

    def _on_runner_applied(self, steps: list):
        failed = [s for s in steps if not s.get("ok")]
        if failed:
            self.statusBar().showMessage(tr("Bazı adımlar başarısız: {details}").format(
                details="; ".join(f"{s.get('title')}: {s.get('error')}" for s in failed)), 10000)

    def _on_runner_confirm(self, seconds: int):
        ctx = getattr(self, "_apply_ctx", {})
        self.confirmBar.show_confirm(seconds, tr("Uygulandı: {what}. {why} Çalışıyorsa “Koru”ya basın; "
                                                  "yanıt gelmezse geri alınır.").format(
            what=ctx.get("titles", ""), why=ctx.get("why", "")))

    def _on_bar_revert(self):
        if self.runner.busy:
            self.runner.revert()                       # onay suresi icinde: betik geri alir
            return
        ctx = getattr(self, "_apply_ctx", {})          # hata sonrasi: geri alma adimlarini ayrica uygula
        plan = ctx.get("plan")
        if plan is not None and plan.rollback:
            self.apply_now(plan.rollback)

    def _on_runner_finished(self, outcome: str, steps: list, rolled: list):
        ctx = getattr(self, "_apply_ctx", {})
        failed = [s for s in steps if not s.get("ok")]
        if ctx.get("dhcp"):
            ok = outcome == "kept" and not failed
            if ok and getattr(self, "_dhcp_steps", []):
                QTimer.singleShot(0, self._dhcp_next_step)          # sonraki adim (etkinlestir)
            else:
                self._dhcp_steps = []
                self.dhcpPanel.on_static_result(ok, "; ".join(str(s.get("error")) for s in failed))
        if outcome == "kept" and not failed:
            self.confirmBar.show_info(tr("Uygulandı: {what}").format(what=ctx.get("titles", "")))
            if ctx.get("from_queue"):
                for key in ctx.get("keys", []):
                    self.changes.remove(tuple(key))
                self.undo.clear()
                self._changes_updated()
        elif outcome == "reverted":
            bad = [r for r in rolled if not r.get("ok")]
            if bad:
                self.confirmBar.show_error(tr("Bazı geri alma adımları başarısız: {details}").format(
                    details="; ".join(f"{r.get('title')}: {r.get('error')}" for r in bad)))
            else:
                self.confirmBar.show_info(tr("Geri alındı: ayarlar önceki hâline döndü."))
        else:
            done = [s for s in steps if s.get("ok")]
            msg = "; ".join(f"{s.get('title')}: {s.get('error')}" for s in failed) or tr("bilinmeyen hata")
            self.confirmBar.show_error(tr("Uygulanamadı: {details}").format(details=msg), can_revert=bool(done))
        self.refresh()

    def _on_runner_failed(self, message: str):
        self.confirmBar.show_error(tr("Uygulanamadı: {details}").format(details=message))
        if getattr(self, "_apply_ctx", {}).get("dhcp"):
            self.dhcpPanel.on_static_result(False, message)

    # ----------------------------------------------------------------- DHCP sunucusu
    def _dhcp_live(self) -> bool:
        """Sunucu yalniz canli sistemde (dosyadan goruntude degil). Testler bunu degistirir."""
        return not isinstance(self.collector, FileCollector)

    def _dhcp_preflight(self) -> tuple[bool, str]:
        """Windows: gelen UDP 67 icin guvenlik duvari kurali (testler bunu degistirir)."""
        if sys.platform == "win32":
            return ensure_windows_firewall(self.elevated)
        return True, ""

    def _dhcp_static_ip(self, node_id: str, address: str, prefix: int):
        """Sunucu icin statik IP; kart etkin degilse (Linux) SONRA etkinlestir. Iki ayri uygulama:
        tek planda etkinlestirme once calisir ve eski DHCP profiliyle adres beklerdi."""
        steps = [[Change(ChangeKind.IPV4, node_id, {"mode": "static", "address": address, "prefix": prefix,
                                                     "gateway": None})]]
        node = self.topology.nodes.get(node_id) if self.topology else None
        if node is not None and node.status == Status.DISABLED:
            steps.append([Change(ChangeKind.ENABLED, node_id, {"enabled": True})])
        self._dhcp_steps = steps
        self._dhcp_next_step()

    def _dhcp_next_step(self):
        steps = getattr(self, "_dhcp_steps", [])
        if not steps:
            return
        if self.apply_now(steps.pop(0)):
            self._apply_ctx["dhcp"] = True
        else:
            self._dhcp_steps = []
            self.dhcpPanel.on_static_result(False, "")

    def _apply_dhcp_overlay(self, topo: Topology):
        ov = self.dhcpPanel.overlay()
        apply_overlay(topo, *(ov if ov else (None,)))

    def _dhcp_overlay_changed(self):
        topo = self.topology
        if topo is None:
            return
        self._apply_dhcp_overlay(topo)
        self.diagram.set_topology(topo)
        current = self.diagram.selected_id()
        if current and current.startswith(CLIENTS_PREFIX) and current in topo.nodes:
            self.inspector.set_topology(topo)
            self.inspector.show_node(current)

    def _dhcp_notify(self, title: str, message: str):
        if self.actNotifications.isChecked():
            self.tray.notify(title, message)
        self.statusBar().showMessage(f"{title}: {message}", 8000)

    def show_dhcp(self, node_id: str = ""):
        self.show_window()
        if node_id and not self.dhcpPanel.select_adapter(node_id):
            self.statusBar().showMessage(tr("DHCP sunucusu başka bir kartta çalışıyor; önce durdurun."), 6000)
        self.dockDhcp.show()
        self.dockDhcp.raise_()

    def _sync_queue_mode(self, *_):
        on = self.actQueueMode.isChecked()
        self.dockChanges.setVisible(on or bool(len(self.changes)))
        # Toplu kip kapaliyken Degisiklikler menusu bos kaliyordu: menu ve panel anahtari gizlenir.
        self.dockChanges.toggleViewAction().setVisible(on)
        self.menuChanges.menuAction().setVisible(on)
        self.inspector.set_queue_mode(on)
        for act in (self.actApply, self.actReviewPlan, self.actClearChanges, self.actUndo, self.actRedo):
            act.setVisible(on)

    def _review_plan(self):
        """Istege bagli: plan + betik penceresi (eski akis), kuyruk icin."""
        topo = self.topology
        if topo is None or not len(self.changes):
            return
        ok, reason = apply_support(topo, self.collector)
        if not ok:
            QMessageBox.information(self, "networkPlus", reason)
            return
        plan = build_plan(self.changes, topo)
        try:
            bundle = prepare_apply(plan, topo)
        except ValueError as exc:
            QMessageBox.warning(self, "networkPlus", tr("Betik üretilemedi: {error}").format(error=exc))
            return
        dlg = ApplyDialog(plan, topo, bundle.preview, bundle.create_job, self,
                          script_suffix=bundle.suffix, elevated=self.elevated)
        dlg.exec_()
        if dlg.outcome == "kept":
            # Uygulanan degisiklikler kuyruk gecmisinden de cikar (geri al onlari geri getirmesin).
            self.changes.clear()
            self.undo.clear()
            self._changes_updated()
        if dlg.outcome in ("kept", "reverted", "failed"):
            self.refresh()

    # ----------------------------------------------------------------- menuler
    def _ics_change(self, public: str | None, private: str | None) -> Change:
        return Change(ChangeKind.ICS, HOST_TARGET, {"public": public, "private": private})

    def _on_connect_requested(self, src: str, dst: str, pos: QPoint):
        topo = self.topology
        a, b = topo.nodes[src], topo.nodes[dst]
        menu = QMenu(self)
        title = menu.addAction(f"{a.label}  →  {b.label}")
        title.setEnabled(False)
        menu.addSeparator()
        act_ics = menu.addAction(tr("İnterneti paylaş (ICS): {source} → {target}").format(source=a.label, target=b.label))
        if a.kind in _NOT_SHAREABLE or b.kind in _NOT_SHAREABLE:
            act_ics.setEnabled(False)
        pending_bridge = next((c for c in self.changes if c.kind == ChangeKind.BRIDGE_CREATE
                               and (src in c.params["members"] or dst in c.params["members"])), None)
        bridge_text = (tr("{bridge} köprüsüne ekle").format(bridge=pending_bridge.target) if pending_bridge
                       else tr("Köprü oluştur: {a} + {b}").format(a=a.label, b=b.label))
        act_bridge = menu.addAction(bridge_text)
        if ChangeKind.BRIDGE_CREATE not in SUPPORTED.get(topo.platform, set()):
            act_bridge.setEnabled(False)
            act_bridge.setText(bridge_text + " " + tr("(bu platformda yok)"))
        chosen = menu.exec_(pos)
        if chosen is act_ics:
            self.submit(self._ics_change(src, dst))
            self.diagram.select(dst, center=False)
        elif chosen is act_bridge:
            self.submit(self._bridge_change([src, dst], pending_bridge))

    def _bridge_change(self, members: list[str], pending: Change | None) -> Change:
        """Yeni kopru ya da bekleyen kopruye uye ekleme. IP ayari ilk uyeden devralinir."""
        topo = self.topology
        if pending is not None:
            merged = list(dict.fromkeys(pending.params["members"] + members))
            return Change(ChangeKind.BRIDGE_CREATE, pending.target, {**pending.params, "members": merged})
        first = topo.nodes[members[0]]
        ip = current_ipv4(topo, first.id).params
        if ip.get("mode") == "static" and not ip.get("address"):
            ip = {"mode": "disabled"}
        return Change(ChangeKind.BRIDGE_CREATE, next_bridge_name(topo, self.changes),
                      {"members": members, "ipv4": ip})

    def _node_menu(self, node_id: str, pos: QPoint):
        topo = self.topology
        node = topo.nodes.get(node_id) if topo else None
        if node is None:
            return
        menu = QMenu(self)
        act_props = menu.addAction(tr("Özellikler"))
        actions: dict = {}
        act_dhcp = None
        if node.kind == NodeKind.DHCP_CLIENTS:
            act_dhcp = menu.addAction(tr("DHCP sunucusu…"))
        elif any(n.id == node.id for n in eligible_adapters(topo)):
            act_dhcp = menu.addAction(tr("DHCP sunucusu…"))
        if node.is_adapter:
            menu.addSeparator()
            disabled = node.status == Status.DISABLED
            actions[menu.addAction(tr("Etkinleştir") if disabled else tr("Devre dışı bırak"))] = \
                Change(ChangeKind.ENABLED, node.id, {"enabled": disabled})
            if not node.props.get("dhcp4"):
                actions[menu.addAction(tr("IPv4 adresini otomatik al (DHCP)"))] = \
                    Change(ChangeKind.IPV4, node.id, {"mode": "dhcp"})
            elif node.status == Status.UP:
                actions[menu.addAction(tr("DHCP adresini yenile"))] = Change(ChangeKind.DHCP_RENEW, node.id, {})
            if node.kind == NodeKind.BRIDGE and ChangeKind.BRIDGE_DELETE in SUPPORTED.get(topo.platform, set()):
                actions[menu.addAction(tr("Köprüyü kaldır"))] = Change(
                    ChangeKind.BRIDGE_DELETE, node.label,
                    {"members": [m for m in topo.nodes if topo.nodes[m].props.get("bridge_master") == node.label]})
            if node.props.get("dns4_manual"):
                actions[menu.addAction(tr("DNS sunucularını otomatik al"))] = \
                    Change(ChangeKind.DNS4, node.id, {"mode": "auto"})
            if node.kind not in _NOT_SHAREABLE:
                share = menu.addMenu(tr("Bu bağdaştırıcının internetini paylaş →"))
                for other in sorted(topo.nodes.values(), key=lambda n: n.label.lower()):
                    if other.is_adapter and other.id != node.id and not other.hidden \
                            and other.kind not in _NOT_SHAREABLE:
                        actions[share.addAction(other.label)] = self._ics_change(node.id, other.id)
            if node.props.get("sharing"):
                actions[menu.addAction(tr("İnternet paylaşımını kapat"))] = self._ics_change(None, None)
            pending = [c for c in self.changes if c.target == node.id]
            if pending:
                menu.addSeparator()
                act_drop = menu.addAction(tr("Bu bağdaştırıcının bekleyen değişikliklerini at ({count})").format(count=len(pending)))
                actions[act_drop] = ("drop", [c.key for c in pending])
        chosen = menu.exec_(pos)
        if chosen is None:
            return
        if chosen is act_props:
            self.diagram.select(node_id, center=False)
            self.dockInspector.show()
            return
        if act_dhcp is not None and chosen is act_dhcp:
            self.show_dhcp(node.props.get("adapter", "") if node.kind == NodeKind.DHCP_CLIENTS else node.id)
            return
        payload = actions.get(chosen)
        if isinstance(payload, Change):
            self.submit(payload)
        elif isinstance(payload, tuple) and payload[0] == "drop":
            self._remove_changes(payload[1])

    def _edge_menu(self, edge_id: str, pos: QPoint):
        topo = self.topology
        edge = next((e for e in topo.edges if e.id == edge_id), None) if topo else None
        if edge is None:
            return
        menu = QMenu(self)
        act_props = menu.addAction(tr("Özellikler"))
        act_off = None
        if edge.kind in (EdgeKind.ICS, EdgeKind.HOTSPOT):
            act_off = menu.addAction(tr("Bu paylaşımı kapat"))
        chosen = menu.exec_(pos)
        if chosen is act_props:
            self.diagram.select(edge_id, center=False)
        elif act_off is not None and chosen is act_off:
            self.submit(self._ics_change(None, None))

    # ----------------------------------------------------------------- dosya
    def _update_source_label(self):
        if isinstance(self.collector, FileCollector):
            self.lblSource.setText(tr("Kaynak: {name}").format(name=self.collector.path.name))
            self.setWindowTitle(f"networkPlus — {self.collector.path.name}")
            self.actLive.setEnabled(True)
        else:
            self.lblSource.setText(tr("Kaynak: canlı sistem"))
            self.setWindowTitle("networkPlus")
            self.actLive.setEnabled(False)

    def _open_snapshot(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Anlık görüntü aç"), "", "JSON (*.json)")
        if path:
            self.collector = FileCollector(path)
            self._update_source_label()
            self._changes_updated()
            self.refresh()

    def _go_live(self):
        self.collector = get_collector()
        self._update_source_label()
        self._changes_updated()
        self.refresh()

    def _save_snapshot(self):
        if self.topology is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Anlık görüntü kaydet"), "networkplus-snapshot.json",
                                              "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(self.topology.snapshot, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
            self.statusBar().showMessage(tr("Kaydedildi: {path}").format(path=path), 5000)

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("PNG olarak dışa aktar"), "networkplus.png", "PNG (*.png)")
        if path and self.diagram.export_png(path):
            self.statusBar().showMessage(tr("Dışa aktarıldı: {path}").format(path=path), 5000)

    # ----------------------------------------------------------------- tepsi / pencere
    def show_window(self):
        """Gizli/kucultulmus pencereyi one getir. showNormal() KULLANILMAZ: tam ekrani
        bozup pencereyi kucultuyordu (kullanici bildirdi)."""
        if self.isMinimized():
            self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def show_node(self, node_id: str):
        self.show_window()
        self._on_list_activated(node_id)
        self.dockInspector.show()

    def quick_apply(self, change: Change):
        """Tepsi / diyagram dugmesi: pencere ACMADAN dogrudan uygula."""
        self.apply_now([change])

    def _toggle_power(self, node_id: str):
        node = self.topology.nodes.get(node_id) if self.topology else None
        if node is not None and node.is_adapter:
            self.quick_apply(Change(ChangeKind.ENABLED, node_id, {"enabled": node.status == Status.DISABLED}))

    def quit_app(self):
        self._quitting = True
        self.close()
        QApplication.quit()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_size_on_show", False):
            self._size_on_show = False
            QTimer.singleShot(0, self._apply_default_sizes)

    def changeEvent(self, event):
        # Kucultunce tepsiye (tepsi varsa). getattr: kapanmis pencere cop toplayicida yok edilirken
        # Qt bu olayi yarim silinmis nesneye gonderebiliyor (testte cokme olarak yakalandi).
        tray = getattr(self, "tray", None)
        if event.type() == QEvent.WindowStateChange and tray is not None and self.isMinimized() and tray.available:
            QTimer.singleShot(0, self._hide_to_tray)
        super().changeEvent(event)

    def _hide_to_tray(self):
        self._save_layout()                    # ayirici surukleme gibi sinyalsiz degisiklikler de
        self.hide()
        if not self.tray.told_hidden_once():
            self.tray.notify(tr("networkPlus tepside çalışıyor"),
                             tr("Açmak için simgeye tıklayın; çıkmak için sağ tık › networkPlus'tan çık."))

    def _sync_bg_timer(self, *_):
        # Bildirimler aciksa arka planda da okunur (60 sn); otomatik yenileme ayridir (30 sn).
        if self.actNotifications.isChecked():
            self._bg_timer.start()
        else:
            self._bg_timer.stop()

    def _background_refresh(self):
        # Canli kesfi olmayan sistemde (macOS) her dakika hata penceresi acilmasin.
        if not self.actAutoRefresh.isChecked() and not isinstance(self.collector, (FileCollector, UnsupportedCollector)):
            self.refresh()

    def _setup_autostart_menu(self):
        modes = autostart_modes()
        group = QActionGroup(self)
        group.setExclusive(True)
        self._autostart_actions = {"off": self.actAutostartOff, "user": self.actAutostartUser,
                                   "admin": self.actAutostartAdmin}
        for mode, act in self._autostart_actions.items():
            group.addAction(act)
            act.setVisible(mode in modes)
            act.triggered.connect(lambda _=False, m=mode: self._set_autostart(m))
        self.menuAutostart.menuAction().setVisible(bool(modes))
        self._refresh_autostart_checks()

    def _refresh_autostart_checks(self):
        try:
            mode = autostart_mode()
        except Exception:        # noqa: BLE001 - menu durumu, kritik degil
            mode = "off"
        self._autostart_actions.get(mode, self.actAutostartOff).setChecked(True)

    def _set_autostart(self, mode: str):
        if mode == "admin":
            answer = QMessageBox.question(
                self, "networkPlus",
                tr("networkPlus oturum açılışında ve elle açıldığında UAC sormadan YÖNETİCİ olarak "
                   "çalışacak (Görev Zamanlayıcı). Kurmak için bir kez yönetici izni istenecek.\n\n"
                   "Not: yönetici olarak açık bir uygulamada ağ ayarları UAC sormadan değişir; "
                   "Uygula penceresindeki plan ve geri alma korumaları yine çalışır.\n\nDevam edilsin mi?"))
            if answer != QMessageBox.Yes:
                self._refresh_autostart_checks()
                return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, msg = set_autostart_mode(mode)
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_autostart_checks()
        if ok:
            self.statusBar().showMessage({"off": tr("Sistemle başlatma kapatıldı."),
                                          "user": tr("Oturum açılışında tepside başlayacak."),
                                          "admin": tr("Oturum açılışında yönetici olarak tepside başlayacak.")}[mode], 6000)
        else:
            QMessageBox.warning(self, "networkPlus", tr("Ayarlanamadı: {error}").format(error=msg))

    # ----------------------------------------------------------------- dil (ADR 0008)
    def _setup_language_menu(self):
        from ....i18n import available_languages, language_setting
        group = QActionGroup(self)
        group.setExclusive(True)
        group.addAction(self.actLanguageAuto)
        self._language_actions = {"auto": self.actLanguageAuto}
        for lang in available_languages():            # yeni .ts dosyasi = menude yeni dil
            act = self.menuLanguage.addAction(lang.name)          # dil kendi adiyla, cevrilmez
            act.setObjectName(f"actLang_{lang.code}")
            act.setCheckable(True)
            group.addAction(act)
            self._language_actions[lang.code] = act
        current = language_setting()
        self._language_actions.get(current, self.actLanguageAuto).setChecked(True)
        for code, act in self._language_actions.items():
            act.triggered.connect(lambda _=False, c=code: self._set_language(c))

    # ----------------------------------------------------------------- tema (ADR 0011)
    def _setup_theme_menu(self):
        from ...themes import AUTO, SYSTEM, available_themes, theme_setting
        group = QActionGroup(self)
        group.setExclusive(True)
        self._theme_actions = {AUTO: self.actThemeAuto, SYSTEM: self.actThemeSystem}
        for act in self._theme_actions.values():
            group.addAction(act)
        # Tema satirlari "Tema klasorunu ac"tan onceki ayiricinin ustune girer.
        anchor = self.menuTheme.actions()[-2]
        for theme in available_themes():               # yeni .qss dosyasi = menude yeni tema
            act = QAction(theme.name, self.menuTheme)
            self.menuTheme.insertAction(anchor, act)
            act.setObjectName(f"actTheme_{theme.code}")
            act.setCheckable(True)
            group.addAction(act)
            self._theme_actions[theme.code] = act
        self._theme_actions.get(theme_setting(), self.actThemeAuto).setChecked(True)
        for code, act in self._theme_actions.items():
            act.triggered.connect(lambda _=False, c=code: self.set_theme(c))
        self.actOpenThemesFolder.triggered.connect(self._open_themes_folder)

    def _open_themes_folder(self):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        from ...themes import user_themes_dir
        folder = user_themes_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def set_theme(self, code: str):
        """Temayi hemen uygula (yeniden baslatma gerekmez) ve kaydet."""
        from ...themes import apply_theme, save_theme_setting
        save_theme_setting(code)
        apply_theme(QApplication.instance(), code)
        self._theme_actions[code].setChecked(True)
        # Diyagram ogeleri renkleri cizim aninda paletten alir; lejant HTML'i ve ogeler yeniden kurulur.
        self.diagram.lblLegend.setText(self.diagram._legend_html())
        if self.topology is not None:
            self.diagram.set_topology(self.topology)
            current = self.diagram.selected_id()
            if current and current in self.topology.nodes:
                self.inspector.show_node(current)

    def _set_language(self, code: str):
        from ....i18n import language_setting, save_language_setting
        if code == language_setting():
            return
        save_language_setting(code)
        answer = QMessageBox.question(
            self, "networkPlus",
            tr("Dil değişikliği yeniden başlatınca uygulanır. Şimdi yeniden başlatılsın mı?"))
        if answer == QMessageBox.Yes:
            self.restart_app()

    def restart_app(self):
        """Ayni argumanlarla yeniden baslat (tek kopya kilidini once birak)."""
        import sys
        from PyQt5.QtCore import QProcess
        server = getattr(QApplication.instance(), "np_server", None)
        if server is not None:
            server.server.close()
        from ....platform.selfexec import self_command
        args = [a for a in sys.argv[1:] if a != "--tray"]
        head = self_command()                  # exe | .AppImage | python main.py
        QProcess.startDetached(head[0], [*head[1:], *args])
        self.quit_app()

    def _relaunch_admin(self):
        if len(self.changes):
            answer = QMessageBox.question(
                self, "networkPlus",
                tr("{count} bekleyen değişiklik yeniden başlatınca kaybolacak. Devam edilsin mi?").format(count=len(self.changes)))
            if answer != QMessageBox.Yes:
                return
        if relaunch_as_admin():
            self.close()
        else:
            self.statusBar().showMessage(tr("Yönetici izni verilmedi."), 5000)

    def _about(self):
        QMessageBox.about(
            self, tr("networkPlus hakkında"),
            f"<b>networkPlus {__version__}</b><br>"
            + tr("Ağ bağdaştırıcılarını ve aralarındaki ilişkileri diyagram üzerinde gösterir.") + "<br><br>"
            + tr("Açık kaynak — GNU GPL v3."))

    # ----------------------------------------------------------------- durum
    # ----------------------------------------------------------------- yerlesim
    def _docks(self):
        return (self.dockDiagram, self.dockAdapters, self.dockInspector, self.dockDhcp, self.dockChanges)

    def reset_layout(self):
        """Varsayilan (kullanicinin 2026-10-01'de gosterdigi): solda Bagdastiricilar ustte,
        Ozellikler altta; ortada diyagram; sagda DHCP sunucusu; altta (toplu kipte) kuyruk."""
        self._restoring_layout = True
        for dock in self._docks():
            dock.setFloating(False)
        self.addDockWidget(Qt.TopDockWidgetArea, self.dockDiagram)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dockAdapters)
        self.splitDockWidget(self.dockAdapters, self.dockInspector, Qt.Vertical)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dockDhcp)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dockChanges)
        for dock in (self.dockDiagram, self.dockAdapters, self.dockInspector, self.dockDhcp):
            dock.show()
        self._sync_queue_mode()
        self._restoring_layout = False
        if self.isVisible():
            self._apply_default_sizes()
        else:
            self._size_on_show = True                         # ilk gosterimde (pencere boyutu kesin)
        self._schedule_layout_save()

    def _apply_default_sizes(self):
        """resizeDocks merkez parcacik gizliyken (diyagram da bir panel) etkisiz kaliyor (olculdu);
        bunun yerine en kucuk boyut gecici yukseltilir, yerlesim oturunca eski haline doner."""
        if getattr(self, "_sizing", False):
            return
        self._sizing = True
        self._saved_min_sizes = [(d, d.minimumSize()) for d in (self.dockAdapters, self.dockInspector, self.dockDhcp)]
        for dock in (self.dockAdapters, self.dockInspector, self.dockDhcp):
            dock.setMinimumWidth(max(DEFAULT_SIDE_WIDTH, dock.minimumWidth()))
        free = self.height() - self.dockInspector.minimumSizeHint().height() - 160
        self.dockAdapters.setMinimumHeight(max(self.dockAdapters.minimumHeight(),
                                               min(int(self.height() * 0.42), free)))
        QTimer.singleShot(100, self._restore_min_sizes)      # bagli metot: pencere silinirse dusmez

    def _restore_min_sizes(self):
        for dock, size in getattr(self, "_saved_min_sizes", []):
            dock.setMinimumSize(size)
        self._saved_min_sizes = []
        self._sizing = False

    def _schedule_layout_save(self, *_):
        if not getattr(self, "_restoring_layout", False):
            self._layout_timer.start()

    def _save_layout(self):
        # Gizli/kucultulmus pencerede de dogru: saveGeometry normal geometriyi, saveState panelin
        # kendi gizli bayragini yazar (pencerenin gizlenmesi panelleri "kapali" yapmaz).
        s = QSettings()
        s.setValue("main/geometry", self.saveGeometry())
        s.setValue("main/state", self.saveState(STATE_VERSION))

    def _on_commit_data(self, _manager):
        self._save_state()                                    # Windows oturumu kapanirken (tepsideyken de)

    def _restore_state(self):
        s = QSettings()
        geo = s.value("main/geometry")
        state = s.value("main/state")
        if geo is not None:
            self.restoreGeometry(geo)
        # Surum: varsayilan yerlesim degisince eski kayit bir kez yok sayilir.
        self._restoring_layout = True
        restored = state is not None and self.restoreState(state, STATE_VERSION)
        self._restoring_layout = False
        if not restored:
            self.reset_layout()
        self._loading_settings = True
        self.actShowHidden.setChecked(s.value("main/showHidden", False, type=bool))
        self.actAutoRefresh.setChecked(s.value("view/autoRefresh", False, type=bool))
        self.actCloseToTray.setChecked(s.value("tray/closeToTray", True, type=bool))
        self.actNotifications.setChecked(s.value("tray/notifications", True, type=bool))
        self.actConfirmRisky.setChecked(s.value("apply/confirmRisky", True, type=bool))
        self.actQueueMode.setChecked(s.value("apply/queueMode", False, type=bool))
        self._loading_settings = False
        self.actElevateOnStart.blockSignals(True)
        self.actElevateOnStart.setChecked(s.value(ELEVATE_ON_START_KEY, True, type=bool))
        self.actElevateOnStart.blockSignals(False)
        self.actElevateOnStart.setVisible(sys.platform == "win32")

    def _save_state(self):
        self._save_layout()
        self._save_settings()

    def _save_settings(self, *_):
        """Ayar onay kutulari tiklaninca HEMEN yazilir (eskiden yalniz kapanista: tepsideyken
        Windows kapanirsa kayboluyordu)."""
        if getattr(self, "_loading_settings", False):
            return
        s = QSettings()
        s.setValue("main/showHidden", self.actShowHidden.isChecked())
        s.setValue("view/autoRefresh", self.actAutoRefresh.isChecked())
        s.setValue("tray/closeToTray", self.actCloseToTray.isChecked())
        s.setValue("tray/notifications", self.actNotifications.isChecked())
        s.setValue("apply/confirmRisky", self.actConfirmRisky.isChecked())
        s.setValue("apply/queueMode", self.actQueueMode.isChecked())

    def closeEvent(self, event):
        self._save_state()
        # X dugmesi: tepsiye gonder (ayar acik ve tepsi varsa). Gercek cikis: quit_app.
        if not self._quitting and self.tray.available and self.actCloseToTray.isChecked():
            event.ignore()
            self._hide_to_tray()
            return
        # Is parcaciklari bitmeden pencere yok edilirse surec coker (testte yakalandi).
        self._refresh_again = False
        self.dhcpPanel.shutdown()               # yetim DHCP sunucusu kalmasin
        self.runner.shutdown()
        if self._thread is not None:
            self._thread.wait()
        self.undo.clear()
        self.tray.shutdown()
        super().closeEvent(event)
