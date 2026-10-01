# ADR 0012 — PyInstaller ile tek dosya paket (Windows + Linux)

- Tarih: 2026-10-01
- Durum: Uygulandı — Windows derlendi ve sınandı; Linux betiği hazır, **derlenmedi** (kullanıcı
  "yalnız Windows" dedi).
- Kullanıcı: "windows ve linux build_win build_linux sh dosyaları oluştur, ortak spec dosyası
  oluşsun, pyinstaller ile tek dosya üretelim".

## Karar
1. **Ortak spec:** `packaging/networkplus.spec`. Ad: `networkPlus-<sürüm>-<windows|linux>-<mimari>`.
   Windows'ta exe simgesi (`resources/networkplus.ico`) ve dosya özellikleri (sürüm bilgisi).
   UPX kapalı (virüs tarayıcısı yanlış alarmı, açılış gecikmesi). `console=False`.
2. **Betikler:** `build_win.sh` (Git Bash) ve `build_linux.sh`. Proje içinde ayrı sanal ortam
   (`.venv-build-win` / `.venv-build-linux`, git'e girmez) → sistem Python'una paket kurulmaz.
   Adımlar: bağımlılıklar (`requirements.txt` + `requirements-build.txt`) → testler
   (`SKIP_TESTS=1` ile atlanır) → çeviri denetimi → simge → PyInstaller → `tools/smoke_frozen.py`.
   Ara dosyalar `.tmp/build/<os>` (Windows TEMP değil).
3. **Veri dosyaları** (`.ui .ts .qss .ps1 .png .ico`) kaynak ağacındaki göreli yerleriyle eklenir;
   kod onları `Path(__file__)` ile bulduğu için paketli hâlde değişiklik gerekmez.
4. **Yardımcı süreçler aynı exe ile** (`platform/selfexec.py`): tek dosyada ayrı Python ve `.py`
   yoktur. `--np-dhcp-daemon` (DHCP sunucusu) ve `--np-linux-helper` (pkexec ile kök uygulayıcı);
   `main.py` Qt'ye dokunmadan önce dağıtır. Kaynaktan çalışırken eskisi gibi `python betik.py`.
5. **Tek dosyanın geçici açılma klasörü** çıkışta silinir: hazır temalar düzenlenemez → kullanıcı
   tema klasörü (`QStandardPaths.AppConfigLocation/themes`, menü: Tema › Tema klasörünü aç);
   Linux otomatik başlatma simgesi `~/.local/share/icons/networkplus.png`'ye kopyalanır.
6. `.sh` dosyaları `.gitattributes`'ta `eol=lf` (Windows'tan çekilen betik Linux'ta çalışsın).

## Paket sınamasında yakalanan
- DHCP sunucusu süreci Windows'ta boruya **yerel kod sayfasıyla (cp1254)** yazıyordu; arayüz
  UTF-8 okuduğu için Türkçe hata metinleri bozuktu (kaynaktan çalışırken de). Süreç ve Linux
  uygulayıcı stdout/stdin'i UTF-8'e çevirir; `tests/test_dhcp_core.DaemonPipe` korur.

## Sonuçlar
- Windows: 42 MB; testler 119/119, duman 2/2 (DHCP rolü UTF-8 JSON, arayüz paketten 2,2 sn'de açılır).
  Kullanıcı exe'yi ana makinede çalıştırıp doğruladı (2026-10-01).
- Tek dosya her açılışta geçici klasöre açılır (~1–2 sn); DHCP sunucusu da her başlatmada açılır.
- Linux paketi derlendiği sistemin glibc'sinden eski sistemlerde çalışmaz → en eski hedefte derlenir.
- Uyarı `Hidden import "sip" not found` zararsız (PyQt5.sip kullanılıyor).
- Kod imzası yok: SmartScreen ilk açılışta uyarabilir.
