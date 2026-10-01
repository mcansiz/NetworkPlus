"""Tepsi simgesinin uzerine gelince acilan bilgi penceresi (kullanici istegi 2026-10-01).

Her bagdastirici icin: ad, aciklama, durum, Wi-Fi agi + sinyal, tum IPv4 adresleri / maske
(DHCP isareti), ag gecidi. Satira tiklamak o bagdastiricinin ozelliklerini acar.
Windows tepsi ipucu yalniz duz metin gosterebildigi icin bu ayri, cercevesiz bir penceredir;
ne zaman acilip kapanacagina TrayController karar verir (ui/tray.py).
"""

from __future__ import annotations

import html
import ipaddress

from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPalette
from PyQt5.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from .... import __version__
from ....core.i18n import tr
from ....core.model import Node, NodeKind, Status, Topology
from ...app_icon import icon_pixmap
from ...icons import make_icon
from ...theme import GREEN, palette_color, status_color, status_text
from ...uiloader import load_ui, require

WIDTH = 360
LABEL_WIDTH = 74             # "IP:" / "Ag gecidi:" sutunu her satirda ayni genislikte (degerler hizali)
MAX_SCREEN_FRACTION = 0.7
_SKIP = {NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.CONTAINER}


def _mask(prefix) -> str:
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{int(prefix)}").netmask)
    except (TypeError, ValueError):
        return "?"


def gateway_of(topo: Topology, node_id: str) -> str:
    return next((r.get("next_hop") for r in topo.snapshot.get("default_routes") or []
                 if r.get("adapter") == node_id and r.get("family") == 4
                 and r.get("next_hop") not in (None, "", "0.0.0.0")), "")


def popup_adapters(topo: Topology) -> list[Node]:
    """Gosterilecek bagdastiricilar: internet cikisi once, sonra bagli olanlar, sonra ada gore."""
    nodes = [n for n in topo.nodes.values() if n.is_adapter and not n.hidden and n.kind not in _SKIP]
    return sorted(nodes, key=lambda n: (n.id != topo.internet_via, n.status != Status.UP, n.label.lower()))


def adapter_lines(topo: Topology, node: Node) -> list[tuple[str, str]]:
    """(etiket, deger) satirlari; etiket bos ise deger tek basina (durum, Wi-Fi) yazilir."""
    p = node.props
    lines: list[tuple[str, str]] = []
    if node.status != Status.UP:
        lines.append(("", status_text(node.status)))
    wifi = p.get("wifi") or {}
    if wifi.get("ssid"):
        signal = wifi.get("signal")
        lines.append(("", (tr("Bağlı: {ssid} ({signal}%)") if signal not in (None, "") else
                           tr("Bağlı: {ssid}")).format(ssid=wifi["ssid"], signal=signal)))
    for a in p.get("ipv4") or []:
        if not a.get("address"):
            continue
        dhcp = a.get("origin") == "dhcp" or (p.get("dhcp4") and a.get("origin") != "manual")
        lines.append(("IP", f"{a['address']}  /  {_mask(a.get('prefix'))}" + ("  (DHCP)" if dhcp else "")))
    gw = gateway_of(topo, node.id)
    if gw:
        lines.append((tr("Ağ geçidi"), gw))
    return lines


class AdapterRow(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, topo: Topology, node: Node, parent=None):
        super().__init__(parent)
        self.node_id = node.id
        self.setObjectName("adapterRow")
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        icon = QLabel(self)
        icon.setPixmap(make_icon(node.kind, status_color(node), 22).pixmap(22, 22))
        icon.setAlignment(Qt.AlignTop)
        layout.addWidget(icon)
        dim = palette_color(QPalette.PlaceholderText).name()
        parts = [f"<b>{html.escape(node.label)}:</b>"]
        if node.id == topo.internet_via:
            parts[0] += f' <span style="color:{GREEN.name()}">● {html.escape(tr("İnternet çıkışı"))}</span>'
        desc = node.props.get("description") or ""
        if desc and desc != node.label:
            parts.append(f'<span style="color:{dim}">{html.escape(desc)}</span>')
        rows = []
        for label, value in adapter_lines(topo, node):
            if label:
                rows.append(f"<tr><td width='{LABEL_WIDTH}'>{html.escape(label)}:</td><td>{html.escape(value)}</td></tr>")
            else:
                rows.append(f"<tr><td colspan='2'>{html.escape(value)}</td></tr>")
        text = "<br>".join(parts) + (f"<table cellspacing='0' cellpadding='0'>{''.join(rows)}</table>" if rows else "")
        body = QLabel(text, self)
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        body.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(body, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.node_id)
        super().mousePressEvent(event)


class TrayPopup(QFrame):
    adapterClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        # Ust duzey, cercevesiz, odak calmayan pencere (gorev cubugunda dugmesi olmaz).
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        load_ui(self, __file__)
        require(self, "frameHeader", "lblAppIcon", "lblTitle", "lblSummary", "scroll", "rowsContainer",
                "layoutRows", "lblHint")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(WIDTH)
        self.lblAppIcon.setPixmap(icon_pixmap(32))
        self.lblTitle.setText(f"networkPlus {__version__}")
        f = QFont(self.lblTitle.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 2)
        self.lblTitle.setFont(f)
        self.rows: list[AdapterRow] = []
        self._style()

    def _style(self):
        # Renkler paletten: acik/koyu temaya uyar (ADR 0011).
        self.setStyleSheet(
            "TrayPopup { background: palette(base); border: 1px solid palette(mid); }"
            "#frameHeader { border-bottom: 1px solid palette(mid); }"
            "#adapterRow { border-bottom: 1px solid palette(midlight); }"
            "#adapterRow:hover { background: palette(alternate-base); }"
            "QScrollArea, #rowsContainer { background: palette(base); }"
            "#lblHint { color: palette(placeholder-text); padding: 4px; }")

    def set_topology(self, topo: Topology | None):
        # Eski satirlar HEMEN gizlenir (deleteLater olay dongusune kadar ciziliyor, yenisiyle ust
        # uste biniyordu); esneme ogeleri de birikmesin diye tum yerlesim bosaltilir.
        while self.layoutRows.count():
            item = self.layoutRows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.rows = []
        if topo is None:
            self.lblSummary.setText(tr("Ağ durumu okunuyor…"))
            return
        via = topo.nodes.get(topo.internet_via or "")
        self.lblSummary.setText(tr("İnternet: {name} üzerinden").format(name=via.label) if via
                                else tr("İnternet çıkışı yok"))
        for node in popup_adapters(topo):
            row = AdapterRow(topo, node, self.rowsContainer)
            row.clicked.connect(self._on_row_clicked)
            self.layoutRows.addWidget(row)
            self.rows.append(row)
        self.layoutRows.addStretch(1)

    def _on_row_clicked(self, node_id: str):
        self.hide()
        self.adapterClicked.emit(node_id)

    def show_near(self, anchor: QRect):
        """Tepsi simgesinin yanina: gorev cubugu alttaysa ustune, ustteyse altina; ekran icinde kalir."""
        screen = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.rowsContainer.adjustSize()
        content = self.frameHeader.sizeHint().height() + self.rowsContainer.sizeHint().height() \
            + self.lblHint.sizeHint().height() + 4
        height = min(content, int(area.height() * MAX_SCREEN_FRACTION))
        self.setFixedHeight(height)
        x = min(max(anchor.right() - WIDTH, area.left()), area.right() - WIDTH)
        if anchor.center().y() > area.center().y():
            y = max(area.top(), min(anchor.top(), area.bottom()) - height - 4)
        else:
            y = min(area.bottom() - height, max(anchor.bottom(), area.top()) + 4)
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
