"""Rol tabanli katmanli yerlesim (saf; Qt'siz test edilebilir).

Sutunlar (soldan saga, internetin akis yonu):
    0 Internet | 1 Ag gecitleri | 2 Cikis bagdastiricilari | 3 Diger bagdastiricilar
2 ve 3. sutunlar arayuzde "bu bilgisayar" cercevesinin icinde cizilir.
"""

from __future__ import annotations

from .model import EdgeKind, NodeKind, Topology

COL_X = (0.0, 205.0, 440.0, 700.0, 960.0)   # 4: DHCP istemcileri (cerceve disi)
ROW_H = 86.0

HOST_COLUMNS = (2, 3)

_KIND_ORDER = [
    NodeKind.ETHERNET, NodeKind.WIFI, NodeKind.CELLULAR, NodeKind.VPN, NodeKind.BRIDGE,
    NodeKind.HOTSPOT, NodeKind.VM_NAT, NodeKind.VETHERNET, NodeKind.VM_HOST_ONLY,
    NodeKind.BLUETOOTH, NodeKind.CONTAINER, NodeKind.UNKNOWN, NodeKind.LOOPBACK, NodeKind.SYSTEM,
]
_UPSTREAM_EDGES = {EdgeKind.ICS, EdgeKind.NAT, EdgeKind.TUNNEL, EdgeKind.HOTSPOT, EdgeKind.VSWITCH}


def column_of(topo: Topology, node_id: str) -> int:
    node = topo.nodes[node_id]
    if node.kind == NodeKind.INTERNET:
        return 0
    if node.kind == NodeKind.GATEWAY:
        return 1
    if node.kind == NodeKind.DHCP_CLIENTS:
        return 4
    for e in topo.edges:
        if e.dst == node_id and e.kind in (EdgeKind.UPLINK, EdgeKind.INTERNET):
            return 2
        if e.src == node_id and e.kind in _UPSTREAM_EDGES:
            return 2
    return 3


def compute_layout(topo: Topology, show_hidden: bool = False) -> dict[str, tuple[float, float]]:
    visible = {n.id for n in topo.visible_nodes(show_hidden)}
    columns: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: [], 4: []}
    for nid in visible:
        columns[column_of(topo, nid)].append(nid)

    def adapter_key(nid: str):
        n = topo.nodes[nid]
        kind_rank = _KIND_ORDER.index(n.kind) if n.kind in _KIND_ORDER else len(_KIND_ORDER)
        return (nid != topo.internet_via, n.status.value != "up", kind_rank, n.label.lower())

    pos: dict[str, tuple[float, float]] = {}
    col2 = sorted(columns[2], key=adapter_key)
    for i, nid in enumerate(col2):
        pos[nid] = (COL_X[2], i * ROW_H)

    # 3. sutun: once 2. sutundaki kaynagina gore (ICS/NAT hedefleri), sonra digerleri.
    def downstream_key(nid: str):
        sources = [pos[e.src][1] for e in topo.edges if e.dst == nid and e.src in pos]
        return (0, min(sources)) if sources else (1, 0.0), adapter_key(nid)

    col3 = sorted(columns[3], key=downstream_key)
    for i, nid in enumerate(col3):
        pos[nid] = (COL_X[3], i * ROW_H)

    # Ag gecitleri kendi bagdastiricilarinin hizasinda.
    used_rows: set[float] = set()
    for nid in sorted(columns[1]):
        targets = [pos[e.dst][1] for e in topo.edges if e.src == nid and e.dst in pos]
        y = sum(targets) / len(targets) if targets else 0.0
        while y in used_rows:
            y += ROW_H / 2
        used_rows.add(y)
        pos[nid] = (COL_X[1], y)

    # DHCP istemcileri: sunucu kartinin hizasinda, bilgisayar cercevesinin disinda.
    for nid in columns[4]:
        src = [pos[e.src][1] for e in topo.edges if e.dst == nid and e.src in pos]
        pos[nid] = (COL_X[4], src[0] if src else 0.0)

    for nid in columns[0]:
        gws = [pos[g][1] for g in columns[1] if g in pos]
        direct = [pos[e.dst][1] for e in topo.edges if e.src == nid and e.dst in pos]
        ys = gws or direct or [0.0]
        pos[nid] = (COL_X[0], sum(ys) / len(ys))
    return pos
