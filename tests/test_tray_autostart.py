"""Tepsi bildirimleri, sistemle baslatma (betik METNI; hicbir gorev/kayit olusturulmaz),
kart ustu dugmeler. Ciktilar proje/.tmp altinda (ai_rules/10).
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus.core.discovery import build_topology            # noqa: E402
from networkplus.paths import work_dir                           # noqa: E402
from networkplus.platform.filesource import normalize_any        # noqa: E402
from networkplus.ui.tray import diff_notifications               # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def raw():
    return json.loads((FIX / "win-host.raw.json").read_text(encoding="utf-8"))


class Notifications(unittest.TestCase):
    def test_internet_lost_and_adapter_changes(self):
        before = build_topology(normalize_any(raw()))
        r = copy.deepcopy(raw())
        for a in r["adapters"]:
            if a["name"] == "Wi-Fi":
                a["status"] = "Disconnected"
            if a["name"] == "ETH":
                a["status"] = "Up"
        r["internet_route"] = []
        after = build_topology(normalize_any(r))
        notes = diff_notifications(before, after)
        titles = [t for t, _, _ in notes]
        self.assertIn("İnternet kesildi", titles)
        self.assertIn("Wi-Fi bağlantısı koptu", titles)
        self.assertIn("ETH bağlandı", titles)
        self.assertTrue(dict((t, w) for t, _, w in notes)["İnternet kesildi"])
        self.assertEqual(diff_notifications(None, after), [])
        self.assertEqual(diff_notifications(after, after), [])


@unittest.skipUnless(sys.platform == "win32", "Windows")
class WindowsAutostartScript(unittest.TestCase):
    def test_register_script_text(self):
        from networkplus.platform.windows import autostart
        s = autostart.register_task_script()
        self.assertIn("-RunLevel Highest", s)
        self.assertIn("-AllowStartIfOnBatteries", s)          # dizustu pilde de baslasin
        self.assertIn("-ExecutionTimeLimit ([TimeSpan]::Zero)", s)
        self.assertIn("--tray", s)
        self.assertIn("-AtLogOn", s)
        self.assertIn("main.py", s)

    def test_launch_command_prefers_pythonw(self):
        from networkplus.platform.windows import autostart
        exe, args = autostart.launch_command(tray=True)
        self.assertTrue(exe.lower().endswith(("pythonw.exe", "python.exe")))
        self.assertEqual(args[-1], "--tray")


class LinuxAutostart(unittest.TestCase):
    def test_desktop_file_in_sandbox(self):
        from networkplus.platform.linux import autostart
        sandbox = work_dir("test") / "xdg"
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(sandbox)
        try:
            self.assertEqual(autostart.set_mode("user"), (True, ""))
            text = autostart.desktop_path().read_text(encoding="utf-8")
            self.assertIn("--tray", text)
            self.assertIn("Exec=", text)
            self.assertEqual(autostart.get_mode(), "user")
            self.assertFalse(autostart.set_mode("admin")[0])      # Linux'ta yok
            self.assertEqual(autostart.set_mode("off"), (True, ""))
            self.assertFalse(autostart.desktop_path().exists())
        finally:
            if old is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old


class CardButtons(unittest.TestCase):
    def test_power_button_and_double_click_signals(self):
        from PyQt5.QtCore import QPoint, QPointF, Qt
        from PyQt5.QtWidgets import QApplication
        from networkplus.ui.modules.diagram.items import NodeItem
        QApplication.instance() or QApplication([])
        topo = build_topology(normalize_any(raw()))
        eth = next(n for n in topo.nodes.values() if n.label == "ETH")
        item = NodeItem(eth, False)
        got = []
        item.powerRequested.connect(lambda i: got.append(("power", i)))
        item.propertiesRequested.connect(lambda i: got.append(("props", i)))
        item.contextRequested.connect(lambda i, _p: got.append(("menu", i)))
        item._hover = True                                   # dugmeler yalniz uzerine gelince

        class Ev:                                            # PyQt5 sahne olayi olusturulamiyor
            def __init__(self, pos):
                self._pos = pos
            def button(self):                                # noqa: E301
                return Qt.LeftButton
            def pos(self):                                   # noqa: E301
                return self._pos
            def screenPos(self):                             # noqa: E301
                return QPoint(0, 0)
            def accept(self):                                # noqa: E301
                pass

        item.mousePressEvent(Ev(item._btn_power()))
        item.mousePressEvent(Ev(item._btn_menu()))
        item.mouseDoubleClickEvent(Ev(QPointF(20, 20)))
        self.assertEqual(got, [("power", eth.id), ("menu", eth.id), ("props", eth.id)])

        item._hover = False                                  # uzerinde degilken dugme yok
        self.assertFalse(item._hit(item._btn_power(), item._btn_power()))


if __name__ == "__main__":
    unittest.main()
