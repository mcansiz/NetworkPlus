"""DHCP sunucusu: kart denetimi (guard), diyagram katmani ve panel akisi (sahte servis).

Gercek sunucu sureci, soket, guvenlik duvari ve ag ayari YOK: servis ve uygulama isi sahtedir.
Canli deneme: tools/vm_dhcp_test.py (yalnizca test VM'i).
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt5.QtCore import QObject, QSettings, pyqtSignal      # noqa: E402

from networkplus.core.dhcp.guard import (                   # noqa: E402
    CLIENTS_PREFIX, apply_overlay, check_adapter, eligible_adapters,
)
from networkplus.core.discovery import build_topology       # noqa: E402
from networkplus.core.layout import COL_X, compute_layout   # noqa: E402
from networkplus.core.model import EdgeKind, NodeKind       # noqa: E402
from networkplus.platform.filesource import FileCollector, normalize_any  # noqa: E402
from test_ui_smoke import FIXTURES, FakeJob, _app, dispose, spin_until, wait_loaded  # noqa: E402,F401


def topo_of(name: str):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return build_topology(normalize_any(raw))


def by_label(topo, label):
    return next(n.id for n in topo.nodes.values() if n.label == label)


class GuardTests(unittest.TestCase):
    def test_rules_on_fixtures(self):
        win = topo_of("win-host.raw.json")
        self.assertFalse(check_adapter(win, win.internet_via).ok)            # internet karti: sahte DHCP
        eth = check_adapter(win, by_label(win, "ETH"))
        self.assertTrue(eth.ok)
        self.assertEqual((eth.server_ip, eth.prefix), ("192.168.1.2", 24))
        self.assertEqual(eth.severity, "warning")                            # kablo takili degil

        syn = topo_of("linux-synthetic.raw.json")
        shared = check_adapter(syn, "enp0s8")                                # NM paylasimi acik
        self.assertFalse(shared.ok)
        self.assertFalse(shared.needs_static)
        self.assertTrue(check_adapter(syn, "enp0s9").needs_static)           # statik IP yok
        self.assertIn("virbr0", [n.id for n in eligible_adapters(syn)])
        self.assertTrue(check_adapter(syn, "virbr0").message)                # sanal ag uyarisi

        mint = topo_of("linux-mint.raw.json")
        self.assertFalse(check_adapter(mint, "ens33").ok)                    # SSH/internet karti
        self.assertTrue(check_adapter(mint, "ens37").needs_static)          # DHCP'li ama sunucu yok

    def test_linux_inactive_adapter_static_then_enable(self):
        """NM baglantiyi birakmis (sunucusuz agda DHCP zaman asimi) = devre disi; Linux'ta akis acik."""
        from networkplus.core.model import Status
        mint = topo_of("linux-mint.raw.json")
        mint.nodes["ens37"].status = Status.DISABLED
        c = check_adapter(mint, "ens37")
        self.assertTrue(c.needs_static and c.needs_enable)
        win = topo_of("win-host.raw.json")
        eth = by_label(win, "ETH")
        win.nodes[eth].status = Status.DISABLED
        c = check_adapter(win, eth)
        self.assertFalse(c.ok or c.needs_static)                           # Windows: once etkinlestir

    def test_overlay_node_edge_and_layout(self):
        topo = topo_of("win-host.raw.json")
        eth = by_label(topo, "ETH")
        clients = [{"mac": "02:00:00:00:00:01", "ip": "192.168.1.100", "hostname": "plc"}]
        apply_overlay(topo, eth, "192.168.1.2", clients)
        nid = CLIENTS_PREFIX + eth
        self.assertEqual(topo.nodes[nid].kind, NodeKind.DHCP_CLIENTS)
        self.assertFalse(topo.nodes[nid].is_adapter)
        self.assertIn("(1)", topo.nodes[nid].label)
        self.assertEqual([e.kind for e in topo.edges_of(nid)], [EdgeKind.DHCP])
        pos = compute_layout(topo)
        self.assertEqual(pos[nid], (COL_X[4], pos[eth][1]))                   # kartin hizasinda
        apply_overlay(topo, eth, "192.168.1.2", clients)                     # tekrar: cift dugum olmaz
        self.assertEqual(sum(1 for n in topo.nodes if n.startswith(CLIENTS_PREFIX)), 1)
        apply_overlay(topo, None)
        self.assertNotIn(nid, topo.nodes)
        self.assertFalse([e for e in topo.edges if e.kind == EdgeKind.DHCP])


class FakeService(QObject):
    """DhcpService yerine: surec baslatmaz; testler olaylari elle yayar."""
    started = pyqtSignal(dict)
    stopped = pyqtSignal(str)
    message = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = False
        self.configs = []
        self.reservations = []
        self.deleted = []

    def start(self, cfg):
        self.configs.append(cfg)
        self.running = True

    def stop(self):
        if self.running:
            self.running = False
            self.stopped.emit("")

    def set_reservations(self, items):
        self.reservations.append(items)

    def delete_lease(self, mac):
        self.deleted.append(mac)


class DhcpPanelFlow(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        from networkplus.ui.modules.dhcp_server import dhcp_server
        self._wait = dhcp_server.STATIC_WAIT_S
        dhcp_server.STATIC_WAIT_S = 2                  # sahte is adresi hic getirmez; kisa bekle
        self.addCleanup(setattr, dhcp_server, "STATIC_WAIT_S", self._wait)
        from networkplus.ui.modules.main_window.main_window import MainWindow
        self.win = MainWindow(FileCollector(FIXTURES / "win-host.raw.json"))
        self.win._dhcp_live = lambda: True
        self.preflights = []
        self.svc = FakeService()
        self.win.dhcpPanel.attach(self.svc, lambda: self.preflights.append(1) or (True, ""))
        self.win.show()
        wait_loaded(self.win)
        self.panel = self.win.dhcpPanel
        self.eth = by_label(self.win.topology, "ETH")

    def tearDown(self):
        w = self.win
        spin_until(lambda: not w.runner.busy and not (w._thread and w._thread.isRunning()), 10000)
        _app.processEvents()
        w._quitting = True
        dispose(w)

    def test_internet_adapter_blocked(self):
        self.assertTrue(self.panel.select_adapter(self.win.topology.internet_via))
        self.assertFalse(self.panel.btnStart.isEnabled())
        self.assertIn("sahte DHCP", self.panel.lblWarning.text())

    def test_snapshot_source_blocked(self):
        self.win._dhcp_live = lambda: False
        self.panel.set_live(False)
        self.panel.select_adapter(self.eth)
        self.assertFalse(self.panel.btnStart.isEnabled())

    def test_start_leases_overlay_notify_stop(self):
        p, w = self.panel, self.win
        self.assertTrue(p.select_adapter(self.eth))
        self.assertEqual(p.edServerIp.text(), "192.168.1.2")                 # karttan oneri
        self.assertEqual((p.edPoolStart.text(), p.edPoolEnd.text()), ("192.168.1.100", "192.168.1.200"))
        self.assertEqual(p.btnStart.text(), "Başlat")
        p.btnStart.click()
        self.assertEqual(len(self.svc.configs), 1)
        cfg = self.svc.configs[0]
        self.assertEqual((cfg.server_ip, cfg.prefix, cfg.interface, cfg.gateway), ("192.168.1.2", 24, self.eth, None))
        self.assertEqual(self.preflights, [1])                              # guvenlik duvari adimi
        self.assertTrue(QSettings().value("dhcp/config/" + "".join(c if c.isalnum() else "_" for c in self.eth)))
        self.svc.started.emit({"event": "started", "server_ip": "192.168.1.2"})
        self.assertIn("192.168.1.2", p.lblStatus.text())
        self.assertFalse(p.cmbAdapter.isEnabled())                          # calisirken kart degismez

        notes = []
        p.leaseNotification.connect(lambda t, m: notes.append(m))
        lease = {"mac": "02:00:00:00:00:01", "ip": "192.168.1.100", "hostname": "plc-1",
                 "start": time.time(), "expires": time.time() + 600, "state": "bound"}
        self.svc.message.emit({"event": "lease_event", "kind": "lease_new", "mac": lease["mac"],
                             "ip": lease["ip"], "hostname": "plc-1"})
        self.svc.message.emit({"event": "lease_event", "kind": "lease_renew", "mac": lease["mac"],
                             "ip": lease["ip"], "hostname": "plc-1"})
        self.assertEqual(notes, ["plc-1 → 192.168.1.100"])                  # yalniz yeni cihaz
        self.svc.message.emit({"event": "leases", "items": [lease]})
        self.assertEqual(p.tblLeases.rowCount(), 1)
        nid = CLIENTS_PREFIX + self.eth
        self.assertIn(nid, w.diagram.node_items)                            # diyagramda istemciler
        self.assertTrue(any(e.kind == EdgeKind.DHCP for e in w.topology.edges))
        w.diagram.select(nid)
        self.assertIn("plc-1", w.inspector.treeInfo.topLevelItem(3).text(1))

        p.tblLeases.selectRow(0)
        p.btnReserve.click()                                                # kiradan rezervasyon
        self.assertEqual(self.svc.reservations[-1], {"02:00:00:00:00:01": {"ip": "192.168.1.100", "name": "plc-1"}})
        p.btnDeleteLease.click()
        self.assertEqual(self.svc.deleted, ["02:00:00:00:00:01"])

        w.refresh()                                                         # yenilemede katman korunur
        spin_until(lambda: not (w._thread and w._thread.isRunning()))
        _app.processEvents()
        self.assertIn(nid, w.diagram.node_items)

        p.btnStop.click()
        self.assertFalse(self.svc.running)
        self.assertNotIn(nid, w.diagram.node_items)
        self.assertTrue(p.cmbAdapter.isEnabled())

    def test_start_failure_reported(self):
        p = self.panel
        p.select_adapter(self.eth)
        p.btnStart.click()
        self.svc.running = False
        self.svc.stopped.emit("Port 67 kullanılamıyor")
        self.assertIn("hata", p.lblStatus.text())
        self.assertIn("Port 67", p.lblWarning.text())
        self.assertTrue(p.btnStart.isEnabled())

    def test_changed_server_ip_applies_static_first(self):
        p, w = self.panel, self.win
        plans = []
        w._apply_support = lambda: (True, "")
        w._create_job = lambda plan, secs: plans.append(plan) or FakeJob("script", confirm_seconds=secs)
        p.select_adapter(self.eth)
        p.edServerIp.setText("192.168.1.50")
        p.edServerIp.editingFinished.emit()
        self.assertEqual(p.btnStart.text(), "Karta statik IP ver ve başlat")
        p.btnStart.click()
        self.assertEqual(len(plans), 1)
        change = plans[0].changes[0]
        self.assertEqual((change.target, change.params["mode"], change.params["address"], change.params["prefix"]),
                         (self.eth, "static", "192.168.1.50", 24))
        self.assertEqual(self.svc.configs, [])                               # once statik IP
        # Sahte is hicbir sey degistirmez: dosyadaki ETH hala .2 -> sunucu BASLAMAZ, acik hata
        self.assertTrue(spin_until(lambda: "görünmüyor" in p.lblWarning.text(), 15000))
        self.assertEqual(self.svc.configs, [])
        self.assertTrue(p.btnStart.isEnabled())

    def test_linux_disabled_adapter_two_step_apply(self):
        """Statik IP ve etkinlestirme AYRI uygulamalar, bu sirayla (tek planda etkinlestirme once kosardi)."""
        from networkplus.core.changes import ChangeKind
        from networkplus.core.model import Status
        w, p = self.win, self.panel
        w.collector = FileCollector(FIXTURES / "linux-mint.raw.json")
        w.refresh()
        self.assertTrue(spin_until(lambda: w.topology.platform == "linux" and not w._thread.isRunning()))
        _app.processEvents()
        w.topology.nodes["ens37"].status = Status.DISABLED
        p.set_topology(w.topology)
        plans = []
        w._apply_support = lambda: (True, "")
        w._create_job = lambda plan, secs: plans.append(plan) or FakeJob("script", confirm_seconds=secs)
        self.assertTrue(p.select_adapter("ens37"))
        self.assertTrue(p.check.needs_enable)
        p.edServerIp.setText("10.50.0.1")
        p.edServerIp.editingFinished.emit()
        p.btnStart.click()
        self.assertTrue(spin_until(lambda: len(plans) == 2, 15000))
        self.assertEqual([[c.kind for c in pl.changes] for pl in plans], [[ChangeKind.IPV4], [ChangeKind.ENABLED]])
        # Sahte is bir sey degistirmez -> dosyada statik adres yok -> sunucu baslamaz, acik hata
        self.assertTrue(spin_until(lambda: "görünmüyor" in p.lblWarning.text(), 15000))
        self.assertEqual(self.svc.configs, [])

    def test_context_menu_entry_opens_panel(self):
        self.win.show_dhcp(self.eth)
        self.assertEqual(self.panel.selected_adapter(), self.eth)
        self.assertTrue(self.win.dockDhcp.isVisible())


if __name__ == "__main__":
    unittest.main()
