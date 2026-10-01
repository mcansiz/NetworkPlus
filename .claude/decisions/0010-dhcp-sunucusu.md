# ADR 0010 — Yerleşik DHCP sunucusu (qtDHCPserver'ın networkPlus'a taşınması)

- Tarih: 2026-09-30
- Durum: Uygulandı (2026-09-30) — çekirdek, süreç, panel; Linux canlı doğrulandı, Windows kullanıcı denemesi bekliyor
- Kaynak analiz: `docs/qtdhcpserver-analizi.md`. Kullanıcı: "bu uygulamanın özelliklerini de ekleyelim".

## Karar
1. **Çekirdek saf Python** (`core/dhcp/`): `packet.py` (RFC 2131/2132 paketle/çöz),
   `leases.py` (havuz, kira, rezervasyon, teklif süresi, DECLINE karantinası, JSON
   kalıcılık), `server.py` (mesaj işleme; soket yok). Birim testle tamamen doğrulanır.
2. **Sunucu ayrı süreç** (`platform/dhcp_daemon.py`, yalnız stdlib + core): arayüzle
   stdin/stdout JSON satırları. Arayüz kapanınca/çökünce stdin EOF → sunucu durur.
   Windows: normal süreç (port 67 yönetici istemez; güvenlik duvarı kuralı yönetici ister).
   Linux: `pkexec` (port 67 + `SO_BINDTODEVICE`).
3. **Soket:** Windows'ta adaptör IP'si:67'ye **SO_EXCLUSIVEADDRUSE** (qtDHCP'deki
   ReuseAddress, ICS ile çakışmayı gizliyordu); Linux'ta 0.0.0.0:67 + `SO_BINDTODEVICE`.
   Yanıt: istemci `ciaddr` taşıyorsa unicast, değilse 255.255.255.255:68 yayın.
4. **qtDHCP hatalarının düzeltilmesi:** teklif 60 sn'de düşer (havuz sızıntısı); option 54
   başka sunucuyu gösteriyorsa sessiz kalınır; ağ geçidi/DNS isteğe bağlı; havuz alt ağ içinde
   ve sunucu/ağ/yayın adresi dışında doğrulanır; tek IP'lik havuz geçerli; T1/T2 (58/59),
   INFORM, DECLINE, option 61 (client-id) desteklenir; "yeni cihaz" bildirimi yalnız ilk kirada.
5. **Güvenlik (sahte DHCP olmamak):** sunucu şu kartlarda **başlatılamaz**: internet çıkışı,
   DHCP'den adres almış (ağda zaten sunucu var), ICS/NM-shared hedefi. Yalnız kullanıcının
   açıkça seçtiği kartta çalışır. Kartta statik IP yoksa "statik IP ver ve başlat" tek akış.
6. **Arayüz:** yeni modül `dhcp_server` (.ui) dock paneli: kart, havuz, maske, geçit, DNS,
   kira süresi, alan adı; sekmeler Kiralar / Rezervasyonlar / Günlük. Diyagramda karttan
   "DHCP istemcileri (n)" düğümüne kenar. Kart sağ tık: "DHCP sunucusu…".

## Test
- Birim: paket gidiş-dönüş, DORA, rezervasyon, NAK, başka sunucu, teklif süresi, DECLINE,
  kalıcılık, doğrulama.
- Canlı: Mint VM, VMnet5 (yalıtılmış): sunucu ens37'de, ens38 NetworkManager DHCP istemcisi
  olarak kira alır; rezervasyon; durdur. Ana makinede DHCP sunucusu ÇALIŞTIRILMAZ
  (kurumsal ağa sahte DHCP riski).

## Uygulama notları (2026-09-30)
- Denetim `core/dhcp/guard.py` (saf): `check_adapter` → ok / needs_static / needs_enable.
  Sanal ağ kartlarında (VMware/VirtualBox/libvirt) ek uyarı: kendi DHCP'leri olabilir.
- **Linux'ta "etkin değil" kart:** yalıtılmış kabloda DHCP zaman aşımı → NM bağlantıyı
  bırakır (`disconnected` = uygulamada devre dışı). Tam da sunucu kurulacak durum: statik IP
  ve etkinleştirme **iki ayrı uygulama, bu sırayla** (tek planda etkinleştirme önce koşar ve
  eski DHCP profiliyle adres beklerdi). Windows'ta devre dışı kart engelli (IP yığını yok).
- Adresi olmayan (yok / yalnız 169.254) bağlı kartta IPv4 değişikliği artık **onaysız**
  (`needs_confirmation`): kopacak bağlantı yok.
- Panel statik IP'den sonra adres okumada görünene kadar ≤20 sn bekler (yeniden okur);
  `MainWindow.refresh` okuma sürerken gelen isteği kaybetmez (bir kez daha okur).
- Diyagram katmanı `apply_overlay`: `NodeKind.DHCP_CLIENTS` (sentetik), `EdgeKind.DHCP`,
  yerleşimde 4. sütun (bilgisayar çerçevesinin dışı).
- Tepsi bildirimi yalnız yeni cihaz ve havuz dolması; kiralar diskte kaldığı için tanınan
  cihaz yeniden bağlanınca bildirim yok (bilerek).
- Uygulama kapanınca `dhcpPanel.shutdown()`; ayrıca süreç stdin EOF'ta kendiliğinden durur.
