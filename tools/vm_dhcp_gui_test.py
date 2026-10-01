"""DHCP sunucusunun ARAYUZDEN canli denemesi — YALNIZCA test VM'inde, kok olarak (ADR 0010).

    sudo PYTHONDONTWRITEBYTECODE=1 python3 tools/vm_dhcp_gui_test.py [--nics ens37,ens38]

Gercek ana pencere (offscreen) + gercek panel + gercek uygulama yolu + gercek sunucu sureci:
panelde A kartini sec, "Sunucu IP'si" 10.50.0.1/24 yaz, "Karta statik IP ver ve baslat"a bas
(statik IP nmcli ile uygulanir, sonra sunucu baslar). B karti (ayni yalitilmis segment)
DHCP istemcisi olur; diyagramda "DHCP istemcileri (1)" ve yeni cihaz bildirimi beklenir.
Pencere kapaninca sunucu sureci kalmamali. SSH karti HIC degismez; A/B profilleri geri doner.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from vm_dhcp_test import SERVER_IP, check, ipv4, sh, uuid_of, RESULTS   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nics", default="ens37,ens38")
    ap.add_argument("--disconnect-first", action="store_true",
                    help="A'yi once NM'de 'disconnected' yap (yeniden baslatma sonrasi DHCP zaman asimi durumu)")
    args = ap.parse_args()
    a, b = args.nics.split(",")
    if os.geteuid() != 0:
        print("kok olarak calistirin")
        return 2
    via = sh("ip", "-j", "route", "get", "8.8.8.8")
    via_dev = json.loads(via)[0]["dev"] if via else ""
    if via_dev in (a, b):
        print(f"GUVENLIK: {via_dev} internet/SSH karti; durduruldu")
        return 3

    from PyQt5.QtCore import QEventLoop, QSettings, QTimer
    from PyQt5.QtWidgets import QApplication
    app = QApplication([])
    app.setOrganizationName("networkPlus-vmtest")
    app.setApplicationName("networkPlus-vmtest")
    QSettings().clear()
    from networkplus.core.dhcp.guard import CLIENTS_PREFIX
    from networkplus.platform import get_collector
    from networkplus.ui.modules.main_window.main_window import MainWindow

    def spin(pred, timeout):
        end = time.time() + timeout
        while time.time() < end:
            app.processEvents()
            if pred():
                return True
            time.sleep(0.05)
        return pred()

    ua, ub = uuid_of(a), uuid_of(b)
    before = {u: (sh("nmcli", "-g", "ipv4.method", "connection", "show", u),
                  sh("nmcli", "-g", "ipv4.addresses", "connection", "show", u)) for u in (ua, ub)}
    mac_b = Path(f"/sys/class/net/{b}/address").read_text().strip()
    print(f"sunucu: {a} (arayuzden {SERVER_IP}), istemci: {b} ({mac_b}); SSH: {via_dev} (dokunulmaz)")

    win = None
    try:
        if args.disconnect_first:
            sh("nmcli", "device", "disconnect", a)
        win = MainWindow(get_collector())
        win.show()
        loop = QEventLoop()
        win.when_loaded(loop.quit)
        QTimer.singleShot(30000, loop.quit)
        win.refresh()
        loop.exec_()
        p = win.dhcpPanel
        notes = []
        p.leaseNotification.connect(lambda t, m: notes.append(m))

        check("Panel kartlari listeliyor, internet karti engelli",
              p.select_adapter(via_dev) and not p.btnStart.isEnabled(), p.lblWarning.text()[:80])
        check(f"{a} secildi", p.select_adapter(a))
        check("Statik IP gerekiyor (DHCP'li, sunucusuz ag)", p.check.needs_static, p.check.message[:80])
        if args.disconnect_first:
            check("Etkin olmayan kart: statik IP + etkinlestir akisi", p.check.needs_enable, p.check.message[:80])
        p.edServerIp.setText(SERVER_IP)
        p.edMask.setText("24")
        p.edServerIp.editingFinished.emit()
        p.spnLease.setValue(5)
        check("Havuz otomatik onerildi", (p.edPoolStart.text(), p.edPoolEnd.text()) == ("10.50.0.100", "10.50.0.200"),
              f"{p.edPoolStart.text()}-{p.edPoolEnd.text()}")
        check("Dugme: statik IP ver ve baslat", p.btnStart.isEnabled() and "statik" in p.btnStart.text().lower(),
              p.btnStart.text())
        p.btnStart.click()

        def started():
            if win.confirmBar.mode == "confirm":          # riskli sayildiysa kullanici gibi "Koru"
                win.confirmBar.btnKeep.click()
            return p.running and "10.50.0.1" in p.lblStatus.text()
        ok = spin(started, 90)
        check("Statik IP uygulandi ve sunucu basladi", ok,
              f"durum={p.lblStatus.text()!r} uyari={p.lblWarning.text()[:120]!r} bar={win.confirmBar.lblMessage.text()[:120]!r}")
        check(f"{a} uzerinde {SERVER_IP}", SERVER_IP in ipv4(a), str(ipv4(a)))
        daemon_pids = sh("pgrep", "-f", "dhcp_daemon.py")
        check("Sunucu sureci calisiyor", bool(daemon_pids), daemon_pids)

        sh("nmcli", "connection", "modify", ub, "ipv4.method", "auto", "ipv4.addresses", "", check=True)
        client = subprocess.Popen(["nmcli", "--wait", "45", "connection", "up", ub],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = spin(lambda: any(ip.startswith("10.50.0.") for ip in ipv4(b)), 60)
        client.wait(10)
        check("Istemci arayuzden baslatilan sunucudan adres aldi", ok, str(ipv4(b)))
        nid = CLIENTS_PREFIX + a
        ok = spin(lambda: nid in win.diagram.node_items and "(1)" in win.topology.nodes[nid].label, 15)
        check("Diyagramda 'DHCP istemcileri (1)'", ok,
              win.topology.nodes[nid].label if nid in win.topology.nodes else "yok")
        # Kiralar diskte kalir: onceki kosudan taninan cihaz "yeni" degildir (bildirim yok, yenileme kaydi var).
        log = p.txtLog.toPlainText()
        check("Yeni cihaz bildirimi (ya da taninan cihaz: yenileme)",
              any("10.50.0." in m for m in notes) or ("10.50.0." in log and not notes and "→" in log),
              str(notes) if notes else "taninan cihaz")
        check("Kiralar tablosu", p.tblLeases.rowCount() >= 1 and p.tblLeases.item(0, 0).text() == mac_b,
              str(p.tblLeases.rowCount()))

        win._quitting = True
        win.close()                                   # yetim sunucu kalmamali
        win = None
        ok = spin(lambda: not sh("pgrep", "-f", "dhcp_daemon.py"), 10)
        check("Pencere kapaninca sunucu sureci kalmadi", ok, sh("pgrep", "-af", "dhcp_daemon.py"))
    finally:
        if win is not None:
            win._quitting = True
            win.close()
        subprocess.run(["pkill", "-f", "dhcp_daemon.py"], capture_output=True)
        for u, (method, addrs) in before.items():
            sh("nmcli", "connection", "modify", u, "ipv4.method", method or "auto", "ipv4.addresses", addrs or "",
               "ipv4.gateway", "")
        sh("nmcli", "--wait", "5", "connection", "up", ua)
        sh("nmcli", "--wait", "5", "connection", "up", ub)
        QSettings().clear()
    after = {u: sh("nmcli", "-g", "ipv4.method", "connection", "show", u) for u in (ua, ub)}
    check("Profiller eski haline dondu", all(after[u] == before[u][0] for u in (ua, ub)), str(after))
    check(f"{via_dev} (SSH) hala calisiyor",
          subprocess.run(["ping", "-c", "1", "-W", "2", "192.168.42.2"], capture_output=True).returncode == 0)
    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\nSONUC: {passed}/{len(RESULTS)} gecti")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
