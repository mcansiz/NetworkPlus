# Normalize Anlık Görüntü Şeması (schema 1)

Her platform toplayıcısı ham veriyi toplar (`collect_raw`), saf bir
`normalize(raw)` fonksiyonu bu şemaya çevirir. `core/` yalnız bu şemayı görür.
Her alan **eksik olabilir**; tüketici varsayılan değer kullanır.

```jsonc
{
  "format": "normalized", "schema": 1,
  "platform": "windows" | "linux",
  "hostname": "…", "taken_at": "ISO-8601", "os": "10.0.19045.0", "is_admin": false,
  "adapters": [{
    "id": "{GUID}" | "eth0",          // kalıcı kimlik (Windows: InterfaceGuid, Linux: ifname)
    "index": 18, "name": "Wi-Fi", "description": "Intel(R) Wi-Fi 6 AX201",
    "mac": "F0-77-…", "status": "up|disconnected|disabled|not_present|unknown",
    "speed_bps": 721000000, "virtual": false, "hidden": false, "hardware": true,
    "hints": {"media_type": "Native 802.11", "physical_media_type": "…",
              "component_id": "…", "nm_type": "wifi", "link_kind": "bridge"},
    "ipv4": [{"address": "10.20.30.57", "prefix": 24, "origin": "dhcp|manual|link_local|other"}],
    "ipv6": [ … ],
    "dhcp4": true, "dns4": ["10.20.30.100"], "dns6": [],
    "metric4": 35, "auto_metric4": true, "mtu": 1500, "forwarding4": false,
    "connectivity": "internet|local|none|unknown",
    "network_name": "barko.local", "network_category": "DomainAuthenticated",
    "wifi": {"ssid": "…", "bssid": "…", "signal": 65} | null,
    "sharing": "public" | "private" | null,      // ICS / NM shared
    "bridge_member": false, "bridge_master": null,
    "bindings": {"ms_tcpip": true, "ms_bridge": false, "vms_pp": false}
  }],
  "default_routes": [{"adapter": "{GUID}", "family": 4, "dest": "0.0.0.0/0",
                      "next_hop": "10.20.30.253", "metric": 0, "effective_metric": 35}],
  "internet_via": "{GUID}" | null,               // işletim sisteminin gerçekte seçtiği çıkış
  "gateway_macs": {"10.20.30.253": "44-12-…"},
  "sharing": {"service": "running|stopped|null", "scope": "192.168.137.1"},
  "vm_switches": [{"name", "type", "uplink"}], "nat": [ … ], "vpn_profiles": [ … ],
  "errors": [{"section": "nat", "message": "Provider load failure"}],
  "timings_ms": {"adapters": 751}
}
```

Notlar
- Windows'ta ICS alt ağı `sharing.scope`'tan okunur; **192.168.137.1 varsayılmaz**
  (geliştirme makinesinde 192.168.1.1 — ölçüldü 2026-09-30).
- `effective_metric` = route metric + interface metric (Windows). Yalnız etiket içindir;
  etkin yol `internet_via`'dan gelir.
