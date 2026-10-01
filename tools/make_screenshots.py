"""README ekran goruntuleri: docs/screenshots/<dil>/*.png — sisteme DOKUNMAZ.

    python tools/make_screenshots.py            # en + tr
    python tools/make_screenshots.py --lang en

Anonim fixture (tests/fixtures/win-host.raw.json) ile, ekran disinda (offscreen) cizilir.
DHCP gorunumu icin sahte servis kullanilir (gercek sunucu/soket yok). Windows'ta yazi tipi
Segoe UI 9 pt (gercek uygulamadaki gibi; offscreen varsayilan yazi tipi Turkce harfleri bozuyor).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QEventLoop, QObject, QRect, QSettings, QTimer, pyqtSignal   # noqa: E402
from PyQt5.QtGui import QFont                                                         # noqa: E402
from PyQt5.QtWidgets import QApplication                                              # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "win-host.raw.json"
OUT = ROOT / "docs" / "screenshots"
SIZE = (1680, 1000)


class FakeDhcp(QObject):
    started = pyqtSignal(dict)
    stopped = pyqtSignal(str)
    message = pyqtSignal(dict)
    running = False

    def start(self, cfg):
        self.running = True

    def stop(self):
        self.running = False
        self.stopped.emit("")

    def set_reservations(self, items):
        pass

    def delete_lease(self, mac):
        pass


def pump(ms=300):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def open_window():
    from networkplus.platform.filesource import FileCollector
    from networkplus.ui.modules.main_window.main_window import MainWindow
    win = MainWindow(FileCollector(FIXTURE))
    win.resize(*SIZE)
    win.show()
    loop = QEventLoop()
    win.when_loaded(loop.quit)
    QTimer.singleShot(15000, loop.quit)
    win.refresh()
    loop.exec_()
    pump()
    return win


def shoot(lang: str):
    from networkplus import i18n
    from networkplus.ui.themes import apply_theme
    app = QApplication.instance()
    i18n.install(app, lang)
    i18n.install_qt_translations(app, lang)
    out = OUT / lang
    out.mkdir(parents=True, exist_ok=True)
    win = open_window()
    by = {n.label: n.id for n in win.topology.nodes.values()}

    # 1-2. Ana pencere, koyu ve acik tema (Wi-Fi secili)
    for theme in ("dark", "light"):
        win.set_theme(theme)
        win.diagram.select(by["Wi-Fi"], center=False)
        win.diagram.view.fit_all()
        pump()
        win.grab().save(str(out / f"main-{theme}.png"))

    # 3. Bagdastirici ayarlari (ETH, IPv4 sekmesi)
    win.diagram.select(by["ETH"], center=False)
    insp = win.inspector
    tabs = getattr(insp, "tabs", None)
    if tabs is not None:
        for i in range(tabs.count()):
            if tabs.tabText(i).lower().startswith("ipv4"):
                tabs.setCurrentIndex(i)
    pump()
    win.grab().save(str(out / "adapter-settings.png"))

    # 4. DHCP sunucusu: calisiyor, iki istemci, diyagramda "DHCP istemcileri"
    win._dhcp_live = lambda: True
    svc = FakeDhcp()
    win.dhcpPanel.attach(svc, lambda: (True, ""))
    win.dhcpPanel.set_live(True)
    win.show_dhcp(by["ETH"])
    win.dhcpPanel.btnStart.click()
    svc.started.emit({"event": "started", "server_ip": "192.168.1.2"})
    now = time.time()
    leases = [{"mac": "02:00:00:00:10:01", "ip": "192.168.1.100", "hostname": "plc-01", "expires": now + 3600, "state": "bound"},
              {"mac": "02:00:00:00:10:02", "ip": "192.168.1.101", "hostname": "camera-02", "expires": now + 3000, "state": "bound"}]
    for lease in leases:
        svc.message.emit({"event": "packet", "type": "DISCOVER", "mac": lease["mac"], "hostname": lease["hostname"],
                          "reply": ["OFFER"], "ip": lease["ip"]})
        svc.message.emit({"event": "lease_event", "kind": "lease_new",
                          **{k: lease[k] for k in ("mac", "ip", "hostname")}})
    svc.message.emit({"event": "leases", "items": leases})
    win.diagram.view.fit_all()
    pump()
    win.grab().save(str(out / "dhcp-server.png"))
    svc.stop()

    # 5. Tepsi bilgi penceresi
    win.set_theme("light")
    win.tray.update(win.topology)
    win.tray.popup.show_near(QRect(1700, 1000, 24, 24))
    pump()
    win.tray.popup.grab().save(str(out / "tray-popup.png"))
    win.tray.popup.hide()

    apply_theme(app, "system")
    win._quitting = True
    win.close()
    win.deleteLater()
    pump(100)
    print(f"{lang}: {sorted(p.name for p in out.glob('*.png'))}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", action="append", help="dil kodu (birden cok verilebilir); varsayilan en + tr")
    args = ap.parse_args()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("networkPlus-screenshots")        # kullanicinin ayarlarina dokunma
    app.setApplicationName("networkPlus-screenshots")
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 9))
    QSettings().clear()
    for lang in args.lang or ["en", "tr"]:
        shoot(lang)
    QSettings().clear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
