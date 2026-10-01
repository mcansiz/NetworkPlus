# 50 — Arayüz ve Diyagram

Referans görünüm: Creately "Cisco Network Diagram" (kullanıcının paylaştığı
ekran görüntüsü, 2026-09-30): solda şekil paleti, ortada tuval, üstte araç
çubuğu, altta yakınlaştırma; router/switch/PC ikonları, etiketli oklar.

## Modüler yapı ve `.ui` dosyaları (ZORUNLU — ADR 0006)

- Her arayüz modülü `src/networkplus/ui/modules/<modul>/` altında
  **`<modul>.ui` + `<modul>.py`** çiftidir. Yerleşim/görünüm `.ui`'da
  (kullanıcı Qt Designer'da düzenler), davranış `.py`'de.
- `.ui` çalışma anında `load_ui(self, __file__)` ile yüklenir; `pyuic5`
  çıktısı üretilmez ve depoya konmaz.
- Modüller ana pencereye promote edilmiş widget olarak girer; özel çizim
  yapan widget'lar (`DiagramView`) da `.ui` içinde promote edilir.
- `.py`'nin kullandığı her `objectName` `require(...)` listesinde olur.
  Kullanıcının `.ui` düzenlemelerine saygı: Claude `.ui` dosyasını yeniden
  **üretmez**, yalnız gereken yeri düzenler; kullanıcının taşıdığı/yeniden
  boyutlandırdığı öğeleri geri almaz.
- Yeni widget eklenirken önce `.ui`'ya eklenir (Designer uyumlu XML), sonra
  `.py`'de bağlanır.
- `.ui` dosyaları **Qt 5.15 Designer** ile açılır:
  `C:\Qt\5.15.2\msvc2019_64\bin\designer.exe`. Makinedeki Qt 6.8 Designer
  kaydederken Qt6'ya özgü yazım (ör. tam nitelikli enum `Qt::Orientation::Vertical`)
  üretebilir; PyQt5 `uic` bunu okuyamayabilir (doğrulanmadı — risk).
  Designer'da promote edilmiş modüller boş `QWidget` olarak görünür; bu normaldir,
  her modül kendi `.ui`'sinde düzenlenir. Düzenlemeden sonra
  `python -m unittest tests.test_ui_smoke` çalıştırılır.

| Modül | `.ui` | Sorumluluk |
|---|---|---|
| `main_window` | `main_window.ui` | Menü, araç çubuğu, dock'lar, modüller arası senkron |
| `diagram` | `diagram_panel.ui` | Tuval (`DiagramView`), yakınlaştırma, yerleşim, lejant |
| `adapter_list` | `adapter_list.ui` | Gruplu liste, arama, gizlileri göster |
| `inspector` | `inspector.ui` | Seçili düğüm/kenarın özellikleri; bağdaştırıcı formu → "Kuyruğa ekle" |
| `changes_panel` | `changes_panel.ui` | Bekleyen değişiklikler listesi, Uygula / çıkar / tümünü at |
| `apply_dialog` | `apply_dialog.ui` | Plan + uyarılar, betik önizleme, UAC, 30 sn koru/geri al |
| `confirm_bar` | `confirm_bar.ui` | Diyagram üstü şerit: uygulanıyor / Koru–Geri al / sonuç |
| `dhcp_server` | `dhcp_server.ui` | DHCP sunucusu paneli: kart, havuz, kiralar, rezervasyonlar, günlük (ADR 0010) |

Servis/iş nesnelerinde Qt sanal metot adlarını (`event`, `timerEvent`, `childEvent`…)
sinyal ya da özellik adı olarak **kullanma**: Qt her olayda onu çağırır (bkz. worklog §8).
Başka bir iş parçacığından/süreçten gelen sinyali **lambda'ya değil bağlı metoda** bağla:
nesne silinince PyQt bağlantıyı yalnız bağlı metotlarda koparır.

`inspector.ui` ilk kez `scratchpad` içindeki tek seferlik bir üreteçle
yazıldı; artık **elle/Designer'da** düzenlenir, yeniden üretilmez.

## Tema (ADR 0011)

- Temalar `ui/themes/*.qss`; baş yorumdaki `@palette` satırları Qt paletini verir (QSS paleti
  değiştirmez, diyagram paletle çizilir). Yeni `.qss` = menüde yeni tema.
- Kodda nötr renk (zemin, metin, çizgi, seçim) **sabit yazılmaz**, `palette_color(...)` ile
  alınır; aksi hâlde koyu temada bozulur. Sabit renk yalnız anlam taşıyorsa (durum, ilişki).
- QSS'te `QSpinBox`/`QComboBox`'a kenarlık verme (ok düğmeleri kaybolur).
- Varsayılan `auto`: işletim sisteminin açık/koyu tercihi.

## Dil (ZORUNLU — ADR 0008)

- Kaynak dil Türkçe; her kullanıcı metni çevrilebilir olmalı: `.ui`'da yazılan metin
  kendiliğinden; `.py`'de `tr("...")` (`core/i18n.py`), modül sabitlerinde `N_()`.
- Değişkenli metin **yer tutuculu**: `tr("{name} bağlandı").format(name=...)`. f-string
  içinde çeviri yapılmaz; metin parçalanıp birleştirilmez.
- Metin karar girdisi değildir (çevrilince bozulur) → durum bayrakla taşınır.
- Bilerek çevrilmeyen (CLI yardımı, dilin kendi adı) satır `# notr` ile işaretlenir.
- Metin ekledikten sonra: `python tools/i18n_update.py` → `en.ts`'de çeviri
  (Qt Linguist ya da `tools/i18n_fill.py`) → `python -m unittest tests.test_i18n`.
- Varsayılan dil: işletim sistemi dili destekleniyorsa o, yoksa İngilizce.
- Diller (2026-10-01): tr (kaynak), en, de, ru, es, fr, zh_CN. Yeni metin eklenince **her
  `.ts`** doldurulur (`tools/i18n_fill.py <kod> <json>`); `--check` hepsini denetler.
- Arayüzde kutu çizim karakteri (━ ╍ ┅) kullanma: Çince yazı tipinde yok, kare çıkıyor.

## Yerleşim

**Varsayılan panel yerleşimi (kullanıcı, 2026-10-01):** solda Bağdaştırıcılar (üst) +
Özellikler (alt), ortada Diyagram, sağda DHCP sunucusu; Bekleyen değişiklikler altta ve
yalnız toplu kipte. Varsayılan değişirse `STATE_VERSION` artırılır (eski kayıt bir kez
yok sayılır). **Kullanıcının yerleşimi hatırlanır:** panel taşınınca/açılıp kapanınca
~0,8 sn sonra, tepsiye giderken, çıkışta ve Windows oturumu kapanırken kaydedilir;
"Görünüm › Panelleri varsayılan yerleşime döndür" ile sıfırlanır. Merkez parçacık gizli
olduğu için `resizeDocks` etkisiz; varsayılan boyut geçici `minimumSize` ile verilir.
Ayar onay kutuları tıklanınca hemen kaydedilir.

- **Sol panel:** bağdaştırıcı listesi / filtreler (fiziksel, sanal, gizli,
  bağlı olmayan) ve arama.
- **Orta:** diyagram tuvali (`QGraphicsView`), yakınlaştır/kaydır, mini harita.
- **Sağ panel (inspector):** seçili düğüm/kenarın tüm ayarları, sekmeli
  (Genel, IPv4, IPv6, DNS, Gelişmiş, Bağlamalar, Paylaşım).
- **Alt çubuk:** bekleyen değişiklik sayısı + **Uygula** / **Vazgeç**,
  yakınlaştırma yüzdesi.
- **Üst:** Yenile, Otomatik yerleşim, Profil kaydet/yükle, Dışa aktar (PNG/SVG/JSON).

## Katmanlı yerleşim (soldan sağa veya yukarıdan aşağı)

```
[İnternet] → [Ağ geçidi / router] → [Bağdaştırıcı (PC)] → [Aşağı akış: ICS istemcisi, VM ağı, hotspot istemcileri]
```

- PC, bağdaştırıcıları içeren bir **çerçeve (grup)** olarak çizilir.
- Kullanıcının taşıdığı düğüm konumları `InterfaceGuid` anahtarıyla saklanır;
  otomatik yerleşim yalnız yeni düğümlere uygulanır.

## Düğüm türleri

Internet, Gateway, PhysicalEthernet, WiFi, Bluetooth, Cellular, VirtualHostOnly
(VMware/VirtualBox), VirtualNat, HyperVSwitch, vEthernet, Vpn/Tunnel, Bridge,
Team, Hotspot (Wi-Fi Direct), Loopback. Her türün kendi QPainter ikonu olur.

## Kenar (ilişki) türleri ve görünüm

| Tür | Anlamı | Görünüm |
|---|---|---|
| `uplink` | Bağdaştırıcı → ağ geçidi (varsayılan rota) | Düz; etiket: metrik |
| `internet` | Ağ geçidi → İnternet (NCSI = Internet) | Düz, kalın |
| `active_route` | Şu an internete çıkan yol | Yeşil vurgu |
| `ics` | Public → private internet paylaşımı | **Turuncu, kesikli ok**, etiket "ICS" |
| `bridge` | Üye bağdaştırıcı → köprü | Mor |
| `vswitch` | Fiziksel NIC → Hyper-V dış anahtar → vEthernet | Mavi |
| `nat` | Host → VMware/WinNAT sanal ağ | Kesikli mavi, etiket "NAT" |
| `tunnel` | VPN bağdaştırıcısı → taşıyan fiziksel bağdaştırıcı | Noktalı |
| `hotspot` | Wi-Fi → Wi-Fi Direct sanal bağdaştırıcı | Turuncu noktalı |
| `team` | Üye → takım | Gri kalın |

## Durum renkleri

- Yeşil: bağlı + İnternet; sarı: bağlı, yalnız yerel ağ / APIPA;
  gri: bağlantı yok / devre dışı; kırmızı: hata (IP çakışması, DHCP alınamadı);
  kesikli çerçeve: **bekleyen değişikliği olan** düğüm.
- Renk tek bilgi kanalı olmaz: durum ikonu + metin de gösterilir.

## Etkileşim

- Bir düğümün kenarından sürükleyip başka düğüme bırakmak **ilişki önerir**:
  uygun türler menüde listelenir (Wi-Fi → ETH: "İnternet paylaşımı (ICS)",
  "Köprü oluştur"). Geçersiz hedefler sürükleme sırasında soluklaşır.
- Kenarı silmek ilişkiyi kaldırmayı **kuyruğa ekler** (ICS kapat, köprüden çıkar).
- Her düzenleme geri alınabilir (`QUndoStack`); kuyruk ile aynı kaynaktan beslenir.
- Sağ tık menüsü ait olduğu düğümde açılır (Etkinleştir/Devre dışı, DHCP'yi
  yenile, Tanıla, Özellikler).
