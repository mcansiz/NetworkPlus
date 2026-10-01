# ADR 0001 — Python + PyQt5 5.15, diyagram için QGraphicsView

- Tarih: 2026-09-30
- Durum: **Kabul edildi** (kullanıcı kararı: "projeyi python ile yapalım, GUI
  tarafı PyQt 5.15 ile yapılsın")

## Bağlam

Uygulama bir düğüm-kenar diyagramı (Creately benzeri) + sekmeli ayar paneli
gerektiriyor; Windows ağ API'lerine erişecek. Kullanıcının diğer Python
masaüstü projeleri (DiskUltimate) PyQt5 kullanıyor.

## Karar

- Dil: **Python** (makinede 3.14.7; en az 3.10 sözdizimi).
- GUI: **PyQt5 5.15** (kurulu: 5.15.11 / Qt 5.15.2; 3.14 ile import edildi,
  `QtSvg` mevcut — ölçüldü 2026-09-30).
- Diyagram: **`QGraphicsScene` / `QGraphicsView`** — hazır bir diyagram
  kütüphanesi değil.

## Gerekçe

- `QGraphicsView` tam olarak ihtiyacı karşılar: yüz binlerce öğeye ölçeklenen
  sahne, yakınlaştırma/kaydırma, seçim, sürükle-bırak, öğe başına boyama,
  `QUndoStack` ile geri alma. Ek bağımlılık getirmez.
- Web tabanlı alternatif (QWebEngine + JS diyagram kütüphanesi) ~150 MB
  ekler, Python ↔ JS köprüsü karmaşıklığı getirir.
- Kullanıcının mevcut deneyimi ve araç zinciri (PyInstaller `build_exe.bat`)
  doğrudan taşınır.

## Sonuçlar / dikkat edilecekler

- **Lisans (karar 2026-09-30):** proje **açık kaynak, GPLv3** olarak
  dağıtılacak (kullanıcı: "açık kaynak yapacağım, PyQt5 benim için yeterli").
  PyQt5'in GPLv3 lisansıyla uyumlu; ticari lisans gerekmez. Kökte `LICENSE`
  (GPLv3 tam metin). Projeye eklenecek her bağımlılık GPLv3 ile uyumlu olmalı.
- **Qt 5.15 yaşam sonu:** Qt 5.15'in açık kaynak güncellemeleri bitti; yeni
  Python sürümleri için PyQt5 tekerlekleri gecikebilir. Şimdilik 3.14 ile
  çalışıyor; bu yüzden en az 3.10 sözdizimi hedeflenir ki gerekirse eski
  Python ile paketlenebilsin.
- Yüksek DPI: `QApplication` oluşturulmadan **önce**
  `AA_EnableHighDpiScaling` ve `AA_UseHighDpiPixmaps` açılır (Qt5'te
  varsayılan kapalı; 4K/%150 ölçekte bulanık arayüz verir).
- Qt6'ya geçişi kolay tutmak için: `exec_()` yerine sarmalayıcı, enum'lar tam
  nitelikli (`Qt.AlignmentFlag.AlignLeft` biçimi PyQt5.15'te de çalışır).
