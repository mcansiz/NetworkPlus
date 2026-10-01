"""Uygulama girisi.

    python main.py                                   # canli sistem (tepsi + pencere)
    python main.py --tray                            # tepside baslat (sistemle baslatma bunu kullanir)
    python main.py --snapshot tests/fixtures/win-host.raw.json
    python main.py --snapshot X.json --screenshot .tmp/shots/a.png   # gelistirici: goruntu al, cik

Canli kipte:
- Tek kopya: calisan kopya varsa ona "goster" denir ve cikilir.
- Windows'ta 'yonetici olarak sistemle baslat' gorevi kuruluysa ve bu surec yetkisizse,
  gorev tetiklenir: uygulama UAC SORMADAN yonetici olarak baslar (--no-elevate ile kapatilir).
"""

from __future__ import annotations

import argparse
import sys

from PyQt5.QtCore import QCoreApplication, Qt, QTimer
from PyQt5.QtWidgets import QApplication

from . import __version__


ELEVATE_ON_START_KEY = "startup/elevate"


def elevate_on_start_enabled() -> bool:
    from PyQt5.QtCore import QSettings
    return QSettings().value(ELEVATE_ON_START_KEY, True, type=bool)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="networkplus", description="Ağ bağdaştırıcısı diyagramı")  # notr: CLI
    ap.add_argument("--snapshot", help="Canlı sistem yerine kayıtlı anlık görüntü (JSON) aç")  # notr
    ap.add_argument("--tray", action="store_true", help="Pencereyi açmadan sistem tepsisinde başlat")  # notr
    ap.add_argument("--no-elevate", action="store_true", help="Yönetici görevi kurulu olsa da yetkisiz aç")  # notr
    ap.add_argument("--screenshot", help=argparse.SUPPRESS)
    ap.add_argument("--select", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    # Qt5'te yuksek DPI varsayilan kapali; QApplication'dan ONCE acilmali (ADR 0001).
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("networkPlus")
    # Gelistirici ekran goruntusu kullanicinin ayarlarini (yerlesim, dil...) okuyup EZMESIN.
    app.setOrganizationName("networkPlus-screenshot" if args.screenshot else "networkPlus")
    app.setApplicationVersion(__version__)
    # Gorev cubugu: kendi simgemiz; Windows'ta python.exe altinda gruplanmasin (AppUserModelID).
    from .platform import set_app_identity
    from .ui.app_icon import app_icon
    set_app_identity()
    app.setWindowIcon(app_icon())

    # Dil: pencereler (ve .ui metinleri) olusturulmadan ONCE (ADR 0008).
    from .i18n import install as install_language, install_qt_translations
    lang = install_language(app)
    install_qt_translations(app, lang)
    # Tema (ADR 0011): pencereler olusmadan once; diyagram paleti buradan okur.
    from .ui.themes import apply_theme
    apply_theme(app)

    live = not args.snapshot and not args.screenshot
    server = None
    if live:
        from .ui.single_instance import SingleInstanceServer, send_to_running, wait_and_send
        if send_to_running("tray" if args.tray else "show"):
            return 0                                   # zaten calisiyor: onu one getirdik
        if not args.no_elevate:
            from .platform import try_elevate_via_task
            if try_elevate_via_task():
                # Yonetici kopya gorevle tepside baslar; kullanici pencere istediyse goster.
                if not args.tray:
                    wait_and_send("show")
                return 0
            # Kullanici karari (2026-09-30): acilista DOGRUDAN yonetici yetkisi iste (UAC).
            # Reddedilirse normal yetkiyle devam. Sistemle baslarken (--tray) sorulmaz.
            if not args.tray and elevate_on_start_enabled():
                from .platform import elevation_state, relaunch_as_admin
                admin, can_relaunch = elevation_state()
                if not admin and can_relaunch and relaunch_as_admin():
                    return 0                           # yonetici kopya acildi
        server = SingleInstanceServer()
        server.listen()
        app.np_server = server           # yeniden baslatirken kilidi birakmak icin

    from .platform import get_collector
    from .ui.modules.main_window.main_window import MainWindow

    win = MainWindow(get_collector(args.snapshot))
    tray_ok = win.tray.available
    if live and tray_ok:
        app.setQuitOnLastWindowClosed(False)           # pencere kapaninca tepside yasar
    if server is not None:
        server.messageReceived.connect(lambda msg: win.show_window() if msg == "show" else None)

    if args.tray and tray_ok:
        pass                                           # yalniz tepsi simgesi
    else:
        win.show()

    if args.screenshot:
        def shoot():
            if args.select:
                node = next((n for n in win.topology.nodes.values() if n.label == args.select), None)
                if node:
                    win.diagram.select(node.id)
            QTimer.singleShot(400, lambda: (win.grab().save(args.screenshot), win.quit_app()))
        win.when_loaded(shoot)

    QTimer.singleShot(0, win.refresh)
    return app.exec_()


__all__ = ["main"]
