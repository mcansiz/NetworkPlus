"""Diyagram modulu: yerlesim diagram_panel.ui'da, davranis burada."""

from __future__ import annotations

from PyQt5.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QImage, QPainter, QPalette, QPen
from PyQt5.QtWidgets import QGraphicsLineItem, QGraphicsScene, QWidget

from ...theme import EDGE_STYLE, GREEN, edge_title, neutral_line, palette_color
from ....core.i18n import tr
from ...uiloader import load_ui, require
from ....core.layout import HOST_COLUMNS, column_of, compute_layout
from ....core.model import Edge, EdgeKind, Topology
from .items import EdgeItem, HostFrame, NodeItem


class DiagramPanel(QWidget):
    nodeSelected = pyqtSignal(str)
    edgeSelected = pyqtSignal(str)
    selectionCleared = pyqtSignal()
    connectRequested = pyqtSignal(str, str, QPoint)   # kaynak, hedef, ekran konumu
    nodeContextMenu = pyqtSignal(str, QPoint)
    edgeContextMenu = pyqtSignal(str, QPoint)
    nodePowerRequested = pyqtSignal(str)          # kart ustu guc dugmesi
    nodePropertiesRequested = pyqtSignal(str)     # cift tik

    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "view", "btnFit", "btnRelayout", "btnZoomIn", "btnZoomOut", "lblZoom", "lblLegend")

        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.scene.selectionChanged.connect(self._on_selection)

        self.btnFit.clicked.connect(self.view.fit_all)
        self.btnRelayout.clicked.connect(self.relayout)
        self.btnZoomIn.clicked.connect(lambda: self.view.zoom_by(1.2))
        self.btnZoomOut.clicked.connect(lambda: self.view.zoom_by(1 / 1.2))
        self.view.zoomChanged.connect(lambda z: self.lblZoom.setText(f"{z}%"))

        self.topology: Topology | None = None
        self.show_hidden = False
        self.node_items: dict[str, NodeItem] = {}
        self.edge_items: dict[str, EdgeItem] = {}
        self.frame: HostFrame | None = None
        # Kullanicinin elle tasidigi konumlar (oturum boyunca; InterfaceGuid anahtarli).
        self._manual: dict[str, tuple[float, float]] = {}
        self._rebuilding = False
        # Bekleyen degisiklikler: isaretli dugumler + onizleme kenarlari.
        self._pending_targets: set[str] = set()
        self._preview_edges: list[Edge] = []
        self._preview_items: list[EdgeItem] = []
        self._drag_line: QGraphicsLineItem | None = None
        self._drag_src: str | None = None
        self.lblLegend.setText(self._legend_html())

    # ----------------------------------------------------------------- genel API
    def set_topology(self, topo: Topology, show_hidden: bool | None = None):
        first = self.topology is None
        if show_hidden is not None:
            self.show_hidden = show_hidden
        selected = self.selected_id()
        self.topology = topo
        self._rebuild()
        if selected:
            self.select(selected, center=False)
        if first:
            self.view.fit_all()

    def set_show_hidden(self, value: bool):
        self.show_hidden = value
        if self.topology:
            self._rebuild()

    def relayout(self):
        self._manual.clear()
        if self.topology:
            self._rebuild()
            self.view.fit_all()

    def select(self, item_id: str, center: bool = True):
        item = self.node_items.get(item_id) or self.edge_items.get(item_id)
        if item is None:
            return
        self.scene.clearSelection()
        item.setSelected(True)
        if center:
            self.view.centerOn(item)

    def selected_id(self) -> str | None:
        for item in self.scene.selectedItems():
            if isinstance(item, NodeItem):
                return item.node.id
            if isinstance(item, EdgeItem):
                return item.edge.id
        return None

    def set_pending(self, targets: set[str], preview_edges: list[Edge]):
        """Kuyruktaki degisiklikleri diyagramda goster (kesikli cerceve / onizleme kenari)."""
        self._pending_targets = set(targets)
        self._preview_edges = list(preview_edges)
        for nid, item in self.node_items.items():
            item.set_pending(nid in self._pending_targets)
        self._draw_previews()

    def _draw_previews(self):
        for it in self._preview_items:
            self.scene.removeItem(it)
        self._preview_items.clear()
        for edge in self._preview_edges:
            src, dst = self.node_items.get(edge.src), self.node_items.get(edge.dst)
            if src and dst:
                it = EdgeItem(edge, src, dst, pending=True)
                self.scene.addItem(it)
                self._preview_items.append(it)

    def export_png(self, path: str) -> bool:
        rect = self.scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        image = QImage(int(rect.width() * 2), int(rect.height() * 2), QImage.Format_ARGB32)
        image.fill(palette_color(QPalette.Base))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene.clearSelection()
        self.scene.render(painter, QRectF(image.rect()), rect)
        painter.end()
        return image.save(path)

    # ----------------------------------------------------------------- ic isler
    def _rebuild(self):
        topo = self.topology
        self._rebuilding = True
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self._preview_items.clear()
        self._drag_line = None

        positions = compute_layout(topo, self.show_hidden)
        active_nodes = {e.src for e in topo.edges if e.active} | {e.dst for e in topo.edges if e.active}

        for nid, (x, y) in positions.items():
            node = topo.nodes[nid]
            item = NodeItem(node, nid in active_nodes)
            item.setPos(*self._manual.get(nid, (x, y)))
            item.set_pending(nid in self._pending_targets)
            item.moved.connect(self._on_node_moved)
            item.connectStarted.connect(self._on_connect_started)
            item.connectMoved.connect(self._on_connect_moved)
            item.connectFinished.connect(self._on_connect_finished)
            item.contextRequested.connect(self.nodeContextMenu)
            item.powerRequested.connect(self.nodePowerRequested)
            item.propertiesRequested.connect(self.nodePropertiesRequested)
            self.scene.addItem(item)
            self.node_items[nid] = item

        for edge in topo.edges:
            src, dst = self.node_items.get(edge.src), self.node_items.get(edge.dst)
            if src and dst:
                item = EdgeItem(edge, src, dst)
                item.on_context = self.edgeContextMenu.emit
                self.scene.addItem(item)
                self.edge_items[edge.id] = item
        self._draw_previews()

        notes = [b.message for b in topo.host_badges]
        title = tr("Bu bilgisayar · {host}").format(host=topo.hostname) if topo.hostname else tr("Bu bilgisayar")
        self.frame = HostFrame(title, notes)
        self.scene.addItem(self.frame)
        self._fit_frame()
        self._rebuilding = False

    def _host_items(self) -> list[NodeItem]:
        return [it for nid, it in self.node_items.items()
                if column_of(self.topology, nid) in HOST_COLUMNS]

    def _fit_frame(self):
        if self.frame is not None:
            self.frame.fit([it.scene_rect() for it in self._host_items()])

    def _on_node_moved(self, node_id: str):
        if self._rebuilding:
            return
        item = self.node_items[node_id]
        self._manual[node_id] = (item.pos().x(), item.pos().y())
        for e in list(self.edge_items.values()) + self._preview_items:
            if e.src is item or e.dst is item:
                e.update_path()
        self._fit_frame()

    # ----------------------------------------------------------------- surukleyerek baglama
    def _on_connect_started(self, src_id: str):
        item = self.node_items[src_id]
        start = item.mapToScene(item.handle_center())
        self._drag_src = src_id
        pen = QPen(palette_color(QPalette.Highlight), 2, Qt.DashLine)
        self._drag_line = self.scene.addLine(QLineF(start, start), pen)
        self._drag_line.setZValue(5)

    def _on_connect_moved(self, pos: QPointF):
        if self._drag_line is not None:
            line = self._drag_line.line()
            self._drag_line.setLine(QLineF(line.p1(), pos))

    def _on_connect_finished(self, pos: QPointF):
        if self._drag_line is not None:
            self.scene.removeItem(self._drag_line)
            self._drag_line = None
        src, self._drag_src = self._drag_src, None
        target = next((it for it in self.scene.items(pos)
                       if isinstance(it, NodeItem) and it.node.id != src), None)
        if src and target is not None and target.node.is_adapter:
            self.connectRequested.emit(src, target.node.id, QCursor.pos())

    def _on_selection(self):
        if self._rebuilding:
            return
        items = self.scene.selectedItems()
        if not items:
            self.selectionCleared.emit()
        elif isinstance(items[0], NodeItem):
            self.nodeSelected.emit(items[0].node.id)
        elif isinstance(items[0], EdgeItem):
            self.edgeSelected.emit(items[0].edge.id)

    @staticmethod
    def _legend_html() -> str:
        # Kutu cizim karakterleri (━ ╍ ┅) Cince yazi tipinde yok, kare cikiyordu: her yazi tipinde
        # bulunan tire/nokta kullanilir.
        solid = "<b>——</b>"
        dash = {1: solid, 2: "<b>– –</b>", 3: "<b>· · ·</b>"}
        parts = [f'<span style="color:{GREEN.name()}">{solid}</span> ' + tr("İnternete çıkan yol")]
        for kind in (EdgeKind.UPLINK, EdgeKind.ICS, EdgeKind.HOTSPOT, EdgeKind.NAT,
                     EdgeKind.TUNNEL, EdgeKind.BRIDGE, EdgeKind.VSWITCH, EdgeKind.DHCP):
            color, style, _ = EDGE_STYLE[kind]
            title = edge_title(kind)
            c = (color or neutral_line()).name()
            parts.append(f'<span style="color:{c}">{dash.get(int(style), solid)}</span> {title}')
        return " &nbsp;&nbsp; ".join(parts)
