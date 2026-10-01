"""Sistem tepsisi: durum simgesi, hizli islemler, bildirimler.

Menunun sabit kismi main_window.ui'daki `menuTray` (Designer'da duzenlenir);
"Baglanti durumu" satiri ve "Bagdastiricilar" alt menusu buradan eklenir.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QCursor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon

from ..core.changes import Change, ChangeKind
from ..core.i18n import tr
from ..core.model import Connectivity, NodeKind, Status, Topology
from .app_icon import app_icon
from .icons import paint_icon
from .theme import AMBER, GRAY, GREEN, status_text, status_color

_SKIP = {NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.CONTAINER}
HOVER_POLL_MS = 200          # QSystemTrayIcon'un "uzerine gelindi" sinyali yok: imlec yoklanir
HOVER_SHOW_TICKS = 2         # ~0,4 sn uzerinde kalinca acilir
HOVER_HIDE_TICKS = 3         # simge ve pencere disinda ~0,6 sn kalinca kapanir


def tray_status_color(topo: Topology | None):
    """Yesil: internet var; sari: yalniz yerel; gri: cikis yok / henuz okunmadi."""
    via = topo.nodes.get(topo.internet_via or "") if topo is not None else None
    if via is None:
        return GRAY
    return GREEN if via.connectivity == Connectivity.INTERNET else AMBER


def tray_icon(topo: Topology | None) -> QIcon:
    """Uygulama rozeti + sag altta internet durumu noktasi (ayrinti ipucu metninde)."""
    return app_icon(tray_status_color(topo))


class TrayController(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.icon = QSystemTrayIcon(tray_icon(None), self)
        menu: QMenu = win.menuTray
        first = menu.actions()[0] if menu.actions() else None
        self.act_status = QAction(tr("Ağ durumu okunuyor…"), menu)
        self.act_status.setEnabled(False)
        self.menu_adapters = QMenu(tr("Bağdaştırıcılar"), menu)
        menu.insertAction(first, self.act_status)
        menu.insertMenu(first, self.menu_adapters)
        menu.insertSeparator(first)
        # "Sistemle baslat" alt menusu Ayarlar'daki ile ayni nesne.
        menu.insertMenu(win.actCloseToTray, win.menuAutostart)
        self.icon.setContextMenu(menu)
        self.icon.setToolTip("networkPlus")
        self.icon.activated.connect(self._on_activated)
        self._told_hidden = False
        # Uzerine gelince bilgi penceresi (kullanici istegi 2026-10-01)
        from .modules.tray_popup.tray_popup import TrayPopup
        self.popup = TrayPopup()                       # ust duzey; pencere gizliyken de acilir
        self.popup.adapterClicked.connect(self.win.show_node)
        self._popup_mode = False
        self._ticks_in = self._ticks_out = 0
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(HOVER_POLL_MS)
        self._hover_timer.timeout.connect(self._poll_hover)
        if self.available:
            self.icon.show()
            self._hover_timer.start()

    # ----------------------------------------------------------------- durum
    def update(self, topo: Topology):
        self.icon.setIcon(tray_icon(topo))
        via = topo.nodes.get(topo.internet_via or "")
        if via is not None:
            ip = next((x["address"] for x in via.props.get("ipv4") or [] if x.get("address")), "")
            text = (tr("İnternet: {name} ({ip})") if ip else tr("İnternet: {name}")).format(name=via.label, ip=ip)
        else:
            text = tr("İnternet çıkışı yok")
        self.act_status.setText(text)
        self._tooltip = f"networkPlus — {text}"
        if not self._popup_mode:
            self.icon.setToolTip(self._tooltip)
        self.popup.set_topology(topo)
        self._rebuild_adapters(topo)

    def _rebuild_adapters(self, topo: Topology):
        self.menu_adapters.clear()
        nodes = sorted((n for n in topo.nodes.values()
                        if n.is_adapter and not n.hidden and n.kind not in _SKIP),
                       key=lambda n: (n.status != Status.UP, n.label.lower()))
        for n in nodes:
            ip = next((x["address"] for x in n.props.get("ipv4") or [] if x.get("address")), "")
            sub = self.menu_adapters.addMenu(f"{n.label} — {status_text(n.status)}" + (f" · {ip}" if ip else ""))
            sub.setIcon(_small_icon(n.kind, status_color(n)))
            disabled = n.status == Status.DISABLED
            act = sub.addAction(tr("Etkinleştir…") if disabled else tr("Devre dışı bırak…"))
            act.triggered.connect(lambda _=False, i=n.id, e=disabled:
                                  self.win.quick_apply(Change(ChangeKind.ENABLED, i, {"enabled": e})))
            if n.props.get("dhcp4") and n.status == Status.UP:
                act = sub.addAction(tr("DHCP adresini yenile…"))
                act.triggered.connect(lambda _=False, i=n.id:
                                      self.win.quick_apply(Change(ChangeKind.DHCP_RENEW, i, {})))
            sub.addSeparator()
            act = sub.addAction(tr("Özellikler"))
            act.triggered.connect(lambda _=False, i=n.id: self.win.show_node(i))
        if not nodes:
            self.menu_adapters.addAction(tr("(bağdaştırıcı yok)")).setEnabled(False)

    # ----------------------------------------------------------------- uzerine gelme
    def _poll_hover(self):
        geo = self.icon.geometry()
        if not self.icon.isVisible() or not geo.isValid() or geo.isEmpty():
            return                                     # konum bilinmiyor (bazi Linux masaustleri): duz ipucu
        if not self._popup_mode:
            self._popup_mode = True                    # yerel ipucu ile pencere ust uste binmesin
            self.icon.setToolTip("")
        self.hover_step(QCursor.pos(), geo, self.icon.contextMenu().isVisible())

    def hover_step(self, pos: QPoint, icon_rect: QRect, menu_open: bool = False):
        """Bir yoklama adimi (test edilebilir): simge uzerinde kalinca ac, ikisinden de cikinca kapat."""
        if menu_open:
            self._ticks_in = 0
            self.popup.hide()
            return
        over_icon = icon_rect.contains(pos)
        over_popup = self.popup.isVisible() and self.popup.geometry().adjusted(-6, -6, 6, 6).contains(pos)
        if over_icon:
            self._ticks_in += 1
            self._ticks_out = 0
            if not self.popup.isVisible() and self._ticks_in >= HOVER_SHOW_TICKS:
                self.popup.show_near(icon_rect)
        elif over_popup:
            self._ticks_out = 0
        else:
            self._ticks_in = 0
            if self.popup.isVisible():
                self._ticks_out += 1
                if self._ticks_out >= HOVER_HIDE_TICKS:
                    self.popup.hide()
                    self._ticks_out = 0

    def shutdown(self):
        self._hover_timer.stop()
        self.popup.hide()
        self.popup.deleteLater()
        self.icon.hide()

    # ----------------------------------------------------------------- olaylar
    def _on_activated(self, reason):
        self.popup.hide()
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.win.toggle_window()

    def notify(self, title: str, message: str, warn: bool = False):
        if self.available and self.icon.isVisible():
            self.icon.showMessage(title, message,
                                  QSystemTrayIcon.Warning if warn else QSystemTrayIcon.Information, 5000)

    def told_hidden_once(self) -> bool:
        """Ilk kez tepsiye gizlenince bir kez bilgi ver."""
        if self._told_hidden:
            return True
        self._told_hidden = True
        return False


def _small_icon(kind: NodeKind, color) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_icon(p, kind, QRectF(0, 0, 16, 16), color)
    p.end()
    return QIcon(pm)


def diff_notifications(old: Topology | None, new: Topology) -> list[tuple[str, str, bool]]:
    """Iki goruntu arasindaki kullaniciya bildirilecek degisiklikler: (baslik, mesaj, uyari)."""
    if old is None:
        return []
    out = []
    old_via, new_via = old.nodes.get(old.internet_via or ""), new.nodes.get(new.internet_via or "")
    if old.internet_via != new.internet_via:
        if new_via is None:
            out.append((tr("İnternet kesildi"), tr("{name} üzerinden internet yok.").format(
                name=old_via.label if old_via else tr("Çıkış")), True))
        elif old_via is None:
            out.append((tr("İnternet geldi"), tr("{name} üzerinden bağlandı.").format(name=new_via.label), False))
        else:
            out.append((tr("İnternet çıkışı değişti"), f"{old_via.label} → {new_via.label}", False))
    for nid, n in new.nodes.items():
        o = old.nodes.get(nid)
        if o is None or not n.is_adapter or n.hidden or n.kind in _SKIP or o.status == n.status:
            continue
        if n.status == Status.UP:
            out.append((tr("{name} bağlandı").format(name=n.label), status_text(n.status), False))
        elif o.status == Status.UP:
            out.append((tr("{name} bağlantısı koptu").format(name=n.label), status_text(n.status), True))
    return out
