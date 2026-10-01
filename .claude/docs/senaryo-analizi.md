# Ağ İlişki Senaryoları — Analiz

Tarih: 2026-09-30. Amaç: diyagramın hangi ilişkileri **tespit edip çizmesi**,
hangilerini **kullanıcının yol çizerek kurabilmesi** gerektiğini belirlemek.

Her senaryo için: ne olur, nasıl tespit edilir, diyagramda nasıl görünür,
diyagramdan nasıl kurulur, tuzaklar.

Bu makinenin salt okunur anlık görüntüsü: `.claude/logs/2026-09-30-host-snapshot.md`.

---

## S1 — İnternet paylaşımı (ICS): Wi-Fi → Ethernet

**Ne olur:** Windows, *public* bağdaştırıcıdaki (Wi-Fi) interneti *private*
bağdaştırıcıya (ETH) NAT + DHCP (+ DNS proxy) ile paylaştırır. ETH'ye bağlı
cihaz 192.168.137.x adresi alır.

**Tespit:** `HNetCfg.HNetShare` COM → her bağlantı için
`SharingEnabled` ve `SharingConnectionType` (0 = public, 1 = private).
Yönetici gerekmez (ölçüldü). Destek: `SharedAccess` hizmeti çalışıyor mu,
private bağdaştırıcının IP'si 192.168.137.1 mi.

**Diyagram:** Wi-Fi → ETH turuncu kesikli ok, etiket **"ICS"**. ETH'nin
aşağı akışına "ICS istemcileri" düğümü (ARP/`Get-NetNeighbor` ile
192.168.137.0/24'teki komşular) eklenir.

**Diyagramdan kurma:** kullanıcı Wi-Fi'den ETH'ye yol çizer → menü
"İnternet paylaşımı (ICS)". Plan penceresi şunları gösterir:
- Mevcut ICS çifti varsa **önce kapatılır** (tek çift sınırı).
- ETH'nin mevcut IP'si (bu makinede statik 192.168.1.2) **192.168.137.1 ile
  değiştirilecek** — uyarı.
- `SharedAccess` hizmeti çalışmıyorsa başlatılır.

**Tuzaklar:** tek public/private çifti; public bağdaştırıcı değişirse (Wi-Fi
kopup Ethernet'e geçilirse) paylaşım kendiliğinden taşınmaz; bazı Win10
sürümlerinde yeniden başlatma sonrası bozulma (TODO: VM'de doğrula);
private tarafta DHCP sunucusu çalıştığından o segmentte başka DHCP varsa çakışır.

## S2 — Mobil Hotspot (Wi-Fi → Wi-Fi Direct sanal bağdaştırıcı)

**Ne olur:** Ayarlar > Mobil etkin nokta; Windows "Microsoft Wi-Fi Direct
Virtual Adapter" üzerinden erişim noktası açar, arkada ICS benzeri paylaşım yapar.

**Tespit:** WinRT `NetworkOperatorTetheringManager.TetheringOperationalState`
ve `ClientCount`; Wi-Fi Direct sanal bağdaştırıcının `Status=Up` olması.
(Bu makinede iki Wi-Fi Direct bağdaştırıcısı var, ikisi de Disconnected.)

**Diyagram:** kaynak bağdaştırıcı → "Hotspot" düğümü, istemci sayısı etiketi.

**Kurma:** hotspot düğümüne yol çizmek → aç, SSID/parola inspector'da.

## S3 — Ağ köprüsü (Network Bridge)

**Ne olur:** iki veya daha fazla bağdaştırıcı L2'de birleşir; "MAC Bridge
Miniport" sanal bağdaştırıcısı oluşur, IP artık köprüde durur.

**Tespit:** `Get-NetAdapterBinding -ComponentID ms_bridge` → `Enabled=True`
olan üyeler; `InterfaceDescription` "Microsoft Network Adapter Multiplexor" /
"MAC Bridge Miniport".

**Diyagram:** üyeler → Bridge düğümü (mor). Üyelerin IP bilgisi soluk gösterilir.

**Kurma:** iki bağdaştırıcı arasına yol → "Köprü oluştur". Win11 22H2+
(2023-09 güncellemesi) `netsh bridge create`; **Win10'da resmi yol yok** →
Win10'da menü öğesi devre dışı + gerekçe tooltip'i.

**Tuzak:** Wi-Fi köprüye alınınca birçok AP'de çalışmaz (MAC değiştirme);
plan uyarır. ICS ile köprü aynı anda kullanılamaz.

## S4 — Birden çok varsayılan rota / hangi bağdaştırıcı internete çıkıyor

**Ne olur:** Wi-Fi + Ethernet + VPN aynı anda bağlıyken trafik en düşük
toplam metrikli rotadan gider.

**Tespit:** `Get-NetRoute -DestinationPrefix 0.0.0.0/0` +
`Get-NetIPInterface` → etkin metrik = `RouteMetric + InterfaceMetric`.
Bu makinede: Wi-Fi (0 + 35 = **35**) ve Radmin VPN (9256 + 1 = 9257) →
internet **Wi-Fi'den** çıkıyor. `Get-NetConnectionProfile.IPv4Connectivity`
= Internet ile çapraz doğrulanır.

**Diyagram:** etkin yol yeşil vurgulu; diğer varsayılan rotalar gri, etiket
"metrik 9257 (yedek)".

**Kurma:** bağdaştırıcıları "öncelik" listesinde sürükleyerek sıralamak →
`InterfaceMetric` değişiklikleri kuyruğa girer. (NetSetMan ve Windows'un
gizli "Gelişmiş ayarlar > bağlantı sırası" eksikliğini giderir.)

## S5 — Statik IP / DHCP / APIPA

**Tespit:** `Get-NetIPInterface.Dhcp`, `Get-NetIPAddress.PrefixOrigin`
(Dhcp / Manual / WellKnown). 169.254.x.x + WellKnown = **APIPA** → DHCP
alınamadı (kırmızı/sarı uyarı).

**Kurma:** inspector'da DHCP/Statik anahtarı, IP/maske/ağ geçidi/DNS alanları;
"profil" olarak kaydedilip başka zaman tek tıkla uygulanabilir (NetSetMan
profilleri gibi).

**Tuzak:** DHCP'ye dönüşte eski statik ağ geçidi rotası silinmezse kalır;
iki bağdaştırıcıya aynı alt ağ verilirse rota belirsizleşir → çakışma uyarısı.

## S6 — Sanal makine ağları

| Tür | Tespit | Diyagram |
|---|---|---|
| VMware VMnet8 (NAT) | `InterfaceDescription` "VMware Virtual Ethernet Adapter for VMnet8"; NAT'ı **VMware NAT Service** yapar | Host'un etkin uplink'i → VMnet8, etiket "VMware NAT" |
| VMware VMnet1 (host-only) | "…for VMnet1" | Yalnızca host ↔ VM, internet yok |
| VirtualBox host-only | "VirtualBox Host-Only Ethernet Adapter" | Host-only |
| Hyper-V dış anahtar | `Get-VMSwitch -SwitchType External` + fiziksel NIC'te `vms_pp` bağlaması | Fiziksel NIC → vSwitch → vEthernet |
| Hyper-V Default Switch / iç + WinNAT | `Get-NetNat` (yoksa hata — bu makinede "Provider load failure") | vEthernet, etiket "WinNAT" |
| WSL2 | vEthernet (WSL) | Default Switch gibi |

Bu makinede: VMnet1, VMnet8, VirtualBox host-only **Up**; Hyper-V/WinNAT yok.

## S7 — VPN / tünel

**Tespit:** `Get-VpnConnection` (Windows yerleşik VPN'leri), sürücü açıklaması
(Fortinet, Radmin, TAP-Windows, Wintun/WireGuard, OpenVPN Data Channel Offload).
Tünelin **hangi fiziksel bağdaştırıcı üzerinden** gittiği: VPN sunucusunun IP'sine
giden rota (`Find-NetRoute -RemoteIPAddress <sunucu>`).

**Diyagram:** VPN düğümü → taşıyan fiziksel bağdaştırıcıya noktalı kenar.
VPN varsayılan rotayı ele geçiriyorsa (full tunnel) etkin yol VPN'den gösterilir;
split tunnel ise yalnız ilgili alt ağlar.

Bu makinede: Radmin VPN Up (26.0.0.0/8, NoTraffic), Fortinet SSL VPN Not Present.

## S8 — Devre dışı / takılı değil / sürücü yok

`Status`: Up, Disconnected (kablo yok), Disabled, Not Present (cihaz yok).
Diyagramda gri; "Not Present" varsayılan filtrede gizli.

## S9 — IP yönlendirme (Windows'un router gibi davranması)

**Tespit:** `Get-NetIPInterface.Forwarding` (bu makinede tümü kapalı).
**Kurma:** iki bağdaştırıcı arasına "Yönlendir (NAT'sız)" ilişkisi →
her iki arayüzde `Forwarding Enabled`. Karşı tarafta statik rota gerektiği
uyarılır. ICS'ten farkı: NAT ve DHCP yok.

## S10 — NIC takımı / VLAN

`Get-NetLbfoTeam` (Windows Server; Win10/11 istemcide LBFO yok — Intel ANS
gibi sürücü araçları kullanılır), VLAN için `Get-NetAdapterAdvancedProperty`
`VlanID`. Öncelik düşük (v2).

## S11 — Sorun tespiti (diyagram üzerinde uyarı rozetleri)

- IP çakışması / aynı alt ağ iki bağdaştırıcıda
- APIPA (DHCP yok)
- Ağ geçidi var ama NCSI "LocalNetwork" (internet yok)
- DNS yanıt vermiyor (`Resolve-DnsName` zaman aşımı)
- ICS açık ama `SharedAccess` hizmeti durmuş
- Kablo bağlı değil ama statik IP tanımlı (bu makinede ETH: 192.168.1.2, Disconnected)

---

## Sonuç: öncelik sırası

| Öncelik | Senaryolar |
|---|---|
| MVP (salt okunur diyagram) | S4, S5, S6, S7, S8, S1 tespiti, S11 temel rozetler |
| v1 (yapılandırma) | S5 düzenleme + profiller, S4 metrik sıralama, **S1 ICS kurma/kaldırma**, etkin/devre dışı, DNS, MTU, bağlamalar |
| v2 | S2 hotspot, S3 köprü, S9 yönlendirme, S10, Hyper-V anahtarı yönetimi |
