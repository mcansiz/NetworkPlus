"""QSS temalari (ADR 0011): dosyalar, palet, cozumleme, canli degistirme."""

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

from PyQt5.QtCore import QSettings, qInstallMessageHandler      # noqa: E402
from PyQt5.QtGui import QColor, QPalette                         # noqa: E402

from networkplus.ui import themes as T                           # noqa: E402
from test_ui_smoke import FIXTURES, _app, dispose, wait_loaded   # noqa: E402,F401


class ThemeFiles(unittest.TestCase):
    def test_builtin_themes_complete(self):
        found = {t.code: t for t in T.available_themes()}
        self.assertEqual(list(found)[:2], ["light", "dark"])            # hazirlar once
        for code in ("light", "dark"):
            theme = found[code]
            roles = {role for disabled, role in theme.palette if not disabled}
            self.assertEqual(roles, set(T._ROLES), f"{code}: eksik palet rolu {set(T._ROLES) - roles}")
        self.assertFalse(found["light"].is_dark)
        self.assertTrue(found["dark"].is_dark)

    def test_stylesheets_parse_without_qt_warnings(self):
        warnings = []
        previous = qInstallMessageHandler(lambda _t, _c, msg: warnings.append(msg))
        try:
            for theme in T.available_themes():
                T.apply_theme(_app, theme.code)
                from PyQt5.QtWidgets import QPushButton
                b = QPushButton("x")
                b.ensurePolished()                                       # QSS ayristirma burada olur
                b.deleteLater()
        finally:
            T.apply_theme(_app, T.SYSTEM)
            qInstallMessageHandler(previous)
        self.assertFalse([w for w in warnings if "style" in w.lower()], warnings)

    def test_resolve(self):
        self.assertEqual(T.resolve_theme("auto", prefers_dark=True), "dark")
        self.assertEqual(T.resolve_theme("auto", prefers_dark=False), "light")
        self.assertEqual(T.resolve_theme("auto", prefers_dark=None), "light")   # bilinmiyor -> acik
        self.assertEqual(T.resolve_theme("system"), "system")
        self.assertEqual(T.resolve_theme("dark", prefers_dark=False), "dark")   # acik secim kazanir
        self.assertEqual(T.resolve_theme("yok-boyle-tema", prefers_dark=True), "dark")

    def test_user_theme_file_appears(self):
        extra = T.THEMES_DIR / "zz-test-tema.qss"
        extra.write_text("/* @name: Deneme\n   @palette window: #102030\n*/\nQWidget { }\n", encoding="utf-8")
        try:
            theme = next(t for t in T.available_themes() if t.code == "zz-test-tema")
            self.assertEqual(theme.name, "Deneme")
            self.assertTrue(theme.is_dark)
        finally:
            extra.unlink()

    def test_user_themes_dir_overrides_and_adds(self):
        """Tek dosya pakette hazir temalar exe icinde; kullanici klasoru ekler/ezer."""
        folder = T.user_themes_dir()
        folder.mkdir(parents=True, exist_ok=True)
        mine, override = folder / "benim.qss", folder / "dark.qss"
        mine.write_text("/* @name: Benim\n   @palette window: #eeeeee\n*/\n", encoding="utf-8")
        override.write_text("/* @palette window: #000000\n*/\n", encoding="utf-8")
        try:
            themes = {t.code: t for t in T.available_themes()}
            self.assertEqual(themes["benim"].name, "Benim")
            self.assertEqual(themes["dark"].path, override)
        finally:
            mine.unlink()
            override.unlink()


class LiveSwitch(unittest.TestCase):
    def setUp(self):
        QSettings().clear()

    def tearDown(self):
        T.apply_theme(_app, T.SYSTEM)
        QSettings().clear()

    def test_switch_changes_palette_and_diagram(self):
        from networkplus.platform.filesource import FileCollector
        from networkplus.ui.modules.main_window.main_window import MainWindow
        win = MainWindow(FileCollector(FIXTURES / "win-host.raw.json"))
        try:
            win.show()
            wait_loaded(win)
            win.set_theme("dark")
            self.assertEqual(T.theme_setting(), "dark")
            self.assertTrue(win.actTheme_dark.isChecked() if hasattr(win, "actTheme_dark")
                            else win._theme_actions["dark"].isChecked())
            base = _app.palette().color(QPalette.Base)
            self.assertLess(base.lightness(), 80)                          # diyagram zemini koyu
            self.assertTrue(_app.styleSheet())
            self.assertEqual(set(win.diagram.node_items), {n.id for n in win.topology.visible_nodes()})
            win.set_theme("light")
            self.assertEqual(_app.palette().color(QPalette.Base), QColor("#ffffff"))
            win.set_theme("system")
            self.assertEqual(_app.styleSheet(), "")
        finally:
            win._quitting = True
            dispose(win)


if __name__ == "__main__":
    unittest.main()
