"""Bagdastirici turu siniflandirmasi.

Karar yerellestirilmis ada ("Yerel Ag Baglantisi* 6") gore VERILMEZ; surucu
aciklamasi, medya turu, NetworkManager turu ve cekirdek baglanti turu
(`hints`) kullanilir (ai_rules/30).
"""

from __future__ import annotations

import re

from .model import NodeKind, Status

_VPN_RE = re.compile(
    r"vpn|tap-windows|wintun|wireguard|openvpn|fortinet|radmin|zerotier|tailscale|"
    r"anyconnect|pangp|sonicwall|nordlynx|hamachi|juniper|checkpoint|globalprotect",
    re.I,
)
_SYSTEM_RE = re.compile(
    r"wan miniport|kernel debug|teredo|6to4|ip-https|isatap|pseudo-interface|"
    r"microsoft kernel|network monitor",
    re.I,
)


def classify(adapter: dict, platform: str) -> NodeKind:
    if platform == "linux":
        return _classify_linux(adapter)
    return _classify_windows(adapter)


def _classify_windows(a: dict) -> NodeKind:
    desc = a.get("description") or ""
    name = a.get("name") or ""
    hints = a.get("hints") or {}
    media = f"{hints.get('media_type', '')} {hints.get('physical_media_type', '')}"
    text = f"{desc} {name}"

    if "wi-fi direct" in desc.lower():
        return NodeKind.HOTSPOT
    if _SYSTEM_RE.search(text):
        return NodeKind.SYSTEM
    if "loopback" in text.lower():
        return NodeKind.LOOPBACK
    if re.search(r"vmware virtual ethernet adapter for vmnet8\b", desc, re.I):
        return NodeKind.VM_NAT
    if re.search(r"vmware virtual ethernet|virtualbox host-only", desc, re.I):
        return NodeKind.VM_HOST_ONLY
    if re.search(r"hyper-v virtual ethernet", desc, re.I):
        # Default Switch ve WSL, HNS'in NAT'ladigi ic anahtarlardir.
        if re.search(r"default switch|\bwsl\b", name, re.I):
            return NodeKind.VM_NAT
        return NodeKind.VETHERNET
    if re.search(r"mac bridge miniport|network bridge", desc, re.I):
        return NodeKind.BRIDGE
    if _VPN_RE.search(desc):
        return NodeKind.VPN
    if "bluetooth" in text.lower():
        return NodeKind.BLUETOOTH
    if re.search(r"802\.11|wireless lan|wi-?fi|wlan", f"{media} {desc}", re.I):
        return NodeKind.WIFI
    # Kelime siniri sart: "Realtek" icinde "lte" geciyor (bir kez ETH'yi hucresel yapti).
    if re.search(r"wireless wan|mobile broadband|\bwwan\b|cellular|\blte\b", f"{media} {desc}", re.I):
        return NodeKind.CELLULAR
    if "802.3" in media or re.search(r"ethernet|\bgbe\b|\bnic\b", desc, re.I):
        return NodeKind.ETHERNET
    return NodeKind.UNKNOWN


def _classify_linux(a: dict) -> NodeKind:
    name = a.get("name") or ""
    hints = a.get("hints") or {}
    nm = (hints.get("nm_type") or "").lower()
    kind = (hints.get("link_kind") or "").lower()
    link_type = (hints.get("link_type") or "").lower()

    if name == "lo" or nm == "loopback" or link_type == "loopback":
        return NodeKind.LOOPBACK
    if nm == "wifi-p2p":
        return NodeKind.HOTSPOT
    if nm in ("wifi", "802-11-wireless"):
        return NodeKind.WIFI
    if nm in ("bt", "bluetooth"):
        return NodeKind.BLUETOOTH
    if nm in ("gsm", "cdma", "modem"):
        return NodeKind.CELLULAR
    if nm in ("vpn", "wireguard", "tun") or kind in ("wireguard", "tun") \
            or re.match(r"(tun|tap|wg|tailscale|zt)\w*", name):
        return NodeKind.VPN
    if name.startswith("virbr"):
        return NodeKind.VM_NAT          # libvirt NAT agi
    if name.startswith("vmnet") or name.startswith("vboxnet"):
        return NodeKind.VM_HOST_ONLY
    if kind == "veth":
        return NodeKind.CONTAINER
    if nm == "bridge" or kind == "bridge":
        return NodeKind.BRIDGE
    if nm == "ethernet" or link_type == "ether":
        return NodeKind.ETHERNET
    return NodeKind.UNKNOWN


def default_hidden(kind: NodeKind, adapter: dict) -> bool:
    """Varsayilan filtrede gizlenecek mi (kullanici 'Gizlileri goster' ile acar)."""
    status = adapter.get("status")
    if kind in (NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.CONTAINER):
        return True
    if status == Status.NOT_PRESENT.value:
        return True
    if kind == NodeKind.HOTSPOT:
        return status != Status.UP.value
    return bool(adapter.get("hidden"))
