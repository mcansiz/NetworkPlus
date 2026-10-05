# ADR 0013 — GitHub Actions: üç platformda test, Windows exe + Linux AppImage + macOS .app sürümü

- Tarih: 2026-10-05
- Durum: Uygulandı — Windows exe yerelde derlendi ve sınandı; Actions çalışmalarının sonucu
  worklog'da.
- Kullanıcı: "projeyi github ile actions bölümünde 3 platformda sanal makinelerde test et;
  release için 3 platformda exe appimage ve macos binary üret — DiskUltimate projemde yaptığım gibi".

## Karar

Yapı DiskUltimate'teki (ADR 0079/0050 orada) iş akışlarının aynısıdır.

1. **`.github/workflows/tests.yml`** (çağrılabilir): Python 3.12, sabit PyQt5
   (`.github/requirements-ci.txt`), çeviri denetimi + `unittest discover` (offscreen Qt). Yalnız
   fixture ile çalışan testler; GitHub sanal makinesinde ağ **değiştirilmez**. Hata olursa `.tmp/`
   test çıktısı olarak yüklenir.
2. **`ci.yml`**: her push/PR'da (yalnız `.claude/`, `*.md`, `docs/` değişmediyse) Linux
   (ubuntu-24.04), Windows (windows-2022), macOS (macos-14, Apple Silicon) testleri.
3. **`release.yml`**: `v*` etiketi → sürüm denetimi (etiket = `src/networkplus/__init__.py`
   `__version__`) → üç platformda test → derleme + paketli program duman testi
   (`tools/smoke_frozen.py`) → **taslak** release + `SHA256SUMS`. Taslağı insan yayınlar. Elle
   çalıştırma (workflow_dispatch) = deneme: dosyalar yalnız "Artifacts"a konur. Sürüm `0.*` ya da
   `-` içeriyorsa pre-release.
4. **Windows:** mevcut PyInstaller tek dosya (ADR 0012) → `networkPlus-<sürüm>-windows-x64.exe`.
5. **Linux: AppImage** (`build_appimage.sh` → `tools/appimage.py`) →
   `networkPlus-<sürüm>-x86_64.AppImage`. PyInstaller tek dosyası derlendiği makinenin glibc'sine
   bağlı (ubuntu-24.04 → Mint 21/Ubuntu 22.04'te çalışmaz); bunun yerine `niess/python-appimage`
   manylinux2014 (glibc 2.17) taşınabilir Python + PyPI PyQt5 tekerlekleri, SHA-256 sabitli.
   `PyQt5.uic` ve `QtNetwork` **tutulur** (DiskUltimate siliyor; burada `.ui` çalışma anında
   yüklenir, tek kopya kilidi QLocalServer). `build_linux.sh` yerel kullanım için kalır.
6. **macOS: deneysel `.app`** (`build_macos.sh` ya da Actions) → `networkPlus-<sürüm>-macos-arm64.zip`.
   PyInstaller klasör çıktı + BUNDLE (tek dosya + .app her açılışta /tmp'ye açar). Simge
   `resources/networkplus.icns` (`tools/make_app_icon.py`, iconutil gerekmez). macOS'ta **canlı ağ
   keşfi yok** (ADR 0005 kapsamı değişmedi): uygulama açılır, `UnsupportedCollector` anlaşılır
   hata verir, kayıtlı anlık görüntü açılabilir. Release'de "yalnız görüntüleyici" diye yazılır;
   macOS derlemesi düşerse release yine oluşur.

## AppImage'a özgü kod değişiklikleri

AppImage içindeki Python ve `.py` dosyaları kullanıcının **FUSE bağlama noktasındadır**: kök
kullanıcı oraya erişemez, uygulama kapanınca bağlama kalkar, ağaç salt okunurdur.
- `platform/selfexec.py`: `APPIMAGE` ortam değişkeni varsa yardımcı roller (pkexec ile kök
  uygulayıcı, DHCP sunucusu), yeniden başlatma ve oturumla başlatma `.AppImage` dosyasının
  **kendisini** bayrakla çağırır (`self_command`, `command_for`). AppRun → `main.py` aynı
  bayrakları dağıtır.
- `paths.py`: AppImage'da çalışma klasörü `~/.cache/networkplus` (proje `.tmp` değil).
- `platform/linux/autostart.py`: simge kalıcı yere kopyalanır (tek dosya pakette olduğu gibi).
- Test: `tests/test_packaging.py`.

## Sonuçlar / sınırlar
- AppImage'da pkexec ile kök uygulayıcı ve DHCP sunucusu **Mint VM'de henüz sınanmadı** (Actions
  yalnız duman testi yapar: yardımcı rol argümansız çağrılır, hiçbir nmcli komutu çalışmaz).
- Paketler imzasız: Windows SmartScreen, macOS Gatekeeper (sağ tık → Aç) uyarır.
- `python-appimage` `python3.12` etiketi yuvarlanır: yeni yama çıkınca eski dosya silinir (404) →
  `tools/appimage.py` başındaki komutla ad + sha256 güncellenir.
- Actions sürümleri commit SHA'sıyla sabitlidir (DiskUltimate ile aynı).
