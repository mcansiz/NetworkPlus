# ADR 0006 — Modüler arayüz, her modülün Qt Designer `.ui` dosyası

- Tarih: 2026-09-30
- Durum: Kabul edildi (kullanıcı kararı: "GUI için UI tasarım dosyalarını da
  istiyorum, yeri geldiğinde editleyebileyim" · "arayüzü modüler kur, her
  modülün ui dosyası olsun")

## Karar

1. Arayüz modüllere bölünür; her modül bir klasördür:
   ```
   ui/modules/<modul>/<modul>.ui   yerleşim + görünüm (Qt Designer'da düzenlenir)
   ui/modules/<modul>/<modul>.py   davranış: sinyaller, veri bağlama
   ```
   Mevcut modüller: `main_window`, `diagram` (`diagram_panel`), `adapter_list`,
   `inspector`.
2. `.ui` dosyaları **çalışma anında** `uic.loadUi` ile yüklenir
   (`ui/uiloader.py::load_ui`). `pyuic5` ile `.py` üretilmez: Designer'da
   kaydetmek yeterlidir, derleme adımı yoktur, üretilmiş kod elle
   düzenlenip ezilmez.
3. Modüller ana pencereye **promote edilmiş widget** olarak yerleşir
   (`main_window.ui` → `<customwidget><header>networkplus.ui.modules.…</header>`).
   Her modül kendi `.ui`'sini kendi `__init__`'inde yükler.
4. Özel çizim yapan tuval (`DiagramView`, `QGraphicsView`'den) de
   `diagram_panel.ui` içinde promote edilir: konumu/boyutu Designer'dan,
   çizimi koddan gelir. Düğüm/kenar çizimi (`items.py`) `.ui` ile ifade
   edilemez, kodda kalır.
5. `.py` kodu `.ui` nesnelerine `objectName` ile erişir ve açılışta
   `require(self, ...)` ile bunların varlığını denetler. Designer'da ad
   değişirse uygulama "şu ad eksik" diye açıkça hata verir;
   `tests/test_ui_smoke.py` bunu testte yakalar.

## Gerekçe

- Kullanıcı yerleşimi kendisi düzenlemek istiyor; çalışma anında yükleme
  "düzenle → kaydet → çalıştır" döngüsünü en kısa tutar.
- Modül başına `.ui` dosyaları çakışmayı azaltır ve her paneli Designer'da
  tek başına açılabilir kılar.

## Sonuçlar / kurallar

- Yeni arayüz modülü = yeni klasör + `.ui` + `.py`; duman testi her modül
  klasöründe `.ui` olduğunu denetler.
- `.ui` içinde sinyal-yuva bağlantısı yalnız basit durumlarda (ör. Çıkış →
  `close()`); iş mantığı `.py`'de.
- Metinler `.ui`'da Türkçe yazılır (kaynak dil). Çeviri eklendiğinde Qt
  Linguist `.ts` akışı değerlendirilir (TODO).
- Paketlemede (PyInstaller) `.ui` dosyaları veri dosyası olarak eklenmelidir.
- Designer `.ui`'yi kaydederken biçimi yeniden düzenler; bu beklenen bir
  durumdur, diff'te görünür.
