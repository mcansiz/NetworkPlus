"""Anlamsal renkler. Genel gorunum QSS temalarindan gelir (ui/themes, ADR 0011); notr renkler
(zemin, metin, secim) her zaman PALETTEN okunur ki acik/koyu temada dogru cizilsin. Sabit renk
yalnizca anlam tasiyan yerlerde: durum, iliski turu (ai_rules/50).
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

from ..core.i18n import N_, tr
from ..core.model import Connectivity, EdgeKind, Node, NodeKind, Severity, Status

GREEN = QColor("#2e7d32")
AMBER = QColor("#e0a100")
RED = QColor("#c62828")
GRAY = QColor("#9e9e9e")
ORANGE = QColor("#ef6c00")
BLUE = QColor("#1565c0")
PURPLE = QColor("#7b1fa2")
TEAL = QColor("#00838f")

SEVERITY_COLOR = {Severity.ERROR: RED, Severity.WARNING: AMBER, Severity.INFO: BLUE}

STATUS_TEXT = {
    Status.UP: N_("Bağlı"),
    Status.DISCONNECTED: N_("Bağlantı yok"),
    Status.DISABLED: N_("Devre dışı"),
    Status.NOT_PRESENT: N_("Aygıt yok"),
    Status.UNKNOWN: N_("Bilinmiyor"),
}
CONNECTIVITY_TEXT = {
    Connectivity.INTERNET: N_("İnternet"),
    Connectivity.LOCAL: N_("Yalnızca yerel ağ"),
    Connectivity.NONE: N_("Trafik yok"),
    Connectivity.UNKNOWN: "—",
}

# (renk, cizgi stili, etiket)
EDGE_STYLE = {
    EdgeKind.INTERNET: (None, Qt.SolidLine, N_("İnternet")),
    EdgeKind.UPLINK: (None, Qt.SolidLine, N_("Varsayılan rota")),
    EdgeKind.ICS: (ORANGE, Qt.DashLine, N_("İnternet paylaşımı (ICS)")),
    EdgeKind.HOTSPOT: (ORANGE, Qt.DotLine, N_("Mobil Hotspot")),
    EdgeKind.NAT: (BLUE, Qt.DashLine, N_("NAT")),
    EdgeKind.TUNNEL: (PURPLE, Qt.DotLine, N_("VPN tüneli")),
    EdgeKind.BRIDGE: (PURPLE, Qt.SolidLine, N_("Köprü üyeliği")),
    EdgeKind.VSWITCH: (TEAL, Qt.SolidLine, N_("Hyper-V sanal anahtar")),
    EdgeKind.DHCP: (TEAL, Qt.DashLine, N_("DHCP sunucusu (networkPlus)")),
}



def status_text(status: Status) -> str:
    return tr(STATUS_TEXT[status])


def connectivity_text(conn: Connectivity) -> str:
    return tr(CONNECTIVITY_TEXT[conn])


def edge_title(kind: EdgeKind) -> str:
    return tr(EDGE_STYLE[kind][2])


def palette_color(role: QPalette.ColorRole) -> QColor:
    return QApplication.palette().color(role)


def neutral_line() -> QColor:
    c = palette_color(QPalette.Text)
    c.setAlpha(150)
    return c


def status_color(node: Node) -> QColor:
    """Dugum durum rengi: yesil internet, sari yerel, gri bagli degil, kirmizi hata."""
    if node.worst_severity == Severity.ERROR:
        return RED
    if node.status != Status.UP:
        return GRAY
    if node.kind == NodeKind.INTERNET or node.connectivity == Connectivity.INTERNET:
        return GREEN
    if node.connectivity in (Connectivity.LOCAL, Connectivity.NONE):
        return AMBER
    return BLUE
