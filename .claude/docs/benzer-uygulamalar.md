# Benzer Uygulamalar, Windows Adaptör İlişkileri ve Diyagram UX Araştırması

> Kaynak: araştırma alt-ajanı raporu, 2026-09-30. "(doğrulanmalı)" işaretli
> maddeler kaynakla kesinleşmedi; VM'de sınanmadan kural yapılmaz.
> Bu makinede ölçülen durum: `.claude/logs/2026-09-30-host-snapshot.md`.
> Senaryo bazlı analiz: `senaryo-analizi.md`.

## 1. Benzer uygulamalar ve çıkarılacak dersler

| Uygulama | Ne yapıyor / UI | Güçlü | Zayıf | Lisans / Fiyat | networkPlus için ders |
|---|---|---|---|---|---|
| **NetSetMan** | Profil tabanlı: IP, GW, DNS, WINS, çoklu IP, IPv6, workgroup/domain, yazıcı, sürücü eşleme, HOSTS, script | Profil kavramı olgun, çok geniş kapsam | Görsel ilişki (ICS, bridge) yok, form ağırlıklı | Free: 8 profil, ticari olmayan; Pro 25–49 € ([netsetman.com](https://netsetman.com/)) | Profil/snapshot şart; diyagram durumu da profil olarak kaydedilip uygulanabilmeli |
| **Simple IP Config** | Portable IP değiştirici: IP/mask/GW/DNS, adaptör aç/kapa, sınırsız profil | Hafif, açık kaynak | Yalnız temel ayar | GPLv3 ([GitHub](https://github.com/KurtisLiggett/Simple-IP-Config)) | MVP'nin "alt sınırı"; hız ve sadelik korunmalı |
| **NETworkManager (BornToBeRoot)** | C#/WPF sekmeli araç kutusu: arayüz yapılandırma, IP/port tarayıcı, LLDP/CDP, Wi-Fi analizörü, RDP/SSH, profiller | Modern UI, çok araç | Diyagram yok | GPLv3 ([GitHub](https://github.com/BornToBeRoot/NETworkManager)) | Tanılama araçları (ping, traceroute, LLDP) düğümün sağ tık menüsüne |
| **Technitium MAC Address Changer** | MAC değiştirme, IP/GW/DNS, DHCP release/renew, IPv6 presetleri | MAC spoof, preset | Eski UI | Ücretsiz ([help](https://technitium.com/tmac/help.html)) | Inspector'da "MAC adresi (NetworkAddress advanced property)" alanı |
| **ncpa.cpl** | Adaptör ikon listesi; Özellikler → Bindings, Sharing (ICS), çoklu seçimle "Bridge Connections" | Her şey burada | İlişkiler görünmez; ICS yönü yalnız sekmeye girince anlaşılır | Yerleşik | Kullanıcının zihinsel modeli bu; terimler (Paylaşım, Köprü, Bağlamalar) aynı tutulmalı |
| **Win7 Network Map** | LLTD ile PC → switch → gateway → Internet haritası; Win8'de kaldırıldı ([Wikipedia](https://en.wikipedia.org/wiki/List_of_features_removed_in_Windows_8)) | "Internet ← gateway ← PC" metaforunun atası | Yalnız görüntüleme | – | Soldan sağa "PC → ağ → Internet" düzeni tanıdık |
| **Ayarlar > Ağ (Win10/11)** | Win11 "Gelişmiş ağ ayarları": adaptör kartları, metrik/DNS, Mobil Hotspot | Modern kart UI | Dağınık; bridge/bindings yok | Yerleşik | Kart tasarımı inspector için referans |
| **Connectify Hotspot / Dispatch** | Hotspot, bridging, çoklu WAN load-balancing; bağlantılar baloncuk | Tek tık paylaşım | Kendi sürücüsünü kurar | ≈45–55 $ ([PCWorld](https://www.pcworld.com/article/451885/review-connectify-dispatch-combines-network-adapters-to-increase-speed-and-reliability.html)) | "Paylaş" tek sürükle-bırak olmalı |
| **Speedify** | Kanal birleştirme; bağlantı başına Priority: Automatic/Primary/Secondary/Backup ([support](https://support.speedify.com/article/62-is-speedify-cost-aware)) | Öncelik kavramı çok anlaşılır | Kendi VPN'i | Abonelik | Metriği "Birincil/İkincil/Yedek" diliyle sun, arkada InterfaceMetric'e çevir |
| **TCP Optimizer** | MTU, RWIN, TCP ayarları; Current/Optimal/Custom; yedekleme | Değişiklik öncesi yedek + geri yükle | Uzman odaklı | Freeware | "Mevcut ↔ yeni değer" yan yana (diff) + yedek/geri al |
| **Wireshark arayüz listesi** | Her arayüzde canlı trafik sparkline'ı | Aktif adaptör anında görünür | – | GPL | Düğümde mini trafik grafiği, kenar kalınlığı ∝ trafik |
| **GNS3 / Packet Tracer** | Cihaz paleti, kablo aracıyla port seçip bağlama, link ışıkları | Sürükle-bağla, durum ışıkları | Simülasyon odaklı | GPL / NetAcad | Kenar çizerken **bağlantı türü menüsü** (ICS / Köprü / Yönlendir); kenar uçlarında durum ışığı |
| **NetCrunch / Spiceworks / LanTopoLog** | SNMP/LLDP fiziksel topoloji, otomatik yerleşim, port/VLAN etiketi ([alternativeto](https://alternativeto.net/software/lantopolog/about)) | Oto yerleşim, etiketler | LAN geneli; host içi yok | Ticari/freemium | Oto yerleşim + kullanıcı konum düzeltmelerinin kalıcılığı |
| **Advanced IP Scanner** | Alt ağ tarama, ad/MAC/üretici, RDP/Radmin kısayolu | Hızlı | Topoloji yok | Ücretsiz | Ağ düğümüne tıklayınca alt ağı tarayıp cihazları gösterme (v1+) |
| **Linux NetworkManager** | "Device" ↔ "Connection (profil)" ayrımı; bridge/bond/team/VLAN/hotspot birinci sınıf; ICS = "Shared to other computers" IPv4 **metodu** | Soyutlama çok temiz | Görsel değil | GPL | **Veri modeli için en iyi referans:** köprü/VLAN/takım "sanal cihaz", ICS "paylaşım yöntemi" |
| **macOS Ağ ayarları** | "Service order" sürükle-sırala; "Internet Sharing" kaynak → hedef | Öncelik sürükle-bırakla | – | Yerleşik | Metrik için sürükle-sırala; paylaşım yönlü gösterilir |
| **Hyper-V Virtual Switch Manager** | External/Internal/Private switch, "management OS paylaşsın" ([docs](https://learn.microsoft.com/windows-server/virtualization/hyper-v/get-started/create-a-virtual-switch-for-hyper-v-virtual-machines)) | vSwitch kavramı net | Form ağırlıklı | Yerleşik | vSwitch = switch düğümü; fiziksel NIC uplink, vEthernet host portu |
| **VMware Virtual Network Editor** | VMnet0 bridged, VMnet1 host-only, VMnet8 NAT ([Broadcom KB](https://knowledge.broadcom.com/external/article/339371)) | Net ağ tipi eşleme | Diyagram yok | – | VMware/VirtualBox adaptörleri "Sanal ağ" grubunda |

**Özet:** İncelenen araçların hiçbiri host içi adaptör ilişkilerini (ICS,
köprü, vSwitch, VPN varsayılan rota) **graf olarak gösterip graf üzerinden
düzenletmiyor**. Pazardaki boşluk tam networkPlus'ın hedefi. En yakın zihinsel
modeller: Win7 Network Map (görünüm), Packet Tracer (etkileşim), NetworkManager
(veri modeli).

## 2. Windows'ta adaptörler arası ilişkiler — tespit ve değiştirme

Genel: okuma çoğunlukla yetki istemez; her değişiklik yönetici ister;
`Get-VMSwitch` admin veya "Hyper-V Administrators" ister.

### 2.1 ICS
- **Tespit:** `HNetCfg.HNetShare` → `EnumEveryConnection` →
  `INetSharingConfigurationForINetConnection(conn)` → `SharingEnabled`,
  `SharingConnectionType` (0 public, 1 private)
  ([MS Learn](https://learn.microsoft.com/en-us/windows/win32/api/netcon/nn-netcon-inetsharingmanager)).
  Ek sinyaller: `SharedAccess` hizmeti, private tarafta 192.168.137.1/24.
- **Değiştirme:** önce tüm paylaşımlarda `DisableSharing()`, sonra kaynakta
  `EnableSharing(0)`, hedefte `EnableSharing(1)`
  ([Mike F Robbins](https://mikefrobbins.com/2017/10/19/configure-internet-connection-sharing-with-powershell/),
  [nullteilerfrei](https://blag.nullteilerfrei.de/2024/06/26/programmatic-internet-connection-sharing/)).
- **Registry:** `HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\ScopeAddress`
  (ICS alt ağı; maske /24 sabit).
  `HKLM\Software\Microsoft\Windows\CurrentVersion\SharedAccess\EnableRebootPersistConnection = 1`
  → yeniden başlatma sonrası çalışmama sorununun çözümü
  ([MS Learn](https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/ics-not-work-after-computer-or-service-restart)).
- **Tuzaklar:** tek public/private çifti; private IP zorla 192.168.137.1/24
  (eski ayar yedeklenip ICS kapanınca geri yüklenmeli); DHCP aralığı/DNS proxy
  ayarlanamaz; `SharedAccess` trafik yoksa ~4 dk'da durabilir → hizmet
  Automatic yapılır; VPN/TAP public yapılırsa yeniden bağlanmada paylaşım
  bozulabilir; GPO "Prohibit use of ICS" engelleyebilir; Mobil Hotspot da ICS
  kullanır → elle ICS ile çakışır; COM eşlemesi GUID ile yapılmalı.

### 2.2 Mobil Hotspot / Hosted Network
- WinRT `NetworkOperatorTetheringManager.CreateFromConnectionProfile`:
  `TetheringOperationalState`, `ClientCount`, `GetTetheringClients()`,
  `StartTetheringAsync()` / `StopTetheringAsync()`, `ConfigureAccessPointAsync`
  ([MS Learn](https://learn.microsoft.com/en-us/uwp/api/Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager)).
  Private taraf gizli Wi-Fi Direct Virtual Adapter, arkada ICS.
- Hosted Network (`netsh wlan show drivers` → "Hosted network supported")
  modern sürücülerde çoğunlukla "No"; yalnız destekleniyorsa gösterilir.

### 2.3 Ağ köprüsü
- **Tespit:** `Get-NetAdapterBinding -ComponentID ms_bridge` Enabled=True üyeler;
  köprü ayrı adaptör ("Microsoft MAC Bridge Miniport" — doğrulanmalı).
- **Değiştirme:** **Win11 22H2 + 2023-09 güncellemesi sonrası** `netsh bridge
  create/list/add/remove/destroy`
  ([woshub](https://woshub.com/bridge-network-interfaces-windows)).
  Win10'da resmi CLI yok (INetCfg COM / ncpa otomasyonu — zor).
- **Tuzaklar:** üyelerin TCP/IP'si kapanır, IP köprüye taşınır; Wi-Fi
  köprülemesi güvenilmez; köprü + ICS aynı adaptörde olmaz; köprü reboot
  sonrası kaybolabilir.

### 2.4 Hyper-V vSwitch, WinNAT, WSL
- `Get-VMSwitch`, `Get-VMNetworkAdapter -ManagementOS`; fiziksel NIC'te
  `vms_pp` bağlaması = External switch uplink'i; `Get-NetNat` WinNAT prefix'leri.
- **Default Switch `Get-NetNat`'ta görünmez** (HNS yönetir) → HNS sorgusu
  gerekir (doğrulanmalı).
- WSL NAT modunda "vEthernet (WSL)"; `networkingMode=mirrored` ise olmayabilir.
- External switch oluşturmak fiziksel NIC'in IP'sini vEthernet'e taşır, kısa kopma olur.

### 2.5 VMware / VirtualBox
InterfaceDescription ile tespit; ayrıntı için VMware Virtual Network Editor
verisi, `VBoxManage list hostonlyifs / natnetworks`. Salt okunur "Sanal ağ" düğümleri.

### 2.6 VPN
- RAS: `Get-VpnConnection` (+ `-AllUserConnection`); `SplitTunneling=False` → VPN varsayılan ağ geçidi.
- Üçüncü parti: "TAP-Windows Adapter V9", "Wintun", "OpenVPN Data Channel Offload".
- **Varsayılan rota ele geçirme:** `0.0.0.0/0` VPN'de **veya** `0.0.0.0/1` +
  `128.0.0.0/1` çifti; WireGuard `/0`'da firewall kill-switch da açar
  ([wireguard netquirk](https://git.zx2c4.com/wireguard-windows/tree/docs/netquirk.md)).

### 2.7 NIC takımı / VLAN
LBFO **Windows 10/11 istemcide desteklenmez**
([NetLbfo](https://learn.microsoft.com/en-us/powershell/module/netlbfo)); SET
`New-VMSwitch -EnableEmbeddedTeaming` ile; sürücü tabanlı (Intel ANS) görülebilir.
VLAN: `Get-NetAdapterAdvancedProperty -RegistryKeyword VlanID`,
`Get-VMNetworkAdapterVlan`. Yalnız görüntüleme ("later").

### 2.8 Yönlendirme ve internet bağlantısı
- Etkin maliyet = RouteMetric + InterfaceMetric.
- **`Find-NetRoute -RemoteIPAddress 8.8.8.8`** gerçekte seçilen arayüzü doğrudan verir →
  "internete giden yol" bununla çizilir.
- Otomatik metrik hıza göre (≥2 Gb → 5, >200 Mb → 10, 20–200 Mb → 20 …)
  ([MS Learn](https://learn.microsoft.com/en-US/troubleshoot/windows-server/networking/automatic-metric-for-ipv4-routes)).
- `Get-NetConnectionProfile.IPv4Connectivity` (Disconnected / NoTraffic /
  Subnet / LocalNetwork / Internet, NCSI tabanlı); NetworkCategory buradan okunur/değişir.

### 2.9 Forwarding, MTU, Loopback
- `Set-NetIPInterface -Forwarding Enabled` (global: `Tcpip\Parameters\IPEnableRouter`);
  ICS'siz router senaryosu bununla + `New-NetNat`.
- MTU `-NlMtuBytes`; **Jumbo frame ayrı advanced property**.
- "Loopback Pseudo-Interface 1" gizlenir; KM-TEST Loopback gösterilir.

### 2.10 Canlı güncelleme
- IP Helper (ctypes): `NotifyIpInterfaceChange`, `NotifyUnicastIpAddressChange`,
  `NotifyRouteChange2` ([netioapi](https://learn.microsoft.com/windows/win32/api/netioapi/)) —
  callback ayrı thread'de gelir → Qt sinyali + 300–500 ms debounce.
- Bağlantı durumu: NLM `INetworkEvents`, WinRT `NetworkStatusChanged`.
- WMI `__InstanceModificationEvent … MSFT_NetAdapter` polling tabanlı ve pahalı → yedek.
- Wi-Fi: `WlanRegisterNotification`. ICS/köprü olay yayınlamaz → bildirimde yeniden sorgula.

### 2.11 Genel tuzaklar
- Adaptörü kapatma / IP değiştirme RDP'yi düşürür → güvenli uygula + otomatik geri alma.
- Statik IP'ye geçişte önce `Remove-NetIPAddress` + `Remove-NetRoute`, sonra DHCP kapat;
  ActiveStore / PersistentStore ayrımına dikkat.
- Adaptör adları değişebilir → kimlik **InterfaceGuid**.

## 3. Kopyalanmaya değer diyagram UX kalıpları

1. **Katmanlı otomatik yerleşim** (soldan sağa): Sanal ağlar/VM'ler → Host PC
   (adaptörleri "port" olarak içeren konteyner) → harici ağlar (alt ağ + gateway)
   → **Internet bulutu**. Basit Sugiyama algoritması; elle taşınan konum kalıcı.
2. **Internet ve gateway düğümleri:** bulut NCSI'ye göre renklenir; gateway'de
   IP + MAC/üretici (ARP).
3. **Durum renkleri** (Packet Tracer link ışıkları gibi): yeşil internet, sarı
   yerel, kırmızı medya yok, gri devre dışı, mavi kenarlık bekleyen değişiklik.
4. **Kenar stilleri:** fiziksel düz; varsayılan rota kalın + akış animasyonu;
   ICS kesikli yönlü ok "ICS · NAT · 192.168.137.0/24"; köprü grup kutusu;
   vSwitch switch düğümü; VPN çift çizgili tünel; hotspot Wi-Fi ikonlu +
   istemci sayısı. Etiketler yakınlaştırmaya göre kısalır.
5. **Sürükle-bağla + doğrulama:** çekerken yalnız geçerli hedefler vurgulanır;
   bırakınca tür menüsü (ICS / Köprüle / Yönlendir); geçersizse tooltip ile
   sebep ("ICS zaten Wi-Fi→Ethernet2 için açık, değiştirilsin mi?").
6. **Inspector:** Genel, IPv4, IPv6, DNS, Gelişmiş (metrik, MTU, MAC, VLAN,
   advanced), Bağlamalar, Paylaşım; metrik için Birincil/İkincil/Yedek seçici.
7. **Bekleyen değişiklikler:** rozet; "Uygula (N)" → diff + üretilecek
   PowerShell komutları; doğrulama + otomatik geri alma; "yalnız betik olarak dışa aktar".
8. **Undo/Redo:** `QUndoStack`; uygulanmış değişiklikler için her Uygula
   öncesi otomatik snapshot.
9. **Filtre ve görünüm:** sanal/gizli/bağlı olmayan göster-gizle; mini harita,
   zoom, arama; PNG/SVG, draw.io XML dışa aktarma.
10. **Canlı trafik:** düğümde sparkline, kenar kalınlığı ∝ throughput.

Qt notu: özel `QGraphicsScene`/`QGraphicsView` en esnek çözüm. NodeGraphQt /
OdenGraphQt'nin "port/pipe" node-editor paradigması ağ diyagramıyla tam
örtüşmüyor (ve PySide6'ya bağlı).

## 4. Önerilen özellik listesi (ajan önerisi)

Nihai yol haritası: `project-overview.md`.

- **MVP:** envanter + filtre + GUID kimlik + tür ikonları; Host → adaptör →
  gateway → Internet diyagramı, durum renkleri, varsayılan rota vurgusu
  (`Find-NetRoute`), NCSI; inspector (DHCP/statik, IP/mask/GW, DNS, metrik,
  MTU, etkin/devre dışı, yeniden adlandır, release/renew); ICS görme + kurma;
  bekleyen değişiklik + diff + PS önizleme + güvenli uygula; canlı güncelleme;
  yetkisiz okuma + UAC'li uygulama.
- **v1:** köprü (Win11 `netsh bridge`), Mobil Hotspot, Hyper-V/WinNAT/WSL,
  VPN + split tunnel, bağlamalar + advanced properties + IPv6 +
  NetworkCategory, profiller, konum kalıcılığı, PNG/SVG, tanılama, sparkline.
- **Later:** forwarding + `New-NetNat` yönlendirme, VMware/VBox ayrıntı,
  LBFO/SET/VLAN görünümü, alt ağ tarama, LLDP/CDP, kural motoru, CLI,
  draw.io XML, çok dil, tema.

## Kaynaklar (seçme)

- ICS COM: https://learn.microsoft.com/en-us/windows/win32/api/netcon/nn-netcon-inetsharingmanager
- ICS reboot: https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/ics-not-work-after-computer-or-service-restart
- ICS scope: https://learn.microsoft.com/en-us/archive/blogs/simonmay/using-your-pc-as-a-wireless-ap-and-how-to-modify-ip-configuration
- Tethering: https://learn.microsoft.com/en-us/uwp/api/Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager
- Bridge: https://woshub.com/bridge-network-interfaces-windows · https://www.techtutsonline.com/programmatically-create-a-network-bridge-in-windows/
- Hyper-V NAT: https://learn.microsoft.com/virtualization/hyper-v-on-windows/user-guide/setup-nat-network
- WSL: https://learn.microsoft.com/windows/wsl/networking
- Metric: https://learn.microsoft.com/en-US/troubleshoot/windows-server/networking/automatic-metric-for-ipv4-routes
- NCSI: https://learn.microsoft.com/powershell/module/netconnection/get-netconnectionprofile
- IP Helper: https://learn.microsoft.com/windows/win32/api/netioapi/
- WireGuard: https://git.zx2c4.com/wireguard-windows/tree/docs/netquirk.md
- VPN: https://learn.microsoft.com/powershell/module/vpnclient/set-vpnconnection
- LBFO: https://learn.microsoft.com/en-us/powershell/module/netlbfo
