"""Uygulama simgesi: pencere, gorev cubugu ve sistem tepsisi.

QPainter ile cizilir (icons.py gibi: dosya yok, her boyutta keskin). Dolu mavi rozet +
beyaz Ethernet (RJ45) yuvasi: koyu ve acik gorev cubugunda okunur. Eski tepsi simgesi seffaf zemin uzerinde
ince yesil Wi-Fi cizgisiydi; gorev cubugunda kayboluyordu (kullanici bildirdi 2026-10-01).
Tepside `status` rengi internet durumudur (yesil / sari / gri).

Tepsi simgesinin piksel boyutunu isletim sistemi belirler (Windows %100'de 16 px); "buyutmek"
= rozeti kenara kadar doldurmak ve cizgileri kalinlastirmak.

Bicem: STYLES (secim 2026-10-01). Paketleme icin .ico: tools/make_app_icon.py.
"""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QPolygonF

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
TOP, BOTTOM = QColor("#1e6fd9"), QColor("#0b3d91")
WHITE = QColor("white")
DEFAULT_STYLE = "port"


def _badge(p: QPainter, margin: float = 0.0):
    grad = QLinearGradient(0, 0, 0, 1)
    grad.setColorAt(0, TOP)
    grad.setColorAt(1, BOTTOM)
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    rect = QRectF(margin, margin, 1 - 2 * margin, 1 - 2 * margin)
    p.drawRoundedRect(rect, 0.20, 0.20)


def _status_node(p: QPainter, center: QPointF, r: float, status: QColor):
    p.setPen(Qt.NoPen)
    p.setBrush(WHITE)
    p.drawEllipse(center, r + 0.055, r + 0.055)             # beyaz halka: her zeminde ayrilir
    p.setBrush(status)
    p.drawEllipse(center, r, r)


def _port(p: QPainter, size: float, status: QColor | None):
    """Ethernet (RJ45) yuvasi: 'ag karti' en dogrudan."""
    _badge(p)
    p.setPen(Qt.NoPen)
    p.setBrush(WHITE)
    p.drawPolygon(QPolygonF([QPointF(0.10, 0.14), QPointF(0.90, 0.14), QPointF(0.90, 0.66),
                             QPointF(0.70, 0.66), QPointF(0.70, 0.82), QPointF(0.30, 0.82),
                             QPointF(0.30, 0.66), QPointF(0.10, 0.66)]))
    p.setBrush(BOTTOM)
    pins = 4 if size <= 24 else 6
    w = 0.56 / (2 * pins - 1)
    for i in range(pins):
        p.drawRect(QRectF(0.22 + i * 2 * w, 0.24, w, 0.20))
    if status is not None:
        _status_node(p, QPointF(0.80, 0.80), 0.17, status)


# Kullanici 2026-10-01'de dort secenekten "port"u secti (digerleri: ag kare/yuvarlak, diyagram).
STYLES = {
    "port": _port,
}


def paint_app_icon(p: QPainter, size: float, status: QColor | None = None, style: str = DEFAULT_STYLE) -> None:
    """`size` kenarli karede ciz. `status` verilirse internet durumu renkli gosterilir."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size, size)
    STYLES.get(style, STYLES[DEFAULT_STYLE])(p, size, status)
    p.restore()


def icon_pixmap(size: int, status: QColor | None = None, style: str = DEFAULT_STYLE) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    paint_app_icon(painter, size, status, style)
    painter.end()
    return pm


def app_icon(status: QColor | None = None, style: str = DEFAULT_STYLE) -> QIcon:
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(icon_pixmap(size, status, style))
    return icon
