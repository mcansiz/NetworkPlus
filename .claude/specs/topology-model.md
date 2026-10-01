# Topoloji Veri Modeli (taslak — 2026-09-30)

`core/model.py` bu spesifikasyonu uygular. Model saf veri, Qt'den bağımsız.

## Node

| Alan | Tür | Not |
|---|---|---|
| `id` | str | Bağdaştırıcı için `InterfaceGuid`; sentetik düğümler için `internet`, `gw:<ip>`, `bridge:<guid>`, `ics-clients:<guid>` |
| `kind` | NodeKind | Internet, Gateway, Ethernet, WiFi, Bluetooth, Cellular, VmHostOnly, VmNat, HyperVSwitch, VEthernet, Vpn, Bridge, Team, Hotspot, Loopback, Clients |
| `label` | str | Görünen ad (Windows'taki ad) |
| `status` | Status | Up, Disconnected, Disabled, NotPresent, Unknown |
| `connectivity` | str | Internet / LocalNetwork / NoTraffic / None |
| `hidden` | bool | Varsayılan filtrede gizlenir mi |
| `props` | dict | Ham ayarlar: ifIndex, mac, speed, ipv4[], ipv6[], gateway[], dns[], dhcp, metric, mtu, forwarding, bindings{} |
| `badges` | list[Badge] | Sorun rozetleri (apipa, ip_conflict, no_internet, ics_service_stopped...) |

## Edge

| Alan | Tür | Not |
|---|---|---|
| `src`, `dst` | str | Node id |
| `kind` | EdgeKind | uplink, internet, ics, bridge, vswitch, nat, tunnel, hotspot, team, forward |
| `active` | bool | Etkin internet yolu üzerinde mi |
| `label` | str | "ICS", "metrik 35", "VMware NAT" |
| `evidence` | list[str] | İlişkinin hangi veriden çıkarıldığı (hata ayıklama + inspector'da "neden?") |

## Snapshot JSON (snapshot.ps1 çıktısı)

```json
{
  "schema": 1,
  "taken_at": "2026-09-30T14:00:00+03:00",
  "is_admin": false,
  "adapters": [...], "ip_interfaces": [...], "ip_addresses": [...],
  "dns": [...], "routes": [...], "profiles": [...], "neighbors": [...],
  "bindings": [...], "ics": [{"name": "...", "guid": "...", "enabled": true, "type": 0}],
  "ics_service": "Running", "vm_switches": [...], "nat": [...], "vpn": [...],
  "wlan": {...}, "hotspot": {...},
  "errors": [{"section": "nat", "message": "Provider load failure"}]
}
```

Değişmez kural: `core/discovery.py` her alanın **eksik olabileceğini** varsayar.
