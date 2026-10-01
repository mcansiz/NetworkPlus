"""Diyagram tuvali: yakinlastirma (tekerlek), kaydirma (bos alanda surukle).

diagram_panel.ui icinde QGraphicsView'den 'promote' edilir; Designer'da
yerlesimi/boyutu degistirilebilir, cizim davranisi burada kalir.
"""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPalette, QPolygonF
from PyQt5.QtWidgets import QGraphicsView

from ...theme import palette_color

MIN_ZOOM, MAX_ZOOM = 0.2, 3.0
GRID = 24.0


class DiagramView(QGraphicsView):
    zoomChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self._zoom = 1.0

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float):
        value = max(MIN_ZOOM, min(MAX_ZOOM, value))
        self.resetTransform()
        self.scale(value, value)
        self._zoom = value
        self.zoomChanged.emit(round(value * 100))

    def zoom_by(self, factor: float):
        self.set_zoom(self._zoom * factor)

    def fit_all(self):
        scene = self.scene()
        if scene is None or scene.itemsBoundingRect().isNull():
            return
        rect = scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self._zoom = min(1.0, self.transform().m11())   # sigdirirken buyutme: kartlar gercek boyutta
        self.set_zoom(self._zoom)
        self.centerOn(rect.center())

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(1.15 ** steps)
        event.accept()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, palette_color(QPalette.Base))
        dot = palette_color(QPalette.Text)
        dot.setAlpha(28)
        painter.setPen(dot)
        cols = int(rect.width() // GRID) + 2
        rows = int(rect.height() // GRID) + 2
        if cols * rows > 20000:     # cok uzakta nokta cizilmez
            return
        left = (rect.left() // GRID) * GRID
        top = (rect.top() // GRID) * GRID
        points = QPolygonF([QPointF(left + c * GRID, top + r * GRID)
                            for c in range(cols) for r in range(rows)])
        painter.drawPoints(points)
