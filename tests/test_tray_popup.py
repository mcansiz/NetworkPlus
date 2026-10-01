"""Tepsi uzerine gelince acilan bilgi penceresi: icerik, acilip kapanma, satira tiklama."""

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
sys.path.insert(0, str(ROOT / "tests"))

from PyQt5.QtCore import QPoint, QRect, QSettings                    # noqa: E402

from networkplus.platform.filesource import FileCollector             # noqa: E402
from networkplus.ui.modules.tray_popup.tray_popup import (            # noqa: E402
    adapter_lines, popup_adapters,
)
from test_ui_smoke import FIXTURES, _app, dispose, wait_loaded       # noqa: E402,F401
from networkplus.ui import tray                                       # noqa: E402


class PopupFlow(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        from networkplus.ui.modules.main_window.main_window import MainWindow
        self.win = MainWindow(FileCollector(FIXTURES / "win-host.raw.json"))
        self.win.show()
        wait_loaded(self.win)
        self.win.tray.update(self.win.topology)          # offscreen'de tepsi yok; icerigi elle besle
        self.by = {n.label: n for n in self.win.topology.nodes.values()}

    def tearDown(self):
        self.win._quitting = True
        dispose(self.win)

    def test_content_like_screenshot(self):
        topo = self.win.topology
        order = [n.label for n in popup_adapters(topo)]
        self.assertEqual(order[0], "Wi-Fi")                               # internet cikisi once
        self.assertNotIn("Loopback Pseudo-Interface 1", order)
        wifi = dict(adapter_lines(topo, self.by["Wi-Fi"]))
        self.assertIn("255.255.255.0", wifi["IP"])
        self.assertIn("(DHCP)", wifi["IP"])
        self.assertEqual(wifi["Ağ geçidi"], "10.20.30.253")
        eth = adapter_lines(topo, self.by["ETH"])
        self.assertEqual(eth[0], ("", "Bağlantı yok"))                    # durum satiri
        self.assertNotIn("(DHCP)", dict(eth)["IP"])                       # statik
        self.assertEqual(len(self.win.tray.popup.rows), len(order))

    def test_hover_opens_and_leaving_closes(self):
        t, popup = self.win.tray, self.win.tray.popup
        icon = QRect(1800, 1000, 24, 24)
        inside, outside = QPoint(1810, 1010), QPoint(200, 200)
        t.hover_step(inside, icon)
        self.assertFalse(popup.isVisible())                               # hemen degil (gecikme)
        t.hover_step(inside, icon)
        self.assertTrue(popup.isVisible())
        screen = _app.primaryScreen().availableGeometry()
        self.assertTrue(screen.contains(popup.geometry()), (screen, popup.geometry()))
        t.hover_step(popup.geometry().center(), icon)                     # pencereye gecis: acik kalir
        for _ in range(tray.HOVER_HIDE_TICKS):
            self.assertTrue(popup.isVisible())
            t.hover_step(outside, icon)
        self.assertFalse(popup.isVisible())
        t.hover_step(inside, icon)
        t.hover_step(inside, icon, menu_open=True)                        # sag tik menusu acikken kapali
        self.assertFalse(popup.isVisible())

    def test_row_click_opens_properties(self):
        popup = self.win.tray.popup
        row = next(r for r in popup.rows if r.node_id == self.by["ETH"].id)
        popup.show()
        row.clicked.emit(row.node_id)
        self.assertFalse(popup.isVisible())
        self.assertEqual(self.win.inspector.lblTitle.text(), "ETH")


if __name__ == "__main__":
    unittest.main()
