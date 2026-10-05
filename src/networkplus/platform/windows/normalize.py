"""snapshot.ps1 ham ciktisi -> normalize snapshot (.claude/specs/snapshot-schema.md).

Saf fonksiyon: isletim sistemine dokunmaz, fixture JSON ile test edilir.
"""

from __future__ import annotations

_STATUS = {
    "up": "up",
    "disconnected": "disconnected",
    "disabled": "disabled",
    "not present": "not_present",
}
_CONNECTIVITY = {
    "internet": "internet",
    "localnetwork": "local",
    "subnet": "local",
    "notraffic": "none",
    "disconnected": "none",
}
_ORIGIN = {"dhcp": "dhcp", "manual": "manual", "wellknown": "link_local"}


def _list(value) -> list:
    """PS 5.1 tek elemanli sonucu dizi yerine nesne yazabilir."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize(raw: dict) -> dict:
    adapters_raw = _list(raw.get("adapters"))
    guid_of = {a.get("index"): a.get("guid") for a in adapters_raw}

    ipif: dict[tuple[int, str], dict] = {}
    for x in _list(raw.get("ip_interfaces")):
        ipif[(x.get("index"), x.get("family"))] = x

    addrs: dict[int, list[dict]] = {}
    for x in _list(raw.get("ip_addresses")):
        addrs.setdefault(x.get("index"), []).append(x)

    dns: dict[tuple[int, int], list[str]] = {}
    for x in _list(raw.get("dns")):
        dns[(x.get("index"), x.get("family"))] = [s for s in _list(x.get("servers")) if s]

    profiles = {p.get("index"): p for p in _list(raw.get("profiles"))}
    # Wi-Fi: GUID ile (netsh anahtarlari dile bagli; ad eslemesi yalniz eski goruntuler icin).
    wlan_by_guid = {str(w.get("guid")).lower(): w for w in _list(raw.get("wlan")) if w.get("guid")}
    wlan_by_name = {w.get("name"): w for w in _list(raw.get("wlan")) if w.get("name")}
    ics = {str(c.get("guid") or "").lower(): c for c in _list(raw.get("ics"))}
    ics_by_name = {c.get("name"): c for c in _list(raw.get("ics"))}

    dns_static = {str(d.get("guid") or "").lower(): (d.get("name_server") or "").strip()
                  for d in _list(raw.get("dns_static"))}

    bindings: dict[str, dict[str, bool]] = {}
    for b in _list(raw.get("bindings")):
        bindings.setdefault(b.get("name"), {})[b.get("component")] = bool(b.get("enabled"))

    advanced: dict[str, list[dict]] = {}
    for x in _list(raw.get("advanced")):
        advanced.setdefault(x.get("name"), []).append(_advanced_property(x))

    adapters = []
    for a in adapters_raw:
        idx = a.get("index")
        v4if = ipif.get((idx, "IPv4"), {})
        prof = profiles.get(idx)
        conn = "unknown"
        if prof:
            conn = _CONNECTIVITY.get(str(prof.get("ipv4", "")).lower(), "unknown")
        elif (a.get("status") or "").lower() != "up":
            conn = "none"

        def ips(family: str) -> list[dict]:
            out = []
            for x in addrs.get(idx, []):
                if x.get("family") != family:
                    continue
                out.append({
                    "address": x.get("address"),
                    "prefix": x.get("prefix"),
                    "origin": _ORIGIN.get(str(x.get("origin", "")).lower(), "other"),
                    "state": x.get("state"),
                })
            return out

        share = ics.get(str(a.get("guid") or "").lower()) or ics_by_name.get(a.get("name"))
        sharing = None
        if share and share.get("enabled"):
            sharing = "public" if share.get("type") == 0 else "private"

        binds = bindings.get(a.get("name"), {})
        w = wlan_by_guid.get(str(a.get("guid") or "").lower()) or wlan_by_name.get(a.get("name"))
        adapters.append({
            "id": a.get("guid") or f"if{idx}",
            "index": idx,
            "name": a.get("name"),
            "description": a.get("description"),
            "mac": a.get("mac") or None,
            "status": _STATUS.get(str(a.get("status", "")).lower(), "unknown"),
            "speed_bps": a.get("speed") or 0,
            "virtual": bool(a.get("virtual")),
            "hidden": bool(a.get("hidden")),
            "hardware": bool(a.get("hardware")),
            "hints": {
                "media_type": a.get("media_type"),
                "physical_media_type": a.get("physical_media_type"),
                "component_id": a.get("component_id"),
                "driver": a.get("driver"),
                "admin_status": a.get("admin_status"),
            },
            "ipv4": ips("IPv4"),
            "ipv6": ips("IPv6"),
            "dhcp4": (str(v4if.get("dhcp")).lower() == "enabled") if v4if else None,
            "dns4": dns.get((idx, 2), []),
            "dns6": dns.get((idx, 23), []),
            # None = bilinmiyor (eski snapshot); True = elle girilmis DNS.
            "dns4_manual": (bool(dns_static[str(a.get("guid") or "").lower()])
                            if str(a.get("guid") or "").lower() in dns_static else None),
            "metric4": v4if.get("metric"),
            "auto_metric4": (str(v4if.get("auto_metric")).lower() == "enabled") if v4if else None,
            "mtu": v4if.get("mtu"),
            "forwarding4": (str(v4if.get("forwarding")).lower() == "enabled") if v4if else None,
            "connectivity": conn,
            "network_name": prof.get("name") if prof else None,
            "network_category": prof.get("category") if prof else None,
            "wifi": ({"ssid": w.get("ssid"), "bssid": w.get("bssid"), "signal": w.get("signal")}
                     if w and w.get("ssid") else None),
            "sharing": sharing,
            "bridge_member": bool(binds.get("ms_bridge")),
            "bridge_master": None,
            "bindings": binds,
            "advanced": sorted(advanced.get(a.get("name"), []), key=lambda x: str(x["display"]).casefold()),
        })

    default_routes = []
    for r in _list(raw.get("routes")):
        idx = r.get("index")
        if idx not in guid_of:
            continue
        family = 6 if ":" in str(r.get("dest")) else 4
        ifm = ipif.get((idx, "IPv6" if family == 6 else "IPv4"), {}).get("metric")
        metric = r.get("metric")
        default_routes.append({
            "adapter": guid_of[idx],
            "family": family,
            "dest": r.get("dest"),
            "next_hop": r.get("next_hop"),
            "metric": metric,
            "effective_metric": (metric + ifm) if (metric is not None and ifm is not None) else metric,
        })
    default_routes.sort(key=lambda r: (r["family"], r["effective_metric"] if r["effective_metric"] is not None else 1 << 30))

    via = None
    ir = _list(raw.get("internet_route"))
    if ir and ir[0].get("index") in guid_of:
        via = guid_of[ir[0]["index"]]

    services = {s.get("name"): s for s in _list(raw.get("services"))}
    shared_access = services.get("SharedAccess")
    scope = None
    for s in _list(raw.get("ics_scope")):
        scope = s.get("scope_address") or scope

    return {
        "format": "normalized",
        "schema": 1,
        "platform": "windows",
        "hostname": raw.get("hostname"),
        "taken_at": raw.get("taken_at"),
        "os": raw.get("os"),
        "is_admin": bool(raw.get("is_admin")),
        "adapters": adapters,
        "default_routes": default_routes,
        "internet_via": via,
        "gateway_macs": {n.get("ip"): n.get("mac") for n in _list(raw.get("neighbors")) if n.get("ip")},
        "sharing": {
            "service": str(shared_access.get("status")).lower() if shared_access else None,
            "service_start": shared_access.get("start") if shared_access else None,
            "scope": scope,
        },
        "vm_switches": _list(raw.get("vm_switches")),
        "nat": _list(raw.get("nat")),
        "vpn_profiles": _list(raw.get("vpn")),
        "errors": _list(raw.get("errors")),
        "timings_ms": raw.get("timings_ms") or {},
    }


def _advanced_property(x: dict) -> dict:
    """Surucu gelismis ozelligi (Get-NetAdapterAdvancedProperty). Ad/deger surucu dilinde."""
    def num(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    lo, hi, step = num(x.get("min")), num(x.get("max")), num(x.get("step"))
    return {
        "keyword": x.get("keyword"),
        "display": x.get("display"),
        "value": x.get("value") or "",
        "registry": [str(r) for r in _list(x.get("registry")) if r is not None],
        "options": [str(o) for o in _list(x.get("options")) if o is not None],
        "default": x.get("default"),
        "range": {"min": lo, "max": hi, "step": step} if lo is not None and hi is not None else None,
    }
