"""Bagdastirici listesi modulu: yerlesim adapter_list.ui'da, davranis burada."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QTreeWidgetItem, QWidget

from ...icons import make_icon
from ....core.i18n import N_, tr
from ...theme import status_text, status_color
from ...uiloader import load_ui, require
from ....core.model import NodeKind, Topology

GROUPS = [
    (N_("Fiziksel"), {NodeKind.ETHERNET, NodeKind.WIFI, NodeKind.BLUETOOTH, NodeKind.CELLULAR}),
    (N_("VPN / tünel"), {NodeKind.VPN}),
    (N_("Sanal ağlar"), {NodeKind.VM_NAT, NodeKind.VM_HOST_ONLY, NodeKind.VETHERNET, NodeKind.BRIDGE,
                     NodeKind.HOTSPOT, NodeKind.CONTAINER}),
    (N_("Sistem"), {NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.UNKNOWN}),
]
ID_ROLE = Qt.UserRole
TITLE_ROLE = Qt.UserRole + 1
IP_ROLE = Qt.UserRole + 2


class AdapterListPanel(QWidget):
    nodeActivated = pyqtSignal(str)
    showHiddenToggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "tree", "edFilter", "chkShowHidden", "lblCount")
        header = self.tree.header()
        header.setStretchLastSection(True)
        self.tree.setHeaderHidden(True)            # tek sutun: ad + altinda IP
        self.tree.currentItemChanged.connect(self._on_current)
        self.edFilter.textChanged.connect(self._apply_filter)
        self.chkShowHidden.toggled.connect(self._on_show_hidden)
        self.topology: Topology | None = None
        self._items: dict[str, QTreeWidgetItem] = {}

    def set_topology(self, topo: Topology):
        self.topology = topo
        current = self.current_id()
        self.tree.blockSignals(True)
        self.tree.clear()
        self._items.clear()
        adapters = [n for n in topo.nodes.values() if n.is_adapter]
        for title, kinds in GROUPS:
            members = sorted((n for n in adapters if n.kind in kinds),
                             key=lambda n: (n.status.value != "up", n.label.lower()))
            if not members:
                continue
            group = QTreeWidgetItem(self.tree, [title])
            group.setData(0, TITLE_ROLE, title)
            group.setFlags(Qt.ItemIsEnabled)
            group.setFirstColumnSpanned(True)
            f = group.font(0)
            f.setBold(True)
            group.setFont(0, f)
            for n in members:
                v4 = ", ".join(x["address"] for x in n.props.get("ipv4") or [] if x.get("address"))
                # IP adin altinda ikinci satirda (kullanici: IPv4 sutunu gorunmuyordu).
                it = QTreeWidgetItem(group, [f"{n.label}\n{v4}" if v4 else n.label])
                it.setData(0, IP_ROLE, v4)
                it.setIcon(0, make_icon(n.kind, status_color(n)))
                it.setData(0, ID_ROLE, n.id)
                tip = f"{n.props.get('description') or n.label}\n{status_text(n.status)}"
                it.setToolTip(0, tip)
                self._items[n.id] = it
            group.setExpanded(True)
        self.tree.blockSignals(False)
        self._apply_filter()
        if current:
            self.select(current)

    def set_show_hidden(self, value: bool):
        if self.chkShowHidden.isChecked() != value:
            self.chkShowHidden.setChecked(value)

    def current_id(self) -> str | None:
        it = self.tree.currentItem()
        return it.data(0, ID_ROLE) if it else None

    def select(self, node_id: str):
        it = self._items.get(node_id)
        self.tree.blockSignals(True)
        if it is None:
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
        else:
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)
        self.tree.blockSignals(False)

    # ----------------------------------------------------------------- ic isler
    def _on_current(self, current, _previous):
        if current is not None and current.data(0, ID_ROLE):
            self.nodeActivated.emit(current.data(0, ID_ROLE))

    def _on_show_hidden(self, value: bool):
        self._apply_filter()
        self.showHiddenToggled.emit(value)

    def _apply_filter(self):
        if self.topology is None:
            return
        needle = self.edFilter.text().strip().lower()
        show_hidden = self.chkShowHidden.isChecked()
        shown = total = 0
        for nid, it in self._items.items():
            n = self.topology.nodes[nid]
            total += 1
            hay = " ".join([n.label, n.props.get("description") or "", it.data(0, IP_ROLE) or ""]).lower()
            visible = (show_hidden or not n.hidden) and (not needle or needle in hay)
            it.setHidden(not visible)
            shown += visible
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            count = sum(not g.child(j).isHidden() for j in range(g.childCount()))
            g.setText(0, f"{tr(g.data(0, TITLE_ROLE))} ({count})")
            g.setHidden(count == 0)
        self.lblCount.setText(tr("{shown} / {total} bağdaştırıcı gösteriliyor").format(shown=shown, total=total))
