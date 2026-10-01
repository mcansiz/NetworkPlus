"""DHCP sunucusu hangi kartta calisabilir (ADR 0010) + diyagram katmani. Saf Python.

Sahte (rogue) DHCP sunucusu kurumsal/ev agini bozar: baska cihazlara yanlis adres
dagitir. Bu yuzden internet kartinda, DHCP'den adres alan kartta (o agda zaten sunucu
var) ve Internet paylasimi (ICS / NetworkManager 'shared') acik kartta ENGELLENIR.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import tr
from ..model import Edge, EdgeKind, Node, NodeKind, Status, Topology

CLIENTS_PREFIX = "dhcp-clients:"
_NOT_ELIGIBLE = {NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.CONTAINER, NodeKind.VPN, NodeKind.HOTSPOT,
                 NodeKind.BLUETOOTH, NodeKind.CELLULAR}


@dataclass
class AdapterCheck:
    ok: bool                      # sunucu bu haliyle baslatilabilir
    needs_static: bool = False    # once karta statik IP verilmeli (sonra baslatilabilir)
    needs_enable: bool = False    # statik IP'den sonra kart etkinlestirilmeli (Linux, NM birakmis)
    message: str = ""
    severity: str = ""            # "" | "warning" | "error"
    server_ip: str = ""
    prefix: int = 24


def eligible_adapters(topo: Topology) -> list[Node]:
    return sorted((n for n in topo.nodes.values()
                   if n.is_adapter and n.kind not in _NOT_ELIGIBLE and n.status != Status.NOT_PRESENT),
                  key=lambda n: n.label.lower())


def static_ipv4(node: Node) -> tuple[str, int] | None:
    for a in node.props.get("ipv4") or []:
        if a.get("origin") == "manual" and a.get("address"):
            return a["address"], int(a.get("prefix") or 24)
    return None


def _has_real_dhcp_address(node: Node) -> bool:
    """DHCP'den gercek adres almis mi (169.254 APIPA sayilmaz: o agda sunucu yok demektir)."""
    return any(a.get("address") and not str(a["address"]).startswith("169.254.")
               for a in node.props.get("ipv4") or [])


def check_adapter(topo: Topology, node_id: str) -> AdapterCheck:
    node = topo.nodes.get(node_id)
    if node is None or not node.is_adapter:
        return AdapterCheck(False, message=tr("Bağdaştırıcı bulunamadı."), severity="error")
    if node.kind in _NOT_ELIGIBLE:
        return AdapterCheck(False, message=tr("Bu tür bağdaştırıcıda DHCP sunucusu çalıştırılamaz."),
                            severity="error")
    if node_id == topo.internet_via:
        return AdapterCheck(False, severity="error", message=tr(
            "Bu kart internet bağlantınızı taşıyor. Burada DHCP sunucusu çalıştırmak bağlı olduğunuz "
            "ağdaki cihazlara yanlış adres dağıtır (sahte DHCP); engellendi."))
    if node.props.get("sharing"):
        return AdapterCheck(False, severity="error", message=tr(
            "Bu kartta İnternet paylaşımı açık; paylaşım kendi DHCP sunucusunu çalıştırıyor. "
            "Önce paylaşımı kapatın."))
    if node.status == Status.DISABLED:
        # Linux: yalitilmis kabloda DHCP zaman asimina ugrayinca NM baglantiyi birakir ('disconnected'
        # = devre disi sayilir). Tam da sunucu kurulacak durum: statik IP + etkinlestir + baslat.
        # Windows'ta devre disi kartin IP yigini yok; once kullanici etkinlestirmeli.
        if topo.platform == "linux":
            return AdapterCheck(False, needs_static=True, needs_enable=True, severity="warning", message=tr(
                "Kart etkin değil (NetworkManager bağlantıyı bırakmış; ağda DHCP sunucusu yok). "
                "Başlatınca karta “Sunucu IP'si” verilir, kart etkinleştirilir ve sunucu başlar."))
        return AdapterCheck(False, severity="error", message=tr("Kart devre dışı; önce etkinleştirin."))
    if node.props.get("dhcp4") and _has_real_dhcp_address(node):
        return AdapterCheck(False, severity="error", message=tr(
            "Bu kart adresini bir DHCP sunucusundan alıyor, yani bu ağda zaten bir sunucu var. "
            "İkinci sunucu adres çakışmasına yol açar; engellendi."))
    static = static_ipv4(node)
    if static is None:
        return AdapterCheck(False, needs_static=True, severity="warning", message=tr(
            "Sunucu için kartın sabit (statik) bir IPv4 adresi olmalı. Aşağıdaki “Sunucu IP'si” "
            "karta verilip sunucu başlatılabilir."))
    ip, prefix = static
    warnings = []
    if node.kind in (NodeKind.VM_NAT, NodeKind.VM_HOST_ONLY):
        warnings.append(tr("Sanal makine yazılımının (VMware, VirtualBox, libvirt) bu ağda kendi DHCP "
                           "sunucusu olabilir; kapatılmadıysa iki sunucu çakışır."))
    if node.status != Status.UP:
        warnings.append(tr("Kartta bağlantı yok (kablo takılı değil?). Sunucu başlatılabilir ama bağlantı "
                           "gelene kadar istemciler adres alamaz."))
    return AdapterCheck(True, severity="warning" if warnings else "", server_ip=ip, prefix=prefix,
                        message=" ".join(warnings))


# --------------------------------------------------------------------------- diyagram katmani

def apply_overlay(topo: Topology, adapter_id: str | None, server_ip: str = "",
                  clients: list[dict] | None = None) -> None:
    """Calisan sunucuyu diyagrama ekle: kart → "DHCP istemcileri (n)". adapter_id None ise kaldirir."""
    for nid in [n for n in topo.nodes if n.startswith(CLIENTS_PREFIX)]:
        del topo.nodes[nid]
    topo.edges = [e for e in topo.edges if e.kind != EdgeKind.DHCP]
    if not adapter_id or adapter_id not in topo.nodes:
        return
    clients = clients or []
    names = [c.get("hostname") or c.get("mac", "") for c in clients]
    nid = CLIENTS_PREFIX + adapter_id
    topo.add_node(Node(
        id=nid, kind=NodeKind.DHCP_CLIENTS,
        label=tr("DHCP istemcileri ({count})").format(count=len(clients)),
        status=Status.UP, subtitle=", ".join(c.get("ip", "") for c in clients[:3])
        + ("…" if len(clients) > 3 else ""),
        props={"adapter": adapter_id, "server_ip": server_ip, "clients": list(clients), "names": names}))
    topo.add_edge(Edge(adapter_id, nid, EdgeKind.DHCP, "DHCP", False,             # IP'si ozelliklerde
                       [tr("networkPlus DHCP sunucusu bu kartta çalışıyor ({ip}).").format(ip=server_ip)]))
