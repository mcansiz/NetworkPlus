# Geliştirme makinesi — ağ anlık görüntüsü (salt okunur)

Tarih: 2026-09-30. Win10 Pro 19045, PowerShell 5.1. Yalnızca `Get-*` ve
`HNetCfg` okuma çalıştırıldı; hiçbir ayar değiştirilmedi. MAC adresleri
yazılmadı.

## Bağdaştırıcılar (`Get-NetAdapter -IncludeHidden`)

| Ad | Açıklama | ifIndex | Durum | Virtual | Hidden |
|---|---|---|---|---|---|
| Wi-Fi | Intel Wi-Fi 6 AX201 160MHz | 18 | Up (721 Mbps) | F | F |
| ETH | Realtek PCIe GbE | 25 | Disconnected | F | F |
| Radmin VPN | Famatech Radmin VPN Ethernet Adapter | 11 | Up | T | F |
| VMware Network Adapter VMnet8 | VMware … VMnet8 | 14 | Up | T | F |
| VMware Network Adapter VMnet1 | VMware … VMnet1 | 7 | Up | T | F |
| Ethernet 3 | VirtualBox Host-Only Ethernet Adapter | 5 | Up | T | F |
| Ethernet 2 | Fortinet SSL VPN Virtual Ethernet Adapter | 13 | Not Present | T | F |
| Ethernet | Fortinet Virtual Ethernet Adapter (NDIS 6.30) | 12 | Not Present | T | F |
| Bluetooth Ağ Bağlantısı | Bluetooth Device (PAN) | 23 | Not Present | T | F |
| Yerel Ağ Bağlantısı* 6 / * 10 | Microsoft Wi-Fi Direct Virtual Adapter (#2) | 24 / 17 | Disconnected | T | T |
| Yerel Ağ Bağlantısı* 1–5, 7–9 | WAN Miniport (SSTP, PPTP, L2TP, IKEv2, PPPOE, IP, IPv6, Network Monitor) | — | karışık | T | T |
| Teredo / 6to4 / IP-HTTPS / Kernel Debug | sözde arayüzler | — | — | T | T |

## IP yapılandırması

| Arayüz | IPv4 | Ağ geçidi | DHCP | IfMetric |
|---|---|---|---|---|
| Wi-Fi | 10.20.30.57 | 10.20.30.253 | Evet | 35 (oto) |
| ETH | 192.168.1.2 (statik, kablo yok) | — | Hayır | 5 (oto) |
| Radmin VPN | 26.11.22.33 | 26.0.0.1 | Hayır | 1 (elle) |
| VMnet8 | 192.168.42.1 | — | Hayır | 35 |
| VMnet1 | 192.168.92.1 | — | Hayır | 35 |
| VirtualBox host-only | 192.168.56.1 | — | Hayır | 25 |

## Varsayılan rotalar

| Arayüz | NextHop | RouteMetric | Etkin (Route+If) |
|---|---|---|---|
| Wi-Fi | 10.20.30.253 | 0 | **35** → internet buradan |
| Radmin VPN | 26.0.0.1 | 9256 | 9257 |

## Diğer

- Bağlantı profili: Wi-Fi = DomainAuthenticated / **Internet**; Radmin VPN = Public / NoTraffic.
- ICS: `SharedAccess` hizmeti Running; hiçbir bağlantıda paylaşım açık değil.
  HNetShare okuma yönetici olmadan da çalışır.
- Köprü (`ms_bridge`): yok. Forwarding: tüm arayüzlerde kapalı.
- `Get-NetNat`: **"Provider load failure"** (WinNAT yok).
- Performans: `Get-NetAdapter -IncludeHidden | ConvertTo-Json` ≈ 610 ms.
- UTF-8 ayarlanmadan Türkçe adlar bozuluyor; `[Console]::OutputEncoding=UTF8` ile düzeliyor.
- Claude Code oturumu yönetici haklarıyla çalışıyor (`IsInRole Administrators = True`).
