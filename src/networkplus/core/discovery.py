"""Normalize snapshot -> Topology: dugumler, iliskiler (kenarlar), sorun rozetleri.

Senaryolar: .claude/docs/senaryo-analizi.md (S1-S11).
"""

from __future__ import annotations

import ipaddress

from .classify import classify, default_hidden
from .i18n import N_, tr
from .model import (
    Badge, Connectivity, Edge, EdgeKind, Node, NodeKind, Severity, Status, Topology,
)

INTERNET_ID = "internet"

KIND_LABELS = {
    NodeKind.INTERNET: N_("İnternet"),
    NodeKind.GATEWAY: N_("Ağ geçidi"),
    NodeKind.ETHERNET: N_("Ethernet"),
    NodeKind.WIFI: N_("Wi-Fi"),
    NodeKind.BLUETOOTH: N_("Bluetooth"),
    NodeKind.CELLULAR: N_("Hücresel"),
    NodeKind.VPN: N_("VPN / tünel"),
    NodeKind.VM_NAT: N_("Sanal ağ (NAT)"),
    NodeKind.VM_HOST_ONLY: N_("Sanal ağ (yalnız host)"),
    NodeKind.VETHERNET: N_("Hyper-V vEthernet"),
    NodeKind.BRIDGE: N_("Ağ köprüsü"),
    NodeKind.HOTSPOT: N_("Mobil Hotspot"),
    NodeKind.CONTAINER: N_("Konteyner"),
    NodeKind.LOOPBACK: N_("Geri döngü"),
    NodeKind.SYSTEM: N_("Sistem arayüzü"),
    NodeKind.UNKNOWN: N_("Bilinmeyen"),
    NodeKind.DHCP_CLIENTS: N_("DHCP istemcileri"),
}


def kind_label(kind: NodeKind) -> str:
    """Gosterim icin cevrilmis tur adi."""
    return tr(KIND_LABELS.get(kind, ""))


def build_topology(snap: dict) -> Topology:
    platform = snap.get("platform", "windows")
    topo = Topology(
        platform=platform,
        hostname=snap.get("hostname") or "",
        taken_at=snap.get("taken_at") or "",
        internet_via=snap.get("internet_via"),
        errors=list(snap.get("errors") or []),
        snapshot=snap,
    )

    adapters = {a["id"]: a for a in snap.get("adapters") or [] if a.get("id")}
    for a in adapters.values():
        kind = classify(a, platform)
        node = Node(
            id=a["id"],
            kind=kind,
            label=a.get("name") or a["id"],
            status=_status(a.get("status")),
            connectivity=_connectivity(a.get("connectivity")),
            hidden=default_hidden(kind, a),
            subtitle=_subtitle(a),
            props=a,
        )
        topo.add_node(node)

    any_internet = any(n.connectivity == Connectivity.INTERNET for n in topo.nodes.values())
    topo.add_node(Node(
        id=INTERNET_ID,
        kind=NodeKind.INTERNET,
        label=tr("İnternet"),
        status=Status.UP if any_internet else Status.DISCONNECTED,
        connectivity=Connectivity.INTERNET if any_internet else Connectivity.NONE,
        subtitle=tr("Bağlı") if any_internet else tr("Erişim yok"),
    ))

    _add_uplinks(topo, snap)
    _add_vpn_tunnels(topo)
    _add_sharing(topo, snap)
    _add_vm_nat(topo)
    _add_bridges(topo)
    _add_vswitches(topo, snap)
    _add_badges(topo, snap)
    _promote_connected_hidden(topo)
    return topo


# --------------------------------------------------------------------------- yardimcilar

def _status(value) -> Status:
    try:
        return Status(value)
    except ValueError:
        return Status.UNKNOWN


def _connectivity(value) -> Connectivity:
    try:
        return Connectivity(value)
    except ValueError:
        return Connectivity.UNKNOWN


def _subtitle(a: dict) -> str:
    v4 = [x for x in a.get("ipv4") or [] if x.get("address")]
    if v4:
        return ", ".join(f"{x['address']}/{x.get('prefix', '?')}" for x in v4[:2])
    return ""


def _ipv4_networks(a: dict) -> list[ipaddress.IPv4Network]:
    nets = []
    for x in a.get("ipv4") or []:
        try:
            nets.append(ipaddress.ip_interface(f"{x['address']}/{x.get('prefix', 32)}").network)
        except (KeyError, ValueError):
            continue
    return nets


def _has_manual_ipv4(a: dict) -> bool:
    return any(x.get("origin") == "manual" for x in a.get("ipv4") or [])


def _is_up(node: Node) -> bool:
    return node.status == Status.UP


# --------------------------------------------------------------------------- iliskiler

def _add_uplinks(topo: Topology, snap: dict) -> None:
    """S4: varsayilan rotalar -> ag gecidi dugumleri; etkin yol vurgusu."""
    macs = snap.get("gateway_macs") or {}
    routes = [r for r in snap.get("default_routes") or [] if r.get("adapter") in topo.nodes]
    full_tunnel = _full_tunnel_adapters(routes)

    for r in routes:
        if r.get("family", 4) != 4 or r.get("dest") not in ("0.0.0.0/0", "0.0.0.0/1"):
            continue
        adapter = topo.nodes[r["adapter"]]
        active = adapter.id == topo.internet_via
        metric = r.get("effective_metric", r.get("metric"))
        metric_label = tr("metrik {metric}").format(metric=metric) if metric is not None else ""
        hop = r.get("next_hop") or ""
        if hop in ("", "0.0.0.0"):
            # Baglanti uzerinde (on-link) varsayilan rota: PPP / tam tunel VPN.
            topo.add_edge(Edge(INTERNET_ID, adapter.id, EdgeKind.INTERNET, metric_label, active,
                               [tr("{dest} rotası ağ geçidi olmadan bu arayüzde").format(dest=r.get("dest"))]))
            continue
        gw_id = f"gw:{hop}@{adapter.id}"
        if gw_id not in topo.nodes:
            reach = adapter.connectivity
            topo.add_node(Node(
                id=gw_id,
                kind=NodeKind.GATEWAY,
                label=hop,
                status=Status.UP if _is_up(adapter) else Status.DISCONNECTED,
                connectivity=reach,
                subtitle=macs.get(hop, ""),
                props={"ip": hop, "mac": macs.get(hop), "adapter": adapter.id},
            ))
            reaches_internet = reach == Connectivity.INTERNET or adapter.id == topo.internet_via \
                or adapter.id in full_tunnel
            topo.add_edge(Edge(
                INTERNET_ID, gw_id, EdgeKind.INTERNET,
                "" if reaches_internet else tr("internet yok"),
                active,
                [tr("Bağlantı profili: {value}").format(value=reach.value)],
                dim=not reaches_internet,
            ))
        topo.add_edge(Edge(gw_id, adapter.id, EdgeKind.UPLINK, metric_label, active,
                           [tr("Varsayılan rota {dest}, ağ geçidi {hop}, rota metriği {route}, toplam {total}")
                            .format(dest=r.get("dest"), hop=hop, route=r.get("metric"), total=metric)]))


def _full_tunnel_adapters(routes: list[dict]) -> set[str]:
    """VPN'in 0.0.0.0/1 + 128.0.0.0/1 ciftiyle varsayilan rotayi ele gecirmesi."""
    by_adapter: dict[str, set[str]] = {}
    for r in routes:
        by_adapter.setdefault(r["adapter"], set()).add(r.get("dest"))
    return {a for a, d in by_adapter.items() if {"0.0.0.0/1", "128.0.0.0/1"} <= d}


def _uplink_carrier(topo: Topology) -> Node | None:
    """VPN olmayan, internete cikan bagdastirici (tunel/NAT'in tasiyicisi)."""
    via = topo.nodes.get(topo.internet_via or "")
    if via is not None and via.kind != NodeKind.VPN:
        return via
    candidates = [
        n for n in topo.nodes.values()
        if n.is_adapter and _is_up(n) and n.kind in (NodeKind.ETHERNET, NodeKind.WIFI, NodeKind.CELLULAR)
        and n.connectivity == Connectivity.INTERNET
    ]
    return candidates[0] if candidates else None


def _add_vpn_tunnels(topo: Topology) -> None:
    """S7: calisan VPN bagdastiricisi -> tasiyici fiziksel bagdastirici (sezgisel)."""
    carrier = _uplink_carrier(topo)
    if carrier is None:
        return
    for n in list(topo.nodes.values()):
        if n.kind == NodeKind.VPN and _is_up(n):
            topo.add_edge(Edge(carrier.id, n.id, EdgeKind.TUNNEL, tr("tünel"),
                               topo.internet_via == n.id,
                               [tr("VPN trafiği internete çıkan {name} üzerinden taşınır "
                                   "(sezgisel: VPN sunucusuna giden rota sorgulanmadı)").format(name=carrier.label)]))


def _add_sharing(topo: Topology, snap: dict) -> None:
    """S1/S2: ICS (public -> private) ve Mobil Hotspot."""
    sharing = snap.get("sharing") or {}
    scope = sharing.get("scope") or "192.168.137.1"
    publics = [n for n in topo.nodes.values() if n.props.get("sharing") == "public"]
    privates = [n for n in topo.nodes.values() if n.props.get("sharing") == "private"]
    if privates and not publics and topo.platform == "linux":
        # NetworkManager "shared" yontemi: cikis isletim sisteminin varsayilan rotasidir.
        carrier = _uplink_carrier(topo)
        publics = [carrier] if carrier else []
    for pub in publics:
        for priv in privates:
            if priv.kind == NodeKind.HOTSPOT:
                topo.add_edge(Edge(pub.id, priv.id, EdgeKind.HOTSPOT, tr("Mobil Hotspot"),
                                   pub.id == topo.internet_via,
                                   [tr("Wi-Fi Direct sanal bağdaştırıcısı paylaşımın hedef tarafı")]))
            else:
                topo.add_edge(Edge(pub.id, priv.id, EdgeKind.ICS, f"ICS · {scope}/24",
                                   pub.id == topo.internet_via,
                                   [f"{pub.label}: SharingConnectionType=public",
                                    f"{priv.label}: SharingConnectionType=private",
                                    tr("Paylaşım kapsamı (ScopeAddress): {scope}").format(scope=scope)]))


def _add_vm_nat(topo: Topology) -> None:
    """S6: host cikisi -> sanal makine NAT agi (VMware NAT Service / WinNAT / libvirt)."""
    carrier = _uplink_carrier(topo)
    if carrier is None:
        return
    for n in topo.nodes.values():
        if n.kind != NodeKind.VM_NAT or n.status != Status.UP:
            continue
        desc = (n.props.get("description") or "").lower()
        if "vmware" in desc:
            label, why = "VMware NAT", tr("VMnet8: NAT'ı VMware NAT Service yapar")
        elif n.label.startswith("virbr"):
            label, why = "libvirt NAT", tr("virbr*: libvirt NAT ağı")
        else:
            label, why = "WinNAT", tr("Hyper-V Default Switch / WSL: HNS NAT'ı")
        topo.add_edge(Edge(carrier.id, n.id, EdgeKind.NAT, label, False, [why]))


def _add_bridges(topo: Topology) -> None:
    """S3: kopru uyeleri -> kopru bagdastiricisi."""
    bridges = [n for n in topo.nodes.values() if n.kind == NodeKind.BRIDGE]
    for n in topo.nodes.values():
        p = n.props
        if not n.is_adapter or n.kind == NodeKind.BRIDGE:
            continue
        master = p.get("bridge_master")
        target = topo.nodes.get(master) if master else None
        if target is None and p.get("bridge_member") and len(bridges) == 1:
            target = bridges[0]    # Windows'ta tek kopru olabilir
        if target is not None:
            topo.add_edge(Edge(n.id, target.id, EdgeKind.BRIDGE, tr("köprü"), False,
                               [tr("ms_bridge bağlaması etkin") if p.get("bridge_member")
                                else f"master = {master}"]))


def _add_vswitches(topo: Topology, snap: dict) -> None:
    """Hyper-V dis anahtar: fiziksel NIC (uplink) -> vEthernet (<anahtar adi>)."""
    for sw in snap.get("vm_switches") or []:
        if (sw.get("type") or "").lower() != "external" or not sw.get("uplink"):
            continue
        phys = next((n for n in topo.nodes.values()
                     if n.props.get("description") == sw["uplink"]), None)
        veth = next((n for n in topo.nodes.values()
                     if n.kind == NodeKind.VETHERNET and sw.get("name", "") in n.label), None)
        if phys and veth:
            topo.add_edge(Edge(phys.id, veth.id, EdgeKind.VSWITCH, f"vSwitch · {sw['name']}",
                               False, [f"Get-VMSwitch: {sw['name']} (External)"]))


def _promote_connected_hidden(topo: Topology) -> None:
    """Gizli ama bir iliskiye katilan dugum (ör. calisan hotspot) gorunur olur."""
    for e in topo.edges:
        for nid in (e.src, e.dst):
            node = topo.nodes.get(nid)
            if node and node.hidden and node.kind not in (NodeKind.SYSTEM, NodeKind.LOOPBACK):
                node.hidden = False


# --------------------------------------------------------------------------- sorun rozetleri

def _add_badges(topo: Topology, snap: dict) -> None:
    """S11: diyagram uzerindeki uyari rozetleri."""
    adapters = [n for n in topo.nodes.values()
                if n.is_adapter and n.kind not in (NodeKind.SYSTEM, NodeKind.LOOPBACK)]
    gw_adapters = {r.get("adapter") for r in snap.get("default_routes") or []}

    for n in adapters:
        p = n.props
        v4 = p.get("ipv4") or []
        if _is_up(n) and any(x.get("origin") == "link_local" or
                             str(x.get("address", "")).startswith("169.254.") for x in v4):
            if p.get("dhcp4"):
                n.badges.append(Badge("apipa", Severity.ERROR,
                                      tr("DHCP sunucusundan adres alınamadı (169.254.x.x APIPA).")))
            else:
                n.badges.append(Badge("apipa", Severity.WARNING,
                                      tr("Yalnızca otomatik özel adres (APIPA) var.")))
        if n.status == Status.DISCONNECTED and _has_manual_ipv4(p):
            ips = ", ".join(x["address"] for x in v4 if x.get("origin") == "manual")
            n.badges.append(Badge("static_no_link", Severity.INFO,
                                  tr("Bağlantı yok; statik IP tanımlı ({ips}).").format(ips=ips)))
        if _is_up(n) and n.id in gw_adapters and n.connectivity in (Connectivity.LOCAL, Connectivity.NONE) \
                and n.kind != NodeKind.VPN:
            n.badges.append(Badge("no_internet", Severity.WARNING,
                                  tr("Ağ geçidi var ama internet erişimi doğrulanamadı (NCSI).")))

    # Ayni alt ag iki calisan bagdastiricida: rota belirsizligi.
    seen: dict[ipaddress.IPv4Network, Node] = {}
    for n in adapters:
        if not _is_up(n):
            continue
        for net in _ipv4_networks(n.props):
            if net.prefixlen >= 32 or net.is_link_local:
                continue
            other = seen.get(net)
            if other is not None and other.id != n.id:
                msg = tr("{net} alt ağı hem {a} hem {b} üzerinde.").format(net=net, a=other.label, b=n.label)
                for target in (n, other):
                    target.badges.append(Badge("duplicate_subnet", Severity.WARNING, msg))
            seen.setdefault(net, n)

    # Ayni IP iki bagdastiricida.
    owners: dict[str, list[Node]] = {}
    for n in adapters:
        for x in n.props.get("ipv4") or []:
            if x.get("address"):
                owners.setdefault(x["address"], []).append(n)
    for ip, nodes in owners.items():
        if len({n.id for n in nodes}) > 1:
            for n in nodes:
                n.badges.append(Badge("ip_conflict", Severity.ERROR,
                                      tr("{ip} adresi birden fazla bağdaştırıcıda tanımlı.").format(ip=ip)))

    sharing = snap.get("sharing") or {}
    shared = [n for n in adapters if n.props.get("sharing")]
    if shared and sharing.get("service") not in (None, "running"):
        for n in shared:
            n.badges.append(Badge("ics_service_stopped", Severity.ERROR,
                                  tr("İnternet paylaşımı açık ama paylaşım hizmeti çalışmıyor.")))

    defaults = [r for r in snap.get("default_routes") or []
                if r.get("family", 4) == 4 and r.get("dest") == "0.0.0.0/0"]
    if len({r.get("adapter") for r in defaults}) > 1:
        via = topo.nodes.get(topo.internet_via or "")
        topo.host_badges.append(Badge(
            "multiple_default_routes", Severity.INFO,
            tr("{count} varsayılan rota var; trafik {name} üzerinden çıkıyor.").format(
                count=len(defaults), name=via.label if via else tr("en düşük metrikli arayüz"))))
