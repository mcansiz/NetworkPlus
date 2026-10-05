# 30 — Mimari ve Kod Kuralları

Ayrıntı: `.claude/docs/architecture.md`. Kararlar: `.claude/decisions/`.

## Teknoloji

- **Python 3.14** (bu makinede 3.14.7; en az 3.10 sözdizimi hedeflenir).
- GUI: **PyQt5 5.15** (kurulu, 3.14 ile çalıştığı ölçüldü 2026-09-30).
  Diyagram `QGraphicsScene` / `QGraphicsView` ile çizilir (ADR 0001).
- Windows erişimi: **PowerShell köprüsü**, JSON çıktı (ADR 0002).

## Katmanlar birbirine sızmaz

- `core/` → saf Python. **PyQt import etmez**, `subprocess` çağırmaz.
  Girdisi bir anlık görüntü sözlüğü (JSON), çıktısı `Topology` modelidir.
  Bu sayede fixture JSON ile işletim sisteminden bağımsız test edilir.
- `platform/` → işletim sistemine dokunan **tek** yer (Windows: PowerShell,
  `ctypes`, UAC; Linux: `ip -j`, `nmcli`, pkexec). Başka katmanda
  `subprocess`, `ctypes.windll`, sabit sistem yolu kullanılmaz.
  Her toplayıcı **normalize edilmiş snapshot** döndürür
  (`specs/snapshot-schema.md`); ham platform verisi `core/`'a girmez.
  Platforma özgü sınıflandırma ipuçları (`description`, `nm_type`,
  `link_kind`) snapshot alanı olarak taşınır, kararı `core/` verir.
- `ui/` → yalnızca sunum. Ağ mantığı içermez; `core/`'u çağırır,
  işletim sistemi işini `platform/` üzerinden bir iş parçacığında yaptırır.
  Modüler, her modülün `.ui` dosyası var (`ai_rules/50`, ADR 0006).

## Testler

```bash
python -m unittest discover -s tests -v     # cekirdek + arayuz dumani (offscreen)
python main.py --snapshot tests/fixtures/win-host.raw.json   # canli sisteme dokunmadan ac
python tools/capture_snapshot.py tests/fixtures/<ad>.raw.json # anonim fixture al (salt okunur)
```

- Paket (ADR 0012): `./build_win.sh` (Git Bash) / `./build_linux.sh` → `dist/`. Sürüm paketleri
  (ADR 0013) GitHub Actions'ta: `v*` etiketi → Windows exe + Linux AppImage (`build_appimage.sh`)
  + macOS `.app` (deneysel, yalnız görüntüleyici) → taslak release. Her push'ta üç platformda test.
  Yeni bir Qt modülü (`PyQt5.QtXxx`) kullanılırsa `tools/appimage.py` `QT_LIBS_KEEP`/`PYQT_KEEP`'e
  eklenir (yoksa AppImage'da yoktur). Kendini/yardımcıyı başlatan kod `selfexec.self_command()` /
  `command_for()` kullanır: AppImage'da `sys.executable` bağlama noktasındadır, kök erişemez. Yeni veri dosyası
  türü eklenirse spec'teki `DATA_PATTERNS`'e; ayrı süreç olarak çalışan yeni betik eklenirse
  `platform/selfexec.py`'ye bayrak eklenir (tek dosyada `python betik.py` yoktur).
- **Kaynaktan deneme tuzağı (2026-10-05):** tek kopya kilidi var — tepside paketli exe çalışıyorsa
  `python main.py` ona "göster" deyip kapanır (eski sürüm görünür). Ayrıca kurulu "networkPlus"
  yönetici görevi `dist\` içindeki exe'yi açar → kaynaktan denerken önce tepsideki uygulama kapatılır
  ve `python main.py --no-elevate` kullanılır. Yeni özellikten sonra `dist\` exe'si yeniden derlenir.
- Alt süreçle borudan konuşan Python betikleri stdout/stdin'i **UTF-8**'e çevirir (Windows'ta
  boru varsayılanı cp1254 — Türkçe metin bozulur).
- `offscreen` Qt platformu Windows'ta yazı tipi bulamaz → `QT_QPA_FONTDIR=C:/Windows/Fonts`
  (test dosyası bunu kendisi ayarlar). Aksi hâlde ekran görüntülerinde metin çıkmaz.
- Fixture'lar **ham** platform çıktısıdır (normalizasyon da test edilsin diye);
  `linux-synthetic.raw.json` elle yazılmıştır, Mint VM çıktısıyla değiştirilecek.

## Değişiklikler kuyruğa girer

Hiçbir ayar tıklama anında uygulanmaz. Her düzenleme `core/changes.py` içinde
tipli bir **adım** (`SetIPv4Static`, `SetDhcp`, `SetDns`, `EnableIcs`,
`CreateBridge`...) olur; kuyruk tek "Uygula" ile tek bir yükseltilmiş
PowerShell betiğine dönüştürülür (ADR 0003). Yeni bir değiştirme yeteneği
eklenirken önce adım türü + betik üretimi + testi yazılır, sonra arayüze
bağlanır.

## Arayüz donmaz

- Arayüz iş parçacığında PowerShell/COM/ağ çağrısı **yapılmaz**
  (tek çağrı ~0.6 sn, ölçüldü 2026-09-30). Hepsi `QThread`/worker içinde.
- Uzun işlem sessiz kalmaz: durum çubuğu / ilerleme gösterilir.

## Genel

- Görünen metin karar girdisi değildir: Windows'un **yerelleştirilmiş**
  adlarına (ör. "Yerel Ağ Bağlantısı* 6") göre karar verilmez. Kimlik olarak
  `InterfaceGuid` / `ifIndex`, tür için `InterfaceDescription`,
  `MediaType`, `PhysicalMediaType`, `ComponentID` kullanılır.
- `ifIndex` yeniden başlatmada/sürücü kurulumunda değişebilir; kalıcı
  kimlik (diyagram yerleşimini saklarken) **`InterfaceGuid`**'dir.
- Yeni özellik: önce `core/` + `tests/`, sonra `ui/`.
