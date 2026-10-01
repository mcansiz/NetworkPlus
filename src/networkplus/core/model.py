"""Topoloji veri modeli (spec: .claude/specs/topology-model.md).

Saf veri; Qt'den ve isletim sisteminden bagimsizdir. Kenarlar her zaman
"internetin aktigi yon"de cizilir: Internet -> ag gecidi -> bagdastirici ->
(ICS / NAT / kopru) -> asagi akis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeKind(str, Enum):
    INTERNET = "internet"
    GATEWAY = "gateway"
    ETHERNET = "ethernet"
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    CELLULAR = "cellular"
    VPN = "vpn"
    VM_NAT = "vm_nat"
    VM_HOST_ONLY = "vm_host_only"
    VETHERNET = "vethernet"
    BRIDGE = "bridge"
    HOTSPOT = "hotspot"          # Wi-Fi Direct sanal bagdastirici (Mobil Hotspot)
    CONTAINER = "container"      # docker/veth
    LOOPBACK = "loopback"
    SYSTEM = "system"            # WAN Miniport, Teredo, 6to4, Kernel Debug...
    UNKNOWN = "unknown"
    DHCP_CLIENTS = "dhcp_clients"  # networkPlus DHCP sunucusunun istemcileri (katman)


# Bagdastirici olmayan, keşif sirasinda uretilen dugumler.
SYNTHETIC_KINDS = {NodeKind.INTERNET, NodeKind.GATEWAY, NodeKind.DHCP_CLIENTS}


class Status(str, Enum):
    UP = "up"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"
    NOT_PRESENT = "not_present"
    UNKNOWN = "unknown"


class Connectivity(str, Enum):
    INTERNET = "internet"
    LOCAL = "local"
    NONE = "none"
    UNKNOWN = "unknown"


class EdgeKind(str, Enum):
    INTERNET = "internet"   # Internet -> ag gecidi (veya dogrudan bagdastirici)
    UPLINK = "uplink"       # ag gecidi -> bagdastirici (varsayilan rota)
    ICS = "ics"             # public -> private internet paylasimi
    HOTSPOT = "hotspot"     # kaynak -> Mobil Hotspot
    NAT = "nat"             # host cikisi -> sanal makine NAT agi
    TUNNEL = "tunnel"       # tasiyici -> VPN
    BRIDGE = "bridge"       # uye -> kopru
    VSWITCH = "vswitch"     # fiziksel NIC -> Hyper-V vEthernet
    DHCP = "dhcp"           # bagdastirici -> networkPlus DHCP istemcileri


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Badge:
    code: str
    severity: Severity
    message: str


@dataclass
class Node:
    id: str
    kind: NodeKind
    label: str
    status: Status = Status.UNKNOWN
    connectivity: Connectivity = Connectivity.UNKNOWN
    hidden: bool = False
    subtitle: str = ""
    # Normalize snapshot'taki bagdastirici kaydi (sentetik dugumlerde ozet).
    props: dict = field(default_factory=dict)
    badges: list[Badge] = field(default_factory=list)

    @property
    def is_adapter(self) -> bool:
        return self.kind not in SYNTHETIC_KINDS

    @property
    def worst_severity(self) -> Severity | None:
        order = [Severity.ERROR, Severity.WARNING, Severity.INFO]
        for sev in order:
            if any(b.severity == sev for b in self.badges):
                return sev
        return None


@dataclass
class Edge:
    src: str
    dst: str
    kind: EdgeKind
    label: str = ""
    active: bool = False
    # Iliskinin hangi veriden cikarildigi (inspector'da "neden?").
    evidence: list[str] = field(default_factory=list)
    # Soluk cizilir (ör. ag gecidinden internete erisim yok). Karar METINDEN verilmez:
    # etiket cevrilince "internet yok" karsilastirmasi bozulurdu.
    dim: bool = False

    @property
    def id(self) -> str:
        return f"{self.kind.value}:{self.src}->{self.dst}"


@dataclass
class Topology:
    platform: str
    hostname: str
    taken_at: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    internet_via: str | None = None
    host_badges: list[Badge] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)

    def add_node(self, node: Node) -> Node:
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: Edge) -> Edge:
        self.edges.append(edge)
        return edge

    def edges_of(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.src == node_id or e.dst == node_id]

    def visible_nodes(self, show_hidden: bool = False) -> list[Node]:
        return [n for n in self.nodes.values() if show_hidden or not n.hidden]
