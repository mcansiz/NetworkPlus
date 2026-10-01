"""Dil destegi (ADR 0008): ceviri dosyalari eksiksiz, kodda sarilmamis metin yok,
sozde dilde (qps) ekrandaki her statik metin ceviriden geciyor, Ingilizce calisiyor.
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
sys.path.insert(0, str(ROOT / "tools"))

from PyQt5.QtWidgets import (                                           # noqa: E402
    QAbstractButton, QApplication, QGroupBox, QLabel, QLineEdit, QMenu, QTableWidget, QTabWidget,
    QTreeWidget,
)

import i18n_find_untranslated                                         # noqa: E402
import i18n_update                                                     # noqa: E402
from networkplus import i18n                                           # noqa: E402
from networkplus.platform.filesource import FileCollector              # noqa: E402

_app = QApplication.instance() or QApplication([])
_app.setOrganizationName("networkPlus-test")
_app.setApplicationName("networkPlus-test")
FIX = ROOT / "tests" / "fixtures"


def dispose(win):
    """Kapat + hemen sil (cop toplayici baska bir Qt cagrisinin ortasinda silerse surec coker)."""
    from PyQt5.QtCore import QEvent
    win.close()
    win.deleteLater()
    _app.sendPostedEvents(None, QEvent.DeferredDelete)


def open_window():
    from PyQt5.QtCore import QEventLoop, QTimer
    from networkplus.ui.modules.main_window.main_window import MainWindow
    win = MainWindow(FileCollector(FIX / "win-host.raw.json"))
    win.show()
    loop = QEventLoop()
    win.when_loaded(loop.quit)
    QTimer.singleShot(15000, loop.quit)
    win.refresh()
    loop.exec_()
    return win


def visible_texts(win) -> list[tuple[str, str]]:
    """Kullanicinin gordugu STATIK metinler (veri degil): (nerede, metin)."""
    out = []
    for w in win.findChildren(QLabel):
        out.append((f"QLabel {w.objectName()}", w.text()))
    for w in win.findChildren(QAbstractButton):
        out.append((f"Button {w.objectName()}", w.text()))
        out.append((f"Button.toolTip {w.objectName()}", w.toolTip()))
    for w in win.findChildren(QGroupBox):
        out.append((f"QGroupBox {w.objectName()}", w.title()))
    for w in win.findChildren(QTabWidget):
        for i in range(w.count()):
            out.append((f"Tab {w.objectName()}[{i}]", w.tabText(i)))
    for w in win.findChildren(QTreeWidget):
        h = w.headerItem()
        for i in range(h.columnCount()):
            out.append((f"Header {w.objectName()}[{i}]", h.text(i)))
    for w in win.findChildren(QTableWidget):
        for i in range(w.columnCount()):
            item = w.horizontalHeaderItem(i)
            out.append((f"Header {w.objectName()}[{i}]", item.text() if item else ""))
    for w in win.findChildren(QLineEdit):
        out.append((f"Placeholder {w.objectName()}", w.placeholderText()))
    for m in win.findChildren(QMenu):
        out.append((f"Menu {m.objectName()}", m.title()))
        for a in m.actions():
            if not a.isSeparator():
                out.append((f"Action {a.objectName()}", a.text()))
    for dock in (win.dockAdapters, win.dockInspector, win.dockChanges, win.dockDhcp):
        out.append((f"Dock {dock.objectName()}", dock.windowTitle()))
    return out


# Bilerek cevrilmeyen (veri ya da ozel ad): dugum/bagdastirici adlari, sayilar, simgeler.
def is_static_text(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 2


class TranslationFiles(unittest.TestCase):
    def test_all_languages_complete(self):
        problems = [p for ts in sorted(i18n_update.I18N.glob("*.ts")) for p in i18n_update.check(ts)]
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_ts_up_to_date_with_sources(self):
        """Koddaki her metin .ts'de var (yoksa: python tools/i18n_update.py)."""
        sources = i18n_update.collect()
        for ts in sorted(i18n_update.I18N.glob("*.ts")):
            _lang, table = i18n_update.read_ts(ts)
            missing = [(ctx, src) for ctx, items in sources.items() for src in items if (ctx, src) not in table]
            self.assertEqual(missing, [], f"{ts.name}: {missing[:10]}")

    def test_no_unwrapped_turkish_in_code(self):
        found = [line for f in sorted((ROOT / "src" / "networkplus").rglob("*.py"))
                 for line in i18n_find_untranslated.scan(f)]
        self.assertEqual(found, [], "\n".join(found[:20]))

    def test_languages_listed(self):
        codes = {l.code: l.name for l in i18n.available_languages()}
        self.assertEqual(codes.get("tr"), "Türkçe")
        self.assertEqual(codes.get("en"), "English")

    def test_resolve_language(self):
        old = os.environ.pop("NETWORKPLUS_LANG", None)
        try:
            self.assertEqual(i18n.resolve_language("en"), "en")
            self.assertEqual(i18n.resolve_language("tr"), "tr")
            # olmayan dil ya da 'auto': sistem dili destekleniyorsa o, yoksa Ingilizce
            from PyQt5.QtCore import QLocale
            codes = {l.code for l in i18n.available_languages()}
            name = QLocale.system().name()                          # "tr_TR", "zh_CN"
            expected = next((c for c in (name, name.split("_")[0]) if c in codes), "en")
            self.assertEqual(i18n.resolve_language("auto"), expected)
            self.assertEqual(i18n.resolve_language("xx"), expected)
        finally:
            if old is not None:
                os.environ["NETWORKPLUS_LANG"] = old


class LiveTranslation(unittest.TestCase):
    def tearDown(self):
        i18n.install(_app, "tr")          # diger testler kaynak dilde kalsin

    def test_pseudo_locale_every_static_text_is_translated(self):
        i18n.install(_app, "qps")
        win = open_window()
        try:
            eth = next(n for n in win.topology.nodes.values() if n.label == "ETH")
            win.diagram.select(eth.id)                 # inspector'in dinamik metinleri de dolsun
            data = {n.label for n in win.topology.nodes.values()}
            offenders = [(where, text) for where, text in visible_texts(win)
                         if text and is_static_text(text) and "[!" not in text and text not in data
                         and "actLang_" not in where]          # dil adlari bilerek kendi dilinde
            self.assertEqual(offenders, [], "\n".join(f"{w}: {t!r}" for w, t in offenders[:30]))
        finally:
            dispose(win)

    def test_every_language_opens_translated(self):
        """Her .ts dili: pencere acilir, menu ve cekirdek metinleri o dilde (kaynak Turkce degil)."""
        from networkplus.core.model import NodeKind
        from networkplus.core.discovery import kind_label
        for lang in i18n.available_languages():
            if lang.path is None:
                continue
            with self.subTest(lang=lang.code):
                i18n.install(_app, lang.code)
                win = open_window()
                try:
                    self.assertNotEqual(win.menuFile.title(), "&Dosya")
                    self.assertNotEqual(win.actRefresh.text(), "Yenile")
                    self.assertNotEqual(kind_label(NodeKind.GATEWAY), "Ağ geçidi")
                    self.assertTrue(win.topology.nodes)
                finally:
                    dispose(win)

    def test_english_ui_and_core(self):
        i18n.install(_app, "en")
        win = open_window()
        try:
            self.assertEqual(win.menuFile.title(), "&File")
            self.assertEqual(win.actRefresh.text(), "Refresh")
            self.assertIn("Internet", win.statusBar().currentMessage())
            from networkplus.core.changes import Change, ChangeKind, describe
            eth = next(n for n in win.topology.nodes.values() if n.label == "ETH")
            self.assertEqual(describe(Change(ChangeKind.DHCP_RENEW, eth.id, {}), win.topology),
                             "ETH: renew DHCP address")
            self.assertIn("Physical", [win.adapterList.tree.topLevelItem(i).text(0).split(" (")[0]
                                       for i in range(win.adapterList.tree.topLevelItemCount())])
        finally:
            dispose(win)


if __name__ == "__main__":
    unittest.main()
