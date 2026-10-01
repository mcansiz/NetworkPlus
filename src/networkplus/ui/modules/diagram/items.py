"""Diyagram ogeleri: dugum karti, iliski kenari, "bu bilgisayar" cercevesi."""

from __future__ import annotations

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPainterPathStroker, QPalette, QPen,
    QPolygonF,
)
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QStyle

from ...icons import paint_icon
from ...theme import (
    EDGE_STYLE, GRAY, GREEN, SEVERITY_COLOR, edge_title, neutral_line, palette_color, status_color,
)
from ....core.discovery import kind_label
from ....core.i18n import tr
from ....core.model import Edge, EdgeKind, Node, NodeKind, Status

NODE_W = 168.0
NODE_H = 54.0


HANDLE_R = 6.0
_NO_HANDLE = {NodeKind.SYSTEM, NodeKind.LOOPBACK}


class NodeItem(QGraphicsObject):
    moved = pyqtSignal(str)
    # Sag kenardaki baglanti noktasindan surukleyerek iliski kurma.
    connectStarted = pyqtSignal(str)
    connectMoved = pyqtSignal(QPointF)
    connectFinished = pyqtSignal(QPointF)
    contextRequested = pyqtSignal(str, QPoint)
    # Uzerine gelince cikan dugmeler ve cift tik (kullanici istegi: grafikten etkin/devre disi, ozellikler).
    powerRequested = pyqtSignal(str)
    propertiesRequested = pyqtSignal(str)

    def __init__(self, node: Node, on_active_path: bool):
        super().__init__()
        self.node = node
        self.on_active_path = on_active_path
        self.pending = False
        self._hover = False
        self._connecting = False
        self.has_handle = node.is_adapter and node.kind not in _NO_HANDLE
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        self.setCursor(Qt.PointingHandCursor)
        tips = [f"<b>{node.label}</b>", kind_label(node.kind)]
        if node.subtitle:
            tips.append(node.subtitle)
        tips += [f"• {b.message}" for b in node.badges]
        self._tooltip = "<br>".join(t for t in tips if t)
        self.setToolTip(self._tooltip)

    def boundingRect(self) -> QRectF:
        return QRectF(-8, -8, NODE_W + 16 + HANDLE_R, NODE_H + 16)

    def center(self) -> QPointF:
        return self.pos() + QPointF(NODE_W / 2, NODE_H / 2)

    def scene_rect(self) -> QRectF:
        return QRectF(self.pos(), QRectF(0, 0, NODE_W, NODE_H).size())

    def handle_center(self) -> QPointF:
        return QPointF(NODE_W, NODE_H / 2)

    def _in_handle(self, pos: QPointF) -> bool:
        if not self.has_handle:
            return False
        d = pos - self.handle_center()
        return d.x() * d.x() + d.y() * d.y() <= (HANDLE_R + 4) ** 2

    # -- kart ustu dugmeler (yalniz bagdastiricilarda, uzerine gelince)
    BTN_R = 7.5

    def _btn_power(self) -> QPointF:
        return QPointF(NODE_W - 29, 11)

    def _btn_menu(self) -> QPointF:
        return QPointF(NODE_W - 11, 11)

    def _hit(self, pos: QPointF, center: QPointF) -> bool:
        d = pos - center
        return self.has_handle and self._hover and d.x() * d.x() + d.y() * d.y() <= (self.BTN_R + 2) ** 2

    def set_pending(self, value: bool):
        if self.pending != value:
            self.pending = value
            self.update()

    def itemChange(self, change, value):
        node = getattr(self, "node", None)            # yok edilirken cagrilabilir
        if change == QGraphicsItem.ItemPositionHasChanged and node is not None:
            self.moved.emit(node.id)
        return super().itemChange(change, value)

    # -- surukleyerek baglama
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._hit(event.pos(), self._btn_power()):
            self.powerRequested.emit(self.node.id)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._hit(event.pos(), self._btn_menu()):
            self.contextRequested.emit(self.node.id, event.screenPos())
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._in_handle(event.pos()):
            self._connecting = True
            self.connectStarted.emit(self.node.id)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._connecting:
            self.connectMoved.emit(event.scenePos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._connecting:
            self._connecting = False
            self.connectFinished.emit(event.scenePos())
            return
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.node.is_adapter:
            self.propertiesRequested.emit(self.node.id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def hoverMoveEvent(self, event):
        pos = event.pos()
        on_power, on_menu = self._hit(pos, self._btn_power()), self._hit(pos, self._btn_menu())
        self.setCursor(Qt.CrossCursor if self._in_handle(pos) else Qt.PointingHandCursor)
        if on_power:
            off = self.node.status == Status.DISABLED
            self.setToolTip(tr("Etkinleştir") if off else tr("Devre dışı bırak"))
        elif on_menu:
            self.setToolTip(tr("İşlemler (sağ tık ile aynı)"))
        else:
            self.setToolTip(self._tooltip)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        self.contextRequested.emit(self.node.id, event.screenPos())
        event.accept()

    def paint(self, p: QPainter, option, widget=None):
        n = self.node
        p.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        accent = status_color(n)
        body = QRectF(0, 0, NODE_W, NODE_H)

        if self.pending:
            p.setPen(QPen(palette_color(QPalette.Highlight), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(body.adjusted(-5, -5, 5, 5), 12, 12)

        border = palette_color(QPalette.Highlight) if selected else (
            GREEN if self.on_active_path else accent)
        width = 3.0 if (selected or self.on_active_path) else 1.6
        p.setPen(QPen(border, width))
        p.setBrush(palette_color(QPalette.Base))
        p.drawRoundedRect(body, 7, 7)

        # Sol serit + ikon
        strip = QColor(accent)
        strip.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(strip)
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, 40, NODE_H - 2), 6, 6)
        p.drawPath(path)
        paint_icon(p, n.kind, QRectF(6, NODE_H / 2 - 14, 28, 28), accent)

        text = palette_color(QPalette.Text)
        dim = QColor(text)
        dim.setAlpha(150)
        x, w = 46.0, NODE_W - 46 - 16

        f = QFont(p.font())
        f.setBold(True)
        p.setFont(f)
        p.setPen(text)
        p.drawText(QRectF(x, 3, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(n.label, Qt.ElideRight, int(w)))

        f2 = QFont(p.font())
        f2.setBold(False)
        f2.setPointSizeF(max(6.5, f2.pointSizeF() - 1.5))
        p.setFont(f2)
        fm = QFontMetrics(f2)
        p.setPen(text)
        p.drawText(QRectF(x, 20, w + 12, 15), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(n.subtitle, Qt.ElideRight, int(w + 12)))
        p.setPen(dim)
        p.drawText(QRectF(x, 35, w + 12, 15), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(kind_label(n.kind), Qt.ElideRight, int(w + 12)))

        if self.has_handle and self._hover:
            self._paint_buttons(p, accent)
        else:
            # Durum noktasi
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawEllipse(QPointF(NODE_W - 9, 9), 4, 4)

        # Sorun rozeti
        sev = n.worst_severity
        if sev is not None:
            c = SEVERITY_COLOR[sev]
            center = QPointF(NODE_W - 10, NODE_H - 10)
            p.setBrush(c)
            p.drawEllipse(center, 6.5, 6.5)
            fb = QFont(f)
            fb.setPointSizeF(max(7.0, fb.pointSizeF() - 1))
            p.setFont(fb)
            p.setPen(QColor("white"))
            p.drawText(QRectF(center.x() - 7, center.y() - 7, 14, 14), Qt.AlignCenter,
                       "i" if sev.value == "info" else "!")

        # Baglanti noktasi (uzerine gelince ya da secilince)
        if self.has_handle and (self._hover or selected):
            p.setPen(QPen(palette_color(QPalette.Base), 2))
            p.setBrush(palette_color(QPalette.Highlight))
            p.drawEllipse(self.handle_center(), HANDLE_R, HANDLE_R)


    def _paint_buttons(self, p: QPainter, accent: QColor):
        base, text = palette_color(QPalette.Base), palette_color(QPalette.Text)
        r = self.BTN_R
        # Guc: etkinse yesil/renkli, devre disiysa gri
        c = self._btn_power()
        on = self.node.status != Status.DISABLED
        color = GREEN if on else GRAY
        p.setPen(QPen(color, 1.2))
        p.setBrush(base)
        p.drawEllipse(c, r, r)
        p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(c.x() - 4, c.y() - 3.5, 8, 8), 120 * 16, 300 * 16)
        p.drawLine(QPointF(c.x(), c.y() - 5), QPointF(c.x(), c.y() - 0.5))
        # Menu: uc nokta
        c = self._btn_menu()
        p.setPen(QPen(text, 1.0))
        p.setBrush(base)
        p.drawEllipse(c, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(text)
        for dx in (-3.2, 0, 3.2):
            p.drawEllipse(QPointF(c.x() + dx, c.y()), 1.1, 1.1)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, edge: Edge, src: NodeItem, dst: NodeItem, pending: bool = False):
        super().__init__()
        self.edge = edge
        self.src = src
        self.dst = dst
        self.pending = pending          # henuz uygulanmamis (kuyruktaki) iliski onizlemesi
        self.on_context = None          # callable(edge_id, QPoint) — panel baglar
        self.setFlag(QGraphicsItem.ItemIsSelectable, not pending)
        self.setZValue(1)
        self._arrow = QPolygonF()
        self._label_pos = QPointF()
        color, style, _ = EDGE_STYLE[edge.kind]
        title = edge_title(edge.kind)
        self._title = title
        lines = [f"<b>{title}</b>", edge.label] + edge.evidence
        if pending:
            lines.insert(1, tr("Bekleyen değişiklik — Uygula ile gerçekleşir"))
        self.setToolTip("<br>".join(lines))
        self.update_path()

    def contextMenuEvent(self, event):
        if self.on_context is not None and not self.pending:
            self.on_context(self.edge.id, event.screenPos())
            event.accept()

    # -- stil
    def _pen(self, selected: bool) -> QPen:
        if self.pending:
            return QPen(palette_color(QPalette.Highlight), 2.4, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)
        color, style, _ = EDGE_STYLE[self.edge.kind]
        weak = self.edge.dim
        if self.edge.active:
            color, width = GREEN, 3.2
        else:
            color = color or (GRAY if weak else neutral_line())
            width = 1.8
        if weak:
            style = Qt.DashLine
        if selected:
            color = palette_color(QPalette.Highlight)
            width += 1.2
        pen = QPen(color, width, style, Qt.RoundCap, Qt.RoundJoin)
        return pen

    # -- geometri
    def update_path(self):
        self.prepareGeometryChange()
        s, d = self.src.scene_rect(), self.dst.scene_rect()
        if self.pending:
            # Onizleme ayni sutundaki mevcut kenarlarla cakismasin: yayi disa it.
            s, d = s.adjusted(0, 0, 18, 0), d.adjusted(0, 0, 18, 0)
        if d.left() >= s.right() + 20:
            p1, p2 = QPointF(s.right(), s.center().y()), QPointF(d.left(), d.center().y())
            dx = (p2.x() - p1.x()) / 2
            c1, c2 = p1 + QPointF(dx, 0), p2 - QPointF(dx, 0)
            direction = QPointF(1, 0)
        elif s.left() >= d.right() + 20:
            p1, p2 = QPointF(s.left(), s.center().y()), QPointF(d.right(), d.center().y())
            dx = (p1.x() - p2.x()) / 2
            c1, c2 = p1 - QPointF(dx, 0), p2 + QPointF(dx, 0)
            direction = QPointF(-1, 0)
        else:
            # Ayni sutun: saga dogru kivrilan yay.
            p1, p2 = QPointF(s.right(), s.center().y()), QPointF(d.right(), d.center().y())
            bulge = 70 + abs(p2.y() - p1.y()) * 0.15
            c1, c2 = p1 + QPointF(bulge, 0), p2 + QPointF(bulge, 0)
            direction = QPointF(-1, 0)
        path = QPainterPath(p1)
        path.cubicTo(c1, c2, p2)
        self.setPath(path)

        size = 11.0
        tip = p2
        back = tip - direction * size
        normal = QPointF(-direction.y(), direction.x()) * (size * 0.5)
        self._arrow = QPolygonF([tip, back + normal, back - normal])
        self._label_pos = path.pointAtPercent(0.5)

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-80, -20, 80, 20)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        pen = self._pen(selected)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(self.path())
        p.setPen(QPen(pen.color(), 1))
        p.setBrush(pen.color())
        p.drawPolygon(self._arrow)

        if self.edge.label:
            f = QFont(p.font())
            f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
            p.setFont(f)
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(self.edge.label) + 12
            th = fm.height() + 4
            r = QRectF(self._label_pos.x() - tw / 2, self._label_pos.y() - th / 2, tw, th)
            bg = palette_color(QPalette.Base)
            p.setPen(QPen(pen.color(), 1))
            p.setBrush(bg)
            p.drawRoundedRect(r, th / 2, th / 2)
            p.setPen(pen.color() if self.edge.kind != EdgeKind.UPLINK or self.edge.active
                     else palette_color(QPalette.Text))
            p.drawText(r, Qt.AlignCenter, self.edge.label)


class HostFrame(QGraphicsItem):
    """Bu bilgisayarin bagdastiricilarini cevreleyen cerceve."""

    PAD = 18.0

    def __init__(self, title: str, notes: list[str]):
        super().__init__()
        self.title = title
        self.notes = notes
        self.setZValue(0)
        self._rect = QRectF()

    def fit(self, rects: list[QRectF]):
        self.prepareGeometryChange()
        if not rects:
            self._rect = QRectF()
            return
        r = rects[0]
        for x in rects[1:]:
            r = r.united(x)
        extra = 18.0 * len(self.notes)
        self._rect = r.adjusted(-self.PAD, -self.PAD - 26, self.PAD + 60, self.PAD + extra)

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-2, -2, 2, 2)

    def paint(self, p: QPainter, option, widget=None):
        if self._rect.isNull():
            return
        p.setRenderHint(QPainter.Antialiasing)
        c = palette_color(QPalette.Text)
        c.setAlpha(70)
        fill = palette_color(QPalette.AlternateBase)
        fill.setAlpha(120)
        p.setPen(QPen(c, 1.4, Qt.DashLine))
        p.setBrush(fill)
        p.drawRoundedRect(self._rect, 16, 16)
        f = QFont(p.font())
        f.setBold(True)
        p.setFont(f)
        p.setPen(palette_color(QPalette.Text))
        p.drawText(self._rect.adjusted(16, 8, -16, 0), Qt.AlignLeft | Qt.AlignTop, self.title)
        f.setBold(False)
        p.setFont(f)
        for i, note in enumerate(self.notes):
            y = self._rect.bottom() - 10 - 18 * (len(self.notes) - i)
            p.drawText(QRectF(self._rect.left() + 16, y, self._rect.width() - 32, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, note)
