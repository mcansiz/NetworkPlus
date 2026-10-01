# İş Günlüğü

## 2026-09-30 — Proje başlangıcı

**Yapılanlar**
- `git init` (dal `main`). `.claude/` düzeni DiskUltimate (docs/decisions/
  specs/hooks/logs/memory/sessions) ile MMCU (`CLAUDE.md` → `@ai_rules/NN-*.md`)
  birleşimi olarak kuruldu.
- `CLAUDE.md` + `ai_rules/00–60` yazıldı.
- `.claude/settings.json`: SessionEnd arşiv kancası + `cleanupPeriodDays: 36500`;
  `settings.local.json`: `autoMemoryDirectory` → `.claude/memory`.
  `.gitattributes` (`.claude/sessions/** -text -diff`), `.gitignore`.
- Oturum kalıcılığı `setup_sessions.py --dry-run` ile doğrulandı; gerçek
  kurulum bu oturum açıkken yapılmadı (transcript bölünür).
- Ana makinede salt okunur ağ keşfi → `logs/2026-09-30-host-snapshot.md`.
- Araştırma: `docs/benzer-uygulamalar.md`; analiz: `docs/senaryo-analizi.md`.
- Kararlar: ADR 0001 (Python + PyQt5 5.15 — kullanıcı kararı), 0002 (PowerShell
  JSON köprüsü), 0003 (değişiklik kuyruğu + koru/geri al), 0004 (yetki yalnız Uygula'da).

**Ölçülenler**
- PyQt5 5.15.11 / Qt 5.15.2, Python 3.14.7 ile çalışıyor; QtSvg var.
- Yalnız Windows PowerShell 5.1 var (pwsh yok).
- PowerShell UTF-8 ayarlanmazsa Türkçe adlar bozuk; tek cmdlet ≈ 610 ms.
- HNetCfg ICS durumu yönetici olmadan okunabiliyor.
- `Get-NetNat` → "Provider load failure".
- Claude Code yönetici haklarıyla çalışıyor → `ai_rules/20` ana makine yasağı.

### Aynı gün, ikinci bölüm — kullanıcı kararları ve M1

**Kararlar (kullanıcı)**
- Açık kaynak, dağıtılabilir; PyQt5 yeterli → proje **GPLv3**, `LICENSE` eklendi (ADR 0001).
- Test VM'i **Linux Mint**, Windows VM kullanılmayacak → Windows + Linux desteği (ADR 0005).
- GUI için düzenlenebilir `.ui` dosyaları, modüler yapı, her modülün `.ui`'si (ADR 0006).

**Yapılanlar**
- `platform/windows/ps/snapshot.ps1` (salt okunur, 18 bölüm) + `normalize.py` + `collector.py`;
  Linux `collector.py` + `normalize.py`; `filesource.py`.
- `core/`: `model.py`, `classify.py`, `discovery.py` (ilişkiler + rozetler), `layout.py`.
- `ui/`: `uiloader.py`, `theme.py`, `icons.py` (QPainter), `worker.py`;
  modüller `main_window`, `diagram`, `adapter_list`, `inspector` — her biri `.ui` + `.py`.
- `tools/capture_snapshot.py` (anonim fixture), `tests/fixtures/win-host.raw.json`,
  `linux-synthetic.raw.json` (sentetik), `tests/test_core.py` (15), `tests/test_ui_smoke.py` (3).
- Sonuç: 18/18 test geçiyor. Canlı sistemde gerçek pencereyle açıldı, okuma 5.0 sn.

**Ölçülenler / bulgular**
- Ham snapshot ≈ 4.9 sn (vpn 0.95, adapters 0.75, ip_interfaces 0.6 sn en pahalıları).
- **ICS kapsamı bu makinede 192.168.1.1** (varsayılan 137.1 değil) → kural: her zaman oku.
- Sınıflandırma hatası yakalandı: "Rea**lte**k" → hücresel. Kelime sınırı + test eklendi.
- `offscreen` Qt Windows'ta yazı tipi bulamıyor → `QT_QPA_FONTDIR`.
- Oturum kurulum script'i kullanıcı tarafından yanlış dizinden çalıştırıldı; açık Claude
  Code'u görüp hiçbir şey yapmadan durdu (`ai_rules/60` güncellendi).

### Aynı gün, üçüncü bölüm — M2: ayar değiştirme

Kullanıcı: "uygulama çalışıyor ama bağdaştırıcıların ayarlarını değiştiremiyorum"
(M1 bilerek salt okunurdu).

**Yapılanlar**
- `core/changes.py`: `Change`/`ChangeSet`, `validate`, `rollback_for`, `build_plan`.
- `platform/windows/apply.py`: `render_script` (uygula + onay bekleme + kendiliğinden
  geri alma tek betikte), `WindowsApplyJob` (`Start-Process -Verb RunAs`, EncodedCommand).
- `snapshot.ps1`: `dns_static` bölümü (registry `NameServer` → DNS elle mi).
- Arayüz: `inspector.ui` düzenlenebilir form; yeni modüller `changes_panel`,
  `apply_dialog`; diyagramda bekleyen işaretleri, "ICS · bekliyor" önizlemesi,
  sağ kenardaki noktadan sürükle-bağla, düğüm/kenar sağ tık menüleri.
- Testler 44/44: `test_changes.py` (19; betik metni + enjeksiyon reddi),
  `test_ui_smoke.py` (FakeJob ile koru / geri al / süre dolması / kapatılamama).
- Üretilen betik `[Parser]::ParseFile` ile sözdizimi denetiminden geçti (çalıştırılmadı).
- Canlı sistemde Uygula'nın etkin olduğu doğrulandı; **Uygula tıklanmadı**.

### Aynı gün, dördüncü bölüm — Linux uygulama, DHCP yenileme, köprü, geri al/yinele

Kullanıcı: "VM çalıştır dene", "DHCP yenileme, undo, köprü — mümkünse Linux'ta dene,
ana makineyi bozma", "oturum script'ini her defasında mı çalıştırmam gerekiyor?"
(Cevap: hayır, makine başına bir kez.)

**Yapılanlar**
- Mint VM: `mint.vmx` yedeklendi; 3 yalıtılmış NIC (VMnet5×2, VMnet6); test için 2 GB/2 çekirdek,
  sonra 8 GB/6 çekirdek/`coresPerSocket 3` geri kondu. VM düzgünce kapatıldı.
- Linux toplayıcı: tüm NM profilleri (`connection show <uuid>` tam çıktı); normalize: `nm{uuid,active,...}`,
  `dns4_setting`, `auto_metric4`, `mtu_auto`; NM `disconnected` → disabled. Gerçek fixture: `linux-mint.raw.json`.
- `core/changes.py`: `DHCP_RENEW`, `BRIDGE_CREATE`, `BRIDGE_DELETE`, `SUPPORTED` tablosu,
  `next_bridge_name`, `ChangeSet.items/restore`.
- `platform/linux/apply.py` + `helper.py`; `platform.prepare_apply` (iki platform, `.ps1`/`.sh` önizleme).
- Arayüz: geri al/yinele (`main_window.ui`'da `actUndo/actRedo`), sürükle-bağla menüsünde
  "Köprü oluştur", sağ tıkta "DHCP adresini yenile", "Köprüyü kaldır"; Uygula penceresi adım
  uyarılarını ve geri alma sonucunu gösteriyor.
- `.claude/hooks/check-sessions.py` (SessionStart): oturum geçmişi bağlı değilse hatırlatır.
- Testler 59/59 (ana makine + VM); VM canlı deneme 38/38 (`tools/vm_apply_test.py`).

**Yakalanan hatalar**
- `QUndoCommand` alt sınıfı pencereye güçlü referans tutunca çöp toplama sırasında
  access violation (6 koşunun 4'ünde). Zayıf referans + kapanışta `undo.clear()`.
- `ApplyThread` iş parçacığı bitmeden diyalog yok edilebiliyordu → `wait()` eklendi.
- Linux: DHCP'siz segmentte `nmcli device connect` takılıyor → `--wait 5` + uyarı.

**Olay:** win11 VM'i 15:37'de VMware kapatma komutuyla kapandı (Mint 15:31'de açılmıştı).
Claude win11'e komut göndermedi; neden belirsiz, kullanıcıya bildirildi.

### Aynı gün, beşinci bölüm — hız, akıllı varsayılanlar, tepsi, kart düğmeleri

Kullanıcı geri bildirimi: ETH → DHCP ana makinede çalıştı (UAC+adım 3 sn; onay 17 sn);
"süreç çok uzun"; "maskeye otomatik 255.255.255.0"; "kutular büyük"; "tepsi, sistemle
başlat, açılışta yetki"; "grafikten etkinleştir/devre dışı, özellikler"; "test dosyaları
proje yolunda, Windows TEMP kullanma"; "qtDHCPserver özelliklerini ekle"; "dil seçeneği,
işletim dili yoksa İngilizce".

**Yapılanlar**
- `needs_confirmation`: 30 sn onay yalnız riskli değişikliklerde; Uygula penceresinde kutu.
- Inspector: "Hemen uygula…", statikte maske otomatik 255.255.255.0, `IP/24` ayrıştırma,
  `24` → maske, ağ geçidi yalnız **öneri** (otomatik yazılmaz: düşük metrikli kartta
  interneti kesebilir), girişlerde rakam/nokta doğrulayıcı.
- Yönetici olarak yeniden başlat; uygulama yöneticiyse Uygula UAC'siz (`elevate.py`).
- Kartlar 210×74 → 168×54, sütun/satır aralıkları, sığdırma en çok %100.
- Kart üstü ⏻ / ⋯ düğmeleri, çift tık = özellikler.
- Tepsi + bildirim + sistemle başlat + UAC'siz yönetici görevi + tek kopya (ADR 0007).
- `paths.py` + `.tmp/` (test/shots/apply/work); Windows TEMP'teki tüm artıklar taşındı.
- qtDHCPserver analizi: `docs/qtdhcpserver-analizi.md`.
- Testler 67/67.

**Sıradaki:** dil altyapısı (Qt .ts, işletim dili yoksa İngilizce) → DHCP sunucusu.

### Aynı gün, altıncı bölüm — dil desteği (ADR 0008)
- `core/i18n.py` (Qt'siz `tr`/`N_` kancası), `networkplus/i18n/` (`TsTranslator` .ts'yi
  doğrudan okur, dil seçimi, `qps` sözde dil, `qtbase_<dil>.qm`), Ayarlar › Dil menüsü +
  yeniden başlatma (tek kopya kilidi bırakılarak).
- Tüm kullanıcı metinleri sarıldı (çekirdek, platform mesajları, arayüz); f-string'ler yer
  tutuculu `tr().format()` oldu. `Edge.dim` eklendi (metinden karar kaldırıldı).
- Araçlar: `tools/i18n_update.py` (topla/güncelle/--new/--check),
  `tools/i18n_find_untranslated.py`, `tools/i18n_fill.py`. `en.ts`: 474 metin, eksiksiz.
- `tests/test_i18n.py`: dosyalar eksiksiz, kod↔.ts senkron, sarılmamış metin yok, sözde
  dilde ekranda çevrilmemiş statik metin yok, İngilizce arayüz + çekirdek. Toplam 74/74.
- Windows konsolu cp1254: araçlar stdout'u UTF-8'e ayarlıyor.

### Aynı gün, yedinci bölüm — doğrudan uygulama (ADR 0009), arayüz düzeltmeleri
Kullanıcı: IP listede görünmüyor; paneller dar; "etkinleştir"e basınca arayüz küçülüyor;
onay formu kaldırılsın; makineye özgü kod var mı; açılışta yönetici yetkisi; router ikonu;
diyagram taşınabilir olsun; "DHCP server nerede?" (henüz yazılmadı — sıradaki).
- `ApplyRunner` + `confirm_bar` modülü; `apply_now`/`submit`; toplu kip isteğe bağlı.
- `show_window` tam ekranı bozmuyor (kök neden `showNormal()`).
- Liste: ad + altında IP (tek sütun); paneller 360/430; `STATE_VERSION=2`.
- Diyagram `dockDiagram` (taşınabilir), merkez gizli; router ikonu silindir çizimi.
- Açılışta doğrudan UAC (`startup/elevate`).
- Makineye özgü kod taraması: kaynakta ETH/IP/makine adı yok. Bulunan ortam bağımlılıkları
  düzeltildi: `netsh wlan` anahtarları dile bağlıydı (yalnız TR/EN) → GUID ile eşleme;
  Linux'ta nmcli yoksa Uygula engellenir; `vm_apply_test --nics`.
- Çökme: pencere, uygulama/yenileme iş parçacığı bitmeden kapanınca access violation
  (6 koşunun 2'si) → `runner.shutdown()` + `_thread.wait()`; testlerde tearDown bekliyor.
- Testler 80/80 (6 ardışık koşu). Bash heredoc'undan
  `python -` ile okunan Türkçe metin bozuluyor → betikler dosyaya yazılıp çalıştırılıyor.

### Aynı gün, sekizinci bölüm — DHCP sunucusu (ADR 0010)
Kullanıcı: "DHCP server özelliğimiz nerede bulamadım" → "başla".
- Çekirdek `core/dhcp/` (packet/leases/server/guard), süreç `platform/dhcp_daemon.py`,
  `ui/dhcp_service.py` (QProcess, Linux pkexec, Windows güvenlik duvarı kuralı).
- Modül `ui/modules/dhcp_server/{dhcp_server.ui,.py}`: DHCP dock paneli (Özellikler ile sekme),
  araç çubuğu + Görünüm menüsü + kart sağ tık "DHCP sunucusu…". `STATE_VERSION=3`.
- Diyagram: kart → "DHCP istemcileri (n)" düğümü (4. sütun); inspector istemci listesini gösterir.
- VM'de yakalanıp düzeltilenler:
  1. NM `disconnected` kartta akış kilitleniyordu → Linux'ta statik IP + etkinleştir (2 adım).
  2. Adressiz karta statik IP "riskli" sayılıp 30 sn onay bekliyordu → onaysız.
  3. Uygulamadan sonraki yenileme, süren okuma yüzünden kayboluyordu → okuma kuyruğa alınır;
     panel adresi ≤20 sn bekler.
  4. `DhcpService.event` sinyali `QObject.event()`'i gölgeliyordu ("native Qt signal is not
     callable") → `message`.
- Test çökmesi (0xC0000409, çıktısız): kapanmış pencere çöp toplayıcıda başka bir Qt
  çağrısının ortasında siliniyordu; ardından `SnapshotThread.finished` lambda'sı silinmiş
  pencereye ulaşıyordu. Teşhis: `QT_FORCE_STDERR_LOGGING=1` (Qt mesajı yoksa stderr'e
  gelmiyor). Düzeltme: `finished` → bağlı metot; testlerde `dispose()` (close + deleteLater +
  DeferredDelete). DHCP yeniden deneme zamanlayıcısı da bağlı metot.
- Testler 106/106 (ardışık koşularda kararlı). Canlı: `vm_dhcp_test` 10/10,
  `vm_dhcp_gui_test` 15/15 ve `--disconnect-first` 16/16. VM temizlendi, kapatıldı,
  vmx kaynakları geri yüklendi (8192 MB / 6 vCPU / 3 çekirdek-soket).

## 2026-10-01 — Uygulama simgesi, İnternet ikonu
Kullanıcı: görev çubuğundaki yeşilimsi simge belli olmuyor; İnternet düğümündeki ikon anlamsız.
- `ui/app_icon.py`: dolu mavi rozet + beyaz ağ çizimi (bilgisayar → iki düğüm); pencere/görev
  çubuğu simgesi (`app.setWindowIcon`). Tepside aynı rozet, alt düğüm internet durumunu renkle
  gösterir (yeşil/sarı/gri). Eski tepsi simgesi şeffaf zeminde ince yeşil Wi-Fi çizgisiydi.
- Windows: `platform.set_app_identity()` → `SetCurrentProcessExplicitAppUserModelID`; görev
  çubuğu düğmesi python.exe'nin simgesi/grubu altında görünmesin. Kullanıcı ana makinede
  doğruladı (2026-10-01): görev çubuğunda mavi simge görünüyor.
- İnternet ikonu bulut → dünya: bulut elips birleşiminden (`simplified()`) oluşuyordu,
  küçük boyutta dolguda delikler kalıyordu.
- Kullanıcı simgeyi büyütmek istedi; tepsi simgesinin piksel boyutunu Windows belirler (%100'de
  16 px), bu yüzden rozet kenara kadar dolduruldu, çizgiler kalınlaştırıldı. Dört seçenek
  (ağ kare / ağ yuvarlak / diyagram / Ethernet portu) karşılaştırma sayfasıyla sunuldu;
  kullanıcı **Ethernet portu (RJ45)**'nu seçti. Diğer çizimler koddan kaldırıldı.
- `.ico`: `tools/make_app_icon.py` → `src/networkplus/resources/networkplus.ico` (16–256 px,
  9 boyut, PNG gömülü; Qt'nin ICO yazıcısı tek boyut yazdığı için dosya elle kuruluyor) +
  `networkplus.png` (256). Linux otomatik başlatma `.desktop` dosyası `Icon=` ile bunu gösterir.
  Çizim değişirse araç yeniden çalıştırılır (tek kaynak `ui/app_icon.py`).

### Aynı gün — varsayılan yerleşim, yerleşimin hatırlanması, menü düzeltmeleri
Kullanıcı: "default yerleşim resimdeki gibi olsun", "kullanıcı yerleşimi hatırlansın",
"üst menü ayarlar içeriklerini de hatalı ve gereksiz varsa düzelt".
- Varsayılan: solda Bağdaştırıcılar/Özellikler, ortada Diyagram, sağda DHCP (`reset_layout`,
  `STATE_VERSION=4`). `resizeDocks` gizli merkez parçacıkta etkisizdi → geçici minimumSize.
- Yerleşim artık yalnız kapanışta değil: panel değişince (gecikmeli), tepsiye giderken,
  `aboutToQuit`, `commitDataRequest` (Windows oturum kapanışı) kaydediliyor. Görünüm menüsüne
  "Panelleri varsayılan yerleşime döndür".
- `main.py --screenshot` kullanıcının QSettings'ini okuyup kapanışta ÜZERİNE YAZIYORDU →
  ayrı organizasyon adı (`networkPlus-screenshot`).
- Menü düzeltmeleri: ayarlar tıklanınca kaydediliyor (önceden yalnız kapanışta); "Otomatik
  yenile" hatırlanıyor; Değişiklikler menüsü toplu kip kapalıyken boş açılıyordu → gizli;
  "Bekleyen değişiklikler" panel anahtarı gri yerine gizli; "Uygula…" (eski pencereyi
  ima ediyordu) → "Kuyruğu uygula"; "Otomatik yerleşim/Sığdır" → "Diyagramı …" (panel
  yerleşiminden ayrılsın); bildirim ve açılışta yönetici ipuçları tamamlandı.
- Hata: zamanlayıcıda kapanış (closure) pencere silindikten sonra çalışıp test sürecini
  çökertti → bağlı metot (ai_rules/50 kuralı). Testler 108/108.

### Aynı gün — QSS temaları (ADR 0011) ve beş yeni dil
Kullanıcı: "projeye qss formatında koyu ve açık tema ekleyelim", "dil seçeneklerini de çoğaltalım"
(seçim: Almanca, Rusça, İspanyolca, Fransızca, Çince).
- `ui/themes/{light,dark}.qss` + yükleyici; palet `.qss` baş yorumunda (`@palette`), çünkü
  QSS paleti değiştirmez ve diyagram paletle çizilir. Ayarlar › Tema: Otomatik (varsayılan;
  Windows `AppsUseLightTheme`, Linux `gsettings`) / Sistem görünümü / Açık tema / Koyu tema
  (+ klasöre eklenen her `.qss`). Canlı geçiş. Geliştirme makinesi koyu modda → varsayılan koyu.
- QSS'te spin/combo kutusuna kenarlık ok düğmelerini bozuyordu → Fusion'a bırakıldı.
- Çeviri: 562 benzersiz metin, dil başına bir ajan (arka plan iş akışı; kullanıcıya önceden
  sorulmadan başlatıldı — bildirildi). Her ajan yer tutucu/`&`/HTML/boşluk öz denetimi yaptı;
  `i18n_update --check` 7 dilin hepsinde eksiksiz. Terim düzeltmeleri: de `Wi-Fi`→`WLAN`,
  zh `Ethernet`/`Bluetooth`→`以太网`/`蓝牙` (yalnız tür etiketi; bağdaştırıcı adları veri).
- Çince'de lejant çizgileri kare çıkıyordu (kutu çizim karakterleri) → `— – ·`.
- Testler 114/114: `test_themes` (palet rolleri, QSS uyarısız ayrışır, çözümleme, canlı geçiş,
  kullanıcı teması), her dilde pencere açılır ve menüler çevrili.

### Aynı gün — tek dosya paket (ADR 0012) ve tepsi bilgi penceresi
Kullanıcı: "build_win build_linux sh dosyaları, ortak spec, pyinstaller ile tek dosya";
"taskbarda simge üzerine geldiğimizde resimdeki gibi bilgilendirme açılsın".
- `packaging/networkplus.spec`, `build_win.sh`, `build_linux.sh`, `requirements-build.txt`,
  `tools/smoke_frozen.py`. Derleme ortamı proje içinde ayrı venv. Kullanıcı yalnız Windows
  derlemesini istedi: `dist/networkPlus-0.1.0-windows-x64.exe` (42 MB), testler 119/119,
  duman 2/2. Linux betiği **derlenmedi**.
- Tek dosya için: yardımcı süreçler aynı exe + gizli bayrak (`platform/selfexec.py`);
  kullanıcı tema klasörü + "Tema klasörünü aç"; Linux otomatik başlatma simgesi kalıcı yere.
- Paket sınaması gerçek hata buldu: DHCP sunucusu boruya cp1254 yazıyordu (Türkçe bozuk) →
  UTF-8 (+ regresyon testi).
- Tepsi bilgi penceresi: `ui/modules/tray_popup` (.ui + .py). QSystemTrayIcon'un "üzerine
  gelindi" sinyali yok ve Windows ipucu düz metin → imleç 200 ms'de bir yoklanır, simge
  üzerinde ~0,4 sn kalınca çerçevesiz pencere açılır (ad, açıklama, durum, Wi-Fi + sinyal,
  IPv4/maske, DHCP, ağ geçidi); simge ve pencere dışında ~0,6 sn sonra kapanır, sağ tık menüsü
  açıkken açılmaz; satıra tıklamak özellikleri açar. Simge konumu bilinmeyen masaüstlerinde
  (bazı Linux) düz ipucu kalır. Hata: eski satırlar `deleteLater` beklerken yenisiyle üst üste
  çiziliyordu → hemen gizle. Kullanıcı paketli exe ile gerçek Windows tepsisinde doğruladı
  (2026-10-01: "evet çalışıyor").
- Heredoc tuzağı tekrar: `
` gerçek satır sonuna dönüştü (test dosyası bozuldu) → Edit ile düzeltildi.

**Doğrulanmamış (kullanıcı denemesi bekliyor)**
- Paketli exe'nin gerçek kullanımı: UAC ile yükseltme, DHCP sunucusu, otomatik başlatma.
- Linux paketi (betik hazır, derlenmedi).
- Beş yeni dilin anadil gözden geçirmesi (yapay zekâ çevirisi).
- Windows'ta DHCP sunucusu: güvenlik duvarı kuralı (UAC), `SO_EXCLUSIVEADDRUSE` bağlama,
  gerçek istemci. Ana makinede kurumsal ağa bağlı kartta DEĞİL, boş bir kartta denenmeli.
- Gerçek UAC + `Set-NetIPInterface`/`New-NetIPAddress`/HNetCfg `EnableSharing` davranışı.
- `Start-Process -Verb RunAs` + `-WindowStyle Hidden` altında betiğin work dir'e yazabilmesi.

**Açık**
- Oturum junction kurulumu: VS Code kapalıyken, proje dizininden.
- Mint VM: kapalı (ping yok). Açmak + Linux toplayıcıyı çalıştırmak için kullanıcı onayı.
  ICS/köprü testleri için ikinci NIC (VM yapılandırma değişikliği) sorulacak.
- M2: değişiklik kuyruğu + Uygula + diyagramda yol çizerek ICS.
