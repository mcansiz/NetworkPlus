"""Dugum turu ikonlari QPainter ile cizilir (SVG/tema ikonu yok: platformdan
bagimsiz ve her boyutta keskin). Yeni tur -> DRAWERS'a bir cizici eklenir.

Her cizici 0..1 birim karesinde cizer; `paint_icon` olcekler.
"""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from ..core.model import NodeKind


def _pen(p: QPainter, color: QColor, w: float = 0.07):
    p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def _globe(p: QPainter, c: QColor):
    """Internet: dunya (cember + ekvator + meridyenler). Eski bulut, elipslerin birlesiminden
    olusuyordu; kucuk boyutta dolguda delikler kaliyor ve anlasilmiyordu (kullanici bildirdi)."""
    _pen(p, c, 0.065)
    p.drawEllipse(QRectF(0.12, 0.12, 0.76, 0.76))
    p.drawEllipse(QRectF(0.32, 0.12, 0.36, 0.76))           # meridyenler
    p.drawLine(QPointF(0.5, 0.12), QPointF(0.5, 0.88))
    p.drawLine(QPointF(0.12, 0.5), QPointF(0.88, 0.5))       # ekvator
    p.drawLine(QPointF(0.20, 0.31), QPointF(0.80, 0.31))     # paraleller
    p.drawLine(QPointF(0.20, 0.69), QPointF(0.80, 0.69))


def _router(p: QPainter, c: QColor):
    """Cisco tarzi yonlendirici: yandan silindir, ust yuzde karsilikli iki ok."""
    left, right, top, face_h, body_h = 0.06, 0.94, 0.18, 0.36, 0.30
    # Govde (yan yuz + alt yay)
    body = QPainterPath()
    body.moveTo(left, top + face_h / 2)
    body.lineTo(left, top + face_h / 2 + body_h)
    body.arcTo(QRectF(left, top + body_h, right - left, face_h), 180, 180)
    body.lineTo(right, top + face_h / 2)
    body.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c).darker(115))
    p.drawPath(body)
    # Ust yuz (acik ton)
    p.setBrush(QColor(c).lighter(125))
    p.drawEllipse(QRectF(left, top, right - left, face_h))
    # Oklar: ust → , alt ←
    white = QColor("white")
    cy = top + face_h / 2
    for y, x1, x2 in ((cy - 0.065, 0.27, 0.70), (cy + 0.065, 0.73, 0.30)):
        _pen(p, white, 0.055)
        p.drawLine(QPointF(x1, y), QPointF(x2, y))
        d = 0.075 if x2 > x1 else -0.075
        p.setPen(Qt.NoPen)
        p.setBrush(white)
        p.drawPolygon(QPolygonF([QPointF(x2 + d * 0.6, y), QPointF(x2 - d * 0.6, y - 0.055),
                                 QPointF(x2 - d * 0.6, y + 0.055)]))


def _ethernet(p: QPainter, c: QColor):
    _pen(p, c)
    poly = QPolygonF([QPointF(0.18, 0.25), QPointF(0.82, 0.25), QPointF(0.82, 0.68),
                      QPointF(0.66, 0.68), QPointF(0.66, 0.80), QPointF(0.34, 0.80),
                      QPointF(0.34, 0.68), QPointF(0.18, 0.68)])
    p.drawPolygon(poly)
    for i in range(4):
        x = 0.32 + i * 0.12
        p.drawLine(QPointF(x, 0.33), QPointF(x, 0.45))


def _wifi(p: QPainter, c: QColor):
    _pen(p, c, 0.08)
    for i, r in enumerate((0.40, 0.27, 0.14)):
        rect = QRectF(0.5 - r, 0.72 - r, 2 * r, 2 * r)
        p.drawArc(rect, 45 * 16, 90 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(0.5, 0.72), 0.06, 0.06)


def _vpn(p: QPainter, c: QColor):
    _pen(p, c)
    p.drawArc(QRectF(0.32, 0.14, 0.36, 0.40), 0, 180 * 16)
    p.drawLine(QPointF(0.32, 0.34), QPointF(0.32, 0.45))
    p.drawLine(QPointF(0.68, 0.34), QPointF(0.68, 0.45))
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(0.22, 0.44, 0.56, 0.42), 0.06, 0.06)


def _vm(p: QPainter, c: QColor):
    _pen(p, c)
    p.drawRoundedRect(QRectF(0.12, 0.18, 0.76, 0.52), 0.05, 0.05)
    p.drawLine(QPointF(0.5, 0.70), QPointF(0.5, 0.82))
    p.drawLine(QPointF(0.32, 0.84), QPointF(0.68, 0.84))
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRect(QRectF(0.36, 0.32, 0.28, 0.24))


def _bridge(p: QPainter, c: QColor):
    _pen(p, c)
    p.drawLine(QPointF(0.08, 0.62), QPointF(0.92, 0.62))
    p.drawArc(QRectF(0.14, 0.30, 0.72, 0.64), 0, 180 * 16)
    for x in (0.30, 0.50, 0.70):
        p.drawLine(QPointF(x, 0.62), QPointF(x, 0.40 if x == 0.5 else 0.45))


def _hotspot(p: QPainter, c: QColor):
    _pen(p, c)
    p.drawLine(QPointF(0.5, 0.45), QPointF(0.5, 0.88))
    p.drawLine(QPointF(0.35, 0.88), QPointF(0.65, 0.88))
    for r in (0.18, 0.32):
        p.drawArc(QRectF(0.5 - r, 0.40 - r, 2 * r, 2 * r), 40 * 16, 100 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(0.5, 0.42), 0.06, 0.06)


def _bluetooth(p: QPainter, c: QColor):
    _pen(p, c)
    pts = [QPointF(0.30, 0.32), QPointF(0.68, 0.66), QPointF(0.50, 0.84), QPointF(0.50, 0.16),
           QPointF(0.68, 0.34), QPointF(0.30, 0.68)]
    p.drawPolyline(QPolygonF(pts))


def _cellular(p: QPainter, c: QColor):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    for i in range(4):
        h = 0.18 + i * 0.16
        p.drawRect(QRectF(0.16 + i * 0.18, 0.84 - h, 0.12, h))


def _chip(p: QPainter, c: QColor):
    _pen(p, c)
    p.drawRoundedRect(QRectF(0.26, 0.26, 0.48, 0.48), 0.05, 0.05)
    for i in range(3):
        o = 0.36 + i * 0.14
        for a, b in ((QPointF(o, 0.12), QPointF(o, 0.26)), (QPointF(o, 0.74), QPointF(o, 0.88)),
                     (QPointF(0.12, o), QPointF(0.26, o)), (QPointF(0.74, o), QPointF(0.88, o))):
            p.drawLine(a, b)


def _devices(p: QPainter, c: QColor):
    """DHCP istemcileri: arkada bir ekran, onde bir telefon."""
    _pen(p, c)
    p.drawRoundedRect(QRectF(0.08, 0.20, 0.58, 0.40), 0.05, 0.05)
    p.drawLine(QPointF(0.37, 0.60), QPointF(0.37, 0.72))
    p.drawLine(QPointF(0.24, 0.74), QPointF(0.50, 0.74))
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(0.62, 0.38, 0.28, 0.46), 0.05, 0.05)
    p.setBrush(QColor("white"))
    p.drawRect(QRectF(0.66, 0.44, 0.20, 0.30))


def _loop(p: QPainter, c: QColor):
    _pen(p, c)
    p.drawArc(QRectF(0.2, 0.2, 0.6, 0.6), 60 * 16, 300 * 16)
    p.drawLine(QPointF(0.66, 0.26), QPointF(0.76, 0.18))
    p.drawLine(QPointF(0.66, 0.26), QPointF(0.78, 0.32))


DRAWERS = {
    NodeKind.INTERNET: _globe,
    NodeKind.GATEWAY: _router,
    NodeKind.ETHERNET: _ethernet,
    NodeKind.WIFI: _wifi,
    NodeKind.VPN: _vpn,
    NodeKind.VM_NAT: _vm,
    NodeKind.VM_HOST_ONLY: _vm,
    NodeKind.VETHERNET: _vm,
    NodeKind.BRIDGE: _bridge,
    NodeKind.HOTSPOT: _hotspot,
    NodeKind.BLUETOOTH: _bluetooth,
    NodeKind.CELLULAR: _cellular,
    NodeKind.CONTAINER: _chip,
    NodeKind.LOOPBACK: _loop,
    NodeKind.SYSTEM: _chip,
    NodeKind.UNKNOWN: _chip,
    NodeKind.DHCP_CLIENTS: _devices,
}


def paint_icon(p: QPainter, kind: NodeKind, rect: QRectF, color: QColor) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.topLeft())
    p.scale(rect.width(), rect.height())
    DRAWERS.get(kind, _chip)(p, color)
    p.restore()


def make_icon(kind: NodeKind, color: QColor, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_icon(p, kind, QRectF(0, 0, size, size), color)
    p.end()
    return QIcon(pm)
