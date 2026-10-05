# 40 — Windows Ağ API'leri: Nereden Okunur, Nasıl Değiştirilir

Senaryo bazında ayrıntı: `.claude/docs/senaryo-analizi.md`.
"Ölçüldü" işaretli satırlar bu makinede (Win10 19045) 2026-09-30'da denendi.

## PowerShell köprüsü kuralları

- Her betik başında: `[Console]::OutputEncoding = [Text.Encoding]::UTF8`.
  **Neden:** olmadan Türkçe arayüz adları bozuk gelir
  ("Yerel A� Ba�lant�s�* 6") — ölçüldü. Python tarafı `encoding="utf-8"` okur.
- `-NoProfile -NonInteractive -ExecutionPolicy Bypass` ile çağrılır.
- Çıktı **yalnızca JSON** (`ConvertTo-Json -Depth 6 -Compress`). Tablo metni
  ayrıştırılmaz.
- Windows PowerShell 5.1'de `ConvertTo-Json` enum'ları **sayı** yazar
  (`Dhcp: 1`, ölçüldü) ve `-EnumsAsStrings` yoktur. Enum alanları
  `Select-Object @{n='Dhcp';e={"$($_.Dhcp)"}}` ile metne çevrilir.
- Tek elemanlı sonuç JSON dizisi değil nesne döner → betikte `@(...)` ile
  sarılır, Python tarafı yine de listeye normalize eder.
- Bir alt sorgu hata verirse tüm anlık görüntü düşmez: her bölüm
  `try/catch` içinde, hata `errors` alanına yazılır.
  Örnek: `Get-NetNat` bu makinede **"Provider load failure"** verir
  (WinNAT/Hyper-V yok) — ölçüldü.
- PowerShell süreç açılışı pahalıdır (~0.6 sn tek cmdlet, ölçüldü). Anlık
  görüntü **tek betikte** alınır; canlı izleme için süreç her seferinde
  yeniden açılmaz (ADR 0002).

## Okuma (yetki gerekmez)

| Bilgi | Kaynak |
|---|---|
| Bağdaştırıcılar (gizliler dahil) | `Get-NetAdapter -IncludeHidden` (Name, InterfaceDescription, InterfaceGuid, ifIndex, Status, MacAddress, LinkSpeed, MediaType, PhysicalMediaType, Virtual, Hidden, ComponentID, DriverDescription) |
| IP arayüz ayarları | `Get-NetIPInterface` (Dhcp, InterfaceMetric, AutomaticMetric, Forwarding, NlMtu, ConnectionState) |
| Adresler | `Get-NetIPAddress` (PrefixOrigin: Dhcp/Manual/WellKnown → APIPA tespiti) |
| DNS | `Get-DnsClientServerAddress`, `Get-DnsClient` (sonek, kayıt) |
| Rotalar | `Get-NetRoute` — varsayılan rota `0.0.0.0/0`, `::/0` |
| İnternet var mı | `Get-NetConnectionProfile` (IPv4Connectivity: Internet/LocalNetwork/NoTraffic, NetworkCategory) |
| Ağ geçidi MAC | `Get-NetNeighbor -IPAddress <gw>` |
| Bağlamalar | `Get-NetAdapterBinding` (ms_tcpip, ms_tcpip6, ms_bridge, ms_server, ms_msclient, vms_pp = Hyper-V) |
| ICS durumu | COM `HNetCfg.HNetShare` → `INetSharingConfigurationForINetConnection.SharingEnabled / SharingConnectionType` (0=Public, 1=Private). **Yönetici olmadan okunabildi** — ölçüldü |
| ICS hizmeti | `Get-Service SharedAccess` |
| Wi-Fi | `netsh wlan show interfaces` (SSID, sinyal, kanal, band) — metin çıktısı, yerelleştirilmiş; anahtar adlarına değil sıraya/biçime dikkat. TODO: WinRT/`WlanQueryInterface` alternatifini değerlendir |
| Hotspot | WinRT `NetworkOperatorTetheringManager` (TetheringOperationalState, ClientCount) |
| Hyper-V | `Get-VMSwitch`, `Get-NetNat` (yoksa hata — tolere et) |
| VPN | `Get-VpnConnection` (+ `-AllUserConnection`) |
| Takım / VLAN | `Get-NetLbfoTeam`, `Get-NetAdapterAdvancedProperty -RegistryKeyword VlanID` |
| Sürücü "Gelişmiş" sekmesi | `Get-NetAdapterAdvancedProperty -Name *` (yalnız `DisplayName`'li olanlar = Aygıt Yöneticisi listesi; `-AllProperties` gizli kayıtları da verir). Betik içinde ~65 ms, bu makinede 63 özellik — ölçüldü 2026-10-05. `DisplayName`/`DisplayValue`/`ValidDisplayValues` **sürücü dilindedir** → karar girdisi değil; kimlik `RegistryKeyword`, değer `RegistryValue` |

## Değiştirme (yönetici gerekir — yalnızca VM'de dene, bkz. `20`)

| İşlem | Komut |
|---|---|
| Statik IPv4 | `Remove-NetIPAddress` + `New-NetIPAddress -IPAddress -PrefixLength -DefaultGateway`; önce `Set-NetIPInterface -Dhcp Disabled` |
| DHCP'ye dön | `Set-NetIPInterface -Dhcp Enabled`; eski statik IP ve **eski ağ geçidi rotası ayrıca silinir** (yoksa kalır) |
| DNS | `Set-DnsClientServerAddress -ServerAddresses` / `-ResetServerAddresses` |
| Metrik | `Set-NetIPInterface -InterfaceMetric` (AutomaticMetric kapanır) |
| MTU | `Set-NetIPInterface -NlMtuBytes` |
| Etkin/devre dışı | `Enable-/Disable-NetAdapter -Confirm:$false` |
| Yeniden adlandır | `Rename-NetAdapter` |
| Bağlama | `Enable-/Disable-NetAdapterBinding -ComponentID` |
| IP yönlendirme | `Set-NetIPInterface -Forwarding Enabled` |
| ICS | `HNetCfg.HNetShare`: public → `EnableSharing(0)`, private → `EnableSharing(1)`; kapatma `DisableSharing()` |
| Köprü | **Win11 22H2 + 2023-09 güncellemesi sonrası** `netsh bridge create/add/remove/destroy`. Win10'da resmi CLI yok → Win10'da köprü **yalnız görüntülenir** (INetCfg COM zor, ertelendi) |
| ICS kalıcılığı | `HKLM\Software\Microsoft\Windows\CurrentVersion\SharedAccess\EnableRebootPersistConnection = 1` + `SharedAccess` hizmeti Automatic |
| Gelişmiş sürücü | `Set-NetAdapterAdvancedProperty` (Jumbo, VLAN ID, Speed/Duplex...) |

## Linux (NetworkManager) — Mint VM'de ölçülenler (2026-09-30)

- Yazma `platform/linux/apply.py` → nmcli **argv listeleri** (kabuk yok) → kökte
  `helper.py` (pkexec; bağımsız, yalnız stdlib). Protokol Windows ile aynı.
- Profil **UUID** ile hedeflenir; profil yoksa `networkplus-<if>` oluşturulur.
  Uygulamanın oluşturduğu tüm profiller `networkplus-` önekiyle başlar.
- DNS/metrik: `nmcli device reapply` (bağlantı düşmez). IP/MTU/paylaşım: `con up`.
- DHCP'ye dönüşte ya da DHCP profilli aygıtı açarken sunucu yoksa `con up` /
  `device connect` IP beklerken takılır ve hata döner → **uyarı** sayılır;
  `device connect` için `--wait 5` (yoksa aygıtın son durumu zamanlamaya bağlı kalıyor — yakalandı).
- Köprü: önce köprü ve port profilleri eklenir, **portlar** etkinleştirilir (köprüyü
  kendiliğinden açar). Köprüyü önce açmak DHCP'de port olmadan bekler.
  `slave-type bridge` + `master <ad>` NM 1.46'da çalışıyor; alanlar `connection.controller`/
  `connection.master`, `connection.port-type`/`slave-type` olarak ikisi de görünür.
- NM `disconnected` (taşıyıcı var, bağlantı etkin değil) → normalize'da **disabled**;
  `unavailable` (taşıyıcı yok) → disconnected. `connecting (...)` → up.
- NM "shared": hedef 10.42.0.1/24 olur, dnsmasq DHCP dağıtır; paylaşılan trafik
  varsayılan rotadan çıkar (kaynak seçimi yok).
- Linux'ta arayüz yeniden adlandırma desteklenmez (`SUPPORTED` tablosu, `core/changes.py`).

## Bilinen tuzaklar

- **ICS aynı anda tek bir public + tek bir private** bağdaştırıcıya izin verir.
  Yeni bir çift açmadan önce mevcut paylaşım kapatılır; arayüz bunu planda
  gösterir.
- ICS açılınca private bağdaştırıcının IP'si `ScopeAddress`/24 olur
  (`HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\ScopeAddress`).
  Varsayılan 192.168.137.1 ama **varsayılmaz, her zaman okunur**: geliştirme
  makinesinde 192.168.1.1'e değiştirilmiş (ölçüldü 2026-09-30).
  Mevcut statik IP'nin üzerine yazılır — plan bunu uyarı olarak gösterir.
- Win10'da ICS yeniden başlatmadan sonra "açık görünüp çalışmaz"; ayrıca
  `SharedAccess` trafik yoksa ~4 dk'da durabilir. Çözüm yukarıdaki
  `EnableRebootPersistConnection` + hizmeti Automatic yapmak (MS KB). ICS
  kurulurken bu ikisi plana otomatik eklenir. TODO: VM'de doğrula.
- ICS'i açmadan önce private bağdaştırıcının mevcut IP ayarı **saklanır**;
  ICS kapatılınca geri yükleme önerilir.
- Mobil Hotspot da arkada ICS kullanır → elle ICS ile **çakışır**; plan uyarır.
- Birden çok varsayılan rota olabilir (bu makinede Wi-Fi + Radmin VPN,
  ölçüldü). "İnternete çıkan yol" **`Find-NetRoute -RemoteIPAddress <genel IP>`**
  ile belirlenir (Windows'un gerçek seçimi); RouteMetric + InterfaceMetric
  toplamı yalnız etiket ve açıklama içindir.
- VPN varsayılan rotayı yalnız `0.0.0.0/0` ile değil, **`0.0.0.0/1` +
  `128.0.0.0/1` çifti** ile de ele geçirebilir (OpenVPN/WireGuard) — ikisi de
  "full tunnel" sayılır.
- Hyper-V **Default Switch `Get-NetNat`'ta görünmez** (HNS yönetir);
  NAT ilişkisi vEthernet (Default Switch) adından/HNS'den çıkarılır (doğrulanmalı).
- LBFO takımı **Windows 10/11 istemcide yoktur**; `Get-NetLbfoTeam` hata
  verirse normaldir.
- Jumbo frame MTU değil, ayrı bir advanced property'dir.
- `Virtual=True` her zaman "önemsiz" değildir (VPN, VMware NAT). Gizli
  (`Hidden=True`) olanlar — WAN Miniport, Kernel Debug, Teredo, 6to4,
  IP-HTTPS — varsayılan olarak diyagramda **gizlenir**, filtreyle açılır.
- Microsoft Wi-Fi Direct Virtual Adapter, Mobil Hotspot açıldığında
  kullanılan sanal bağdaştırıcıdır; hotspot ilişkisi bunun üzerinden çizilir.
- VMware VMnet8 NAT'ı Windows ICS/WinNAT değil **VMware NAT Service** yapar;
  ilişki "VMware NAT" olarak ayrı türle gösterilir.
