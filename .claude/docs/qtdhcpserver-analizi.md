# qtDHCPserver — Özellik Envanteri ve networkPlus'a Taşıma Haritası

Kaynak: kullanıcının daha önce yazdığı qtDHCPserver uygulaması (yerel yolu depoya yazılmaz;
salt okunur incelendi, 2026-09-30).
Kullanıcı isteği: "bu uygulama özelliklerini de ekleyelim".

## Ne
Qt 5.12 Widgets + QtNetwork, C++11, qmake/MinGW 32-bit, **yalnız Windows**, ~1100 satır.
Dosyalar: `dhcpserver.*` (motor, QUdpSocket), `dhcppacket.*` (RFC 2131 paketle/çöz),
`leasemanager.*` (havuz + kira, 30 sn süre dolumu), `networkadapterhelper.*`
(GetAdaptersInfo), `mainwindow.*` (tek pencere + tepsi), manifest `requireAdministrator`.

Kullanım gerekçesi (kaynak projenin notları): ICS'in DHCP'si kira adresini sürekli
değiştiriyordu (.49/.53/.100/...) ve her deploy'u kırıyordu → **kalıcı, deterministik
kira ve MAC→IP rezervasyonu** gerçek bir ihtiyaç.

## Kullanıcının gördüğü özellikler
- Adaptör seçimi ("<Açıklama> - <IP> (<MAC>)"), Yenile.
- DHCP Ayarları: Başlangıç/Bitiş IP, maske (255.255.255.0), ağ geçidi, DNS1/2,
  kira süresi (60–604800 sn, varsayılan 86400). Adaptör seçilince otomatik öneri:
  havuz ağ+100…+200, geçit = adaptör IP'si, DNS 8.8.8.8/8.8.4.4.
- Sunucuyu Başlat / Durdur (çalışırken ayarlar kilitli).
- Kira tablosu: MAC, IP, Bilgisayar Adı, Kira Başlangıcı, Kira Bitişi, Durum (Aktif/Bağlantı Kesildi).
- Tepsi: Göster/Çıkış, kapatınca tepsiye; bildirimler: yeni cihaz, cihaz kesildi, her ACK.

**Olmayanlar:** rezervasyon, ayar/kira kalıcılığı, günlük dosyası, ICS algılama,
güvenlik duvarı kuralı, Linux, çakışma (ARP/ping) denetimi, adaptöre IP atama.

## Protokol (özet)
- Bind: adaptör IP'si:67, `ShareAddress|ReuseAddressHint` (Windows'ta çalışır, **Linux'ta
  DISCOVER almaz**; SO_REUSEADDR port çakışmasını gizleyebilir).
- Yanıtlar hep 255.255.255.255:68; broadcast bayrağı/ciaddr/giaddr dikkate alınmıyor.
- DISCOVER→OFFER, REQUEST→ACK/NAK, RELEASE. DECLINE/INFORM yok.
- Seçenekler: 53, 54, 1, 3 (zorunlu), 6, 51. T1/T2 (58/59), 15, 28 yok; 55 okunmuyor; 61 yok.

## Bilinen hatalar (taşırken düzeltilecek)
1. DISCOVER'da ayrılan IP REQUEST gelmezse geri dönmüyor → havuz sızıntısı.
2. Option 54 denetlenmiyor → istemci başka sunucuyu seçse de ACK/NAK gönderiyor (aynı ağda düşmanca).
3. Havuz alt ağ içinde mi, sunucu/ağ/yayın adresi dışlanmış mı denetlenmiyor; tek IP'lik havuz reddediliyor.
4. Ağ geçidi zorunlu → izole cihaz ağında istemcinin varsayılan rotası bozulur.
5. "Yeni cihaz" bildirimi yanlış cihazı gösterebiliyor; her ACK'te bildirim (gürültü).
6. Durdurunca kiralar silinir (kalıcılık yok).

## networkPlus tasarımı (plan — ADR 0009)
- Diyagram: DHCP sunucusu çalışan bağdaştırıcıdan "İstemciler (x/y)" düğümüne kenar;
  kiralar düğüm/araç ipucu. Sağ tık: "DHCP sunucusu…".
- Yeni arayüz modülü `dhcp_server` (.ui): ayarlar + rezervasyonlar + kira tablosu + günlük.
- "Bağdaştırıcıya statik IP ver + sunucuyu başlat" tek akış (IP'siz adaptör sorunu çözülür).
- Motor: saf Python `socket` + `struct` (`core/dhcp/packet.py`, `leases.py` test edilebilir),
  platform katmanında soket: Windows SO_EXCLUSIVEADDRUSE + güvenlik duvarı kuralı,
  Linux SO_BINDTODEVICE (kök → helper).
- Güvenlik: yalnız açıkça seçilen adaptörde; başlamadan önce ağda başka DHCP var mı
  yoklanır; ICS açık adaptörde engellenir; kiralar/rezervasyonlar JSON ile kalıcı.
- Test: Mint VM'de VMnet5 segmentinde sunucu ens37'de, ens38 istemci (ana makineye dokunmadan).
