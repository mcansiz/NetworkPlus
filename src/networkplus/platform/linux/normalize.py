"""Linux ham ciktisi (ip -j + nmcli -t) -> normalize snapshot. Saf fonksiyon.

DIKKAT: Mint VM uzerinde henuz dogrulanmadi (2026-09-30); testler sentetik
fixture ile yapiliyor. VM'den gercek cikti alininca fixture onunla degisir.
"""

from __future__ import annotations

_NM_STATE = {
    "connected": "up",
    "connecting": "up",
    # NM 'disconnected' = tasiyici var ama baglanti etkin degil (kullanici kesti ya da
    # profil yok): Windows'taki 'devre disi' ile ayni anlam (nmcli device disconnect).
    "disconnected": "disabled",
    "unavailable": "disconnected",   # tasiyici yok (kablo takili degil)
    "unmanaged": None,          # link bayraklarindan karar verilir
}
_NM_CONNECTIVITY = {"full": "internet", "limited": "local", "portal": "local", "none": "none"}


def split_terse(line: str) -> list[str]:
    """`nmcli -t -e yes` satirini kacisli ':' ve '\\' dikkate alarak boler."""
    parts, cur, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return parts


def _kv_blocks(text: str | None, first_key: str) -> list[dict[str, list[str]]]:
    """`nmcli -t device show` -> cihaz basina {alan: [degerler]}."""
    blocks: list[dict[str, list[str]]] = []
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.replace("\\:", ":").replace("\\\\", "\\")
        base = key.split("[", 1)[0]
        if base == first_key:
            blocks.append({})
        if blocks:
            blocks[-1].setdefault(base, []).append(value)
    return blocks


def _kv(text: str | None) -> dict[str, str]:
    out = {}
    for line in (text or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k] = v.replace("\\:", ":").replace("\\\\", "\\")
    return out


def _link_status(link: dict, nm_state: str | None) -> str:
    # "connecting (getting IP configuration)", "connected (externally)" -> ilk kelime
    mapped = _NM_STATE.get((nm_state or "").split(" ", 1)[0], None)
    if mapped:
        return mapped
    flags = link.get("flags") or []
    if "UP" not in flags:
        return "disabled"
    if "LOWER_UP" in flags or link.get("operstate") == "UP":
        return "up"
    return "disconnected"


def normalize(raw: dict) -> dict:
    links = raw.get("ip_addr") or []
    kinds = {l.get("ifname"): ((l.get("linkinfo") or {}).get("info_kind") or "") for l in links}

    nm_dev: dict[str, dict] = {}
    for line in (raw.get("nm_devices") or "").splitlines():
        p = split_terse(line)
        if len(p) >= 4:
            nm_dev[p[0]] = {"type": p[1], "state": p[2], "connection": p[3]}

    nm_uuid_by_dev: dict[str, str] = {}
    for line in (raw.get("nm_active") or "").splitlines():
        p = split_terse(line)
        if len(p) >= 4 and p[3]:
            nm_uuid_by_dev[p[3]] = p[1]
    conns = {uuid: _kv(text) for uuid, text in (raw.get("nm_conn") or {}).items()}
    # Etkin olmayan profil: connection.interface-name ile cihaza baglanir.
    bound_uuid: dict[str, str] = {}
    for uuid, c in conns.items():
        ifname = c.get("connection.interface-name")
        if ifname and ifname not in bound_uuid:
            bound_uuid[ifname] = uuid

    devshow = {}
    for b in _kv_blocks(raw.get("nm_devshow"), "GENERAL.DEVICE"):
        dev = (b.get("GENERAL.DEVICE") or [""])[0]
        devshow[dev] = b

    wifi = {}
    for line in (raw.get("nm_wifi") or "").splitlines():
        p = split_terse(line)
        if len(p) >= 5 and p[0] == "yes":
            wifi[p[4]] = {"ssid": p[1], "bssid": p[2], "signal": int(p[3]) if p[3].isdigit() else None}

    route_get = raw.get("route_get") or []
    via = route_get[0].get("dev") if route_get else None
    global_conn = _NM_CONNECTIVITY.get((raw.get("nm_connectivity") or "").strip(), "unknown")

    default_routes = []
    metric_by_dev: dict[str, int] = {}
    for r in raw.get("routes") or []:
        dst = r.get("dst")
        if dst not in ("default", "0.0.0.0/1", "128.0.0.0/1"):
            continue
        metric = r.get("metric", 0)
        if dst == "default":
            metric_by_dev.setdefault(r.get("dev"), metric)
        default_routes.append({
            "adapter": r.get("dev"),
            "family": 4,
            "dest": "0.0.0.0/0" if dst == "default" else dst,
            "next_hop": r.get("gateway") or "0.0.0.0",
            "metric": metric,
            "effective_metric": metric,
        })
    for r in raw.get("routes6") or []:
        default_routes.append({
            "adapter": r.get("dev"), "family": 6, "dest": "::/0",
            "next_hop": r.get("gateway") or "::", "metric": r.get("metric", 0),
            "effective_metric": r.get("metric", 0),
        })
    default_routes.sort(key=lambda r: (r["family"], r["effective_metric"]))

    shared_scope = None
    adapters = []
    for l in links:
        name = l.get("ifname")
        nd = nm_dev.get(name, {})
        active_uuid = nm_uuid_by_dev.get(name)
        uuid = active_uuid or bound_uuid.get(name)
        conn = conns.get(uuid or "", {})
        ds = devshow.get(name, {})
        method = conn.get("ipv4.method")

        ipv4, ipv6 = [], []
        for a in l.get("addr_info") or []:
            if a.get("family") == "inet":
                addr = a.get("local")
                origin = ("dhcp" if a.get("dynamic") else
                          "link_local" if str(addr).startswith("169.254.") else "manual")
                ipv4.append({"address": addr, "prefix": a.get("prefixlen"), "origin": origin})
            elif a.get("family") == "inet6":
                origin = "link_local" if a.get("scope") == "link" else (
                    "dhcp" if a.get("dynamic") else "manual")
                ipv6.append({"address": a.get("local"), "prefix": a.get("prefixlen"), "origin": origin})

        sharing = "private" if method == "shared" else None
        if sharing and ipv4:
            shared_scope = ipv4[0]["address"]

        dev_conn = (ds.get("GENERAL.IP4-CONNECTIVITY") or [""])[0]
        connectivity = "unknown"
        for word, mapped in _NM_CONNECTIVITY.items():
            if f"({word})" in dev_conn:
                connectivity = mapped
        if connectivity == "unknown" and name == via:
            connectivity = global_conn

        master = l.get("master")
        try:
            metric_setting = int(conn.get("ipv4.route-metric", "-1") or -1)
        except ValueError:
            metric_setting = -1
        metric = metric_setting if metric_setting >= 0 else metric_by_dev.get(name)
        dns_setting = [s.strip() for s in (conn.get("ipv4.dns") or "").split(",") if s.strip()]
        conn_type = conn.get("connection.type") or ""
        mtu_key = "802-11-wireless.mtu" if "wireless" in conn_type else "802-3-ethernet.mtu"
        mtu_setting = (conn.get(mtu_key) or "").strip()

        status = _link_status(l, nd.get("state"))
        adapters.append({
            "id": name,
            "index": l.get("ifindex"),
            "name": name,
            "description": conn.get("connection.id") or nd.get("connection") or kinds.get(name) or "",
            "mac": l.get("address"),
            "status": status,
            "speed_bps": 0,
            "virtual": bool(kinds.get(name)) or l.get("link_type") == "loopback",
            "hidden": False,
            "hardware": not kinds.get(name) and l.get("link_type") == "ether",
            "hints": {
                "nm_type": nd.get("type"),
                "nm_state": nd.get("state"),
                "link_kind": kinds.get(name),
                "link_type": l.get("link_type"),
            },
            "ipv4": ipv4,
            "ipv6": ipv6,
            "dhcp4": (method == "auto") if method else None,
            "dns4": ds.get("IP4.DNS", []),
            "dns6": ds.get("IP6.DNS", []),
            "dns4_setting": dns_setting,
            "dns4_manual": bool(dns_setting) if conn else None,
            "metric4": metric,
            "auto_metric4": (metric_setting < 0) if conn else None,
            "mtu": l.get("mtu"),
            "mtu_auto": (mtu_setting in ("", "auto", "0")) if conn else None,
            "forwarding4": None,
            "nm": {
                "uuid": uuid,
                "id": conn.get("connection.id"),
                "active": bool(active_uuid),
                "type": conn_type or None,
                "method": method,
                "master": conn.get("connection.master") or conn.get("connection.controller") or None,
            } if uuid else None,
            "connectivity": connectivity if status == "up" else "none",
            "network_name": conn.get("connection.id") or nd.get("connection") or None,
            "network_category": None,
            "wifi": wifi.get(name),
            "sharing": sharing,
            "bridge_member": bool(master) and kinds.get(master) == "bridge",
            "bridge_master": master,
            "bindings": {},
        })

    return {
        "format": "normalized",
        "schema": 1,
        "platform": "linux",
        "hostname": raw.get("hostname"),
        "taken_at": raw.get("taken_at"),
        "os": raw.get("os"),
        "is_admin": bool(raw.get("is_admin")),
        "adapters": adapters,
        "default_routes": default_routes,
        "internet_via": via,
        "gateway_macs": {n.get("dst"): n.get("lladdr") for n in raw.get("neigh") or []
                         if n.get("dst") and n.get("lladdr")},
        "sharing": {"service": None, "scope": shared_scope},
        "vm_switches": [],
        "nat": [],
        "vpn_profiles": [],
        "errors": raw.get("errors") or [],
        "timings_ms": {},
    }
