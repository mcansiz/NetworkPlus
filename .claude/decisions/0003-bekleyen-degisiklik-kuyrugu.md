# ADR 0003 — Değişiklikler kuyruğa girer, tek "Uygula", onayla-ya-da-geri-dön

- Tarih: 2026-09-30
- Durum: **Uygulandı** (2026-09-30, M2 ilk sürüm)

## Bağlam

Ağ ayarı değişikliği yıkıcıdır: yanlış IP/ağ geçidi, devre dışı bırakılan
bağdaştırıcı veya ICS'in private tarafın IP'sini ezmesi bağlantıyı koparır;
uzak oturumdaysa kullanıcı makineye bir daha erişemez. Ayrıca her değişiklik
UAC ister; tıklama başına UAC kullanılamaz bir deneyimdir.

## Karar

1. Diyagramda veya inspector'da yapılan her düzenleme tipli bir **adım**
   olarak kuyruğa girer; sistem değişmez. Etkilenen düğüm kesikli çerçeveyle
   "bekliyor" gösterilir.
2. **Uygula** penceresi planı listeler: adım, üretilen komut, uyarılar
   (bağlantıyı koparabilir / IP üzerine yazılacak / ICS tek çift).
3. Uygulamadan önce etkilenen bağdaştırıcıların durumu **geri alma betiğine**
   dönüştürülür.
4. Tek UAC ile tüm plan çalışır; her adımın sonucu JSON olarak döner.
5. Bağlantıyı etkileyen adımlardan sonra **30 sn "Değişiklikleri koru?"**
   sayacı: onaylanmazsa geri alma betiği çalışır. Geri alma, uygulamanın
   yükseltilmiş yardımcı süreci içinde zamanlanır ki arayüz donsa bile çalışsın.

## Gerekçe

Kullanıcının DiskUltimate'te benimsediği model (bekleyen işlem kuyruğu + tek
Uygula) aynı risk sınıfı için işe yaradı. "Koru ya da geri dön" deseni Windows
ekran çözünürlüğü değişikliğinden tanıdık ve uzak makinede kilitlenmeyi önler.

## Uygulama notları (2026-09-30)

- Adımlar: `core/changes.py` (`ENABLED, IPV4, DNS4, METRIC, MTU, ICS, RENAME`);
  hedef + tür başına tek değişiklik, yeni düzenleme eskisinin yerini alır.
- Geri alma, değişiklik **öncesi** snapshot'tan üretilir (`rollback_for`); ICS'in
  ezdiği private IP de geri alma listesine girer.
- Betik: `platform/windows/apply.py::render_script`. Tek `.ps1`: uygula →
  `applied.json` → `keep.flag`/`revert.flag` için 30 sn bekle → karar yoksa
  **betik kendisi** geri alır → `final.json`. Dosya UTF-8 **BOM'lu** yazılır
  (PS 5.1 BOM'suz dosyayı ANSI okur; Türkçe ad bozulur).
- Arayüz: `inspector` formu → "Kuyruğa ekle"; diyagramda sürükle-bağla ve sağ
  tık menüsü; `changes_panel` modülü; `apply_dialog` modülü (plan, betik
  önizleme/kaydetme, geri sayım). Onay sırasında pencere kapatılamaz.
- Kayıtlı anlık görüntü açıkken Uygula engellidir (`platform.apply_support`):
  GUID'ler başka makineye ait olabilir.
- **Windows'ta gerçek çalıştırma doğrulanmadı** (test ortamı yok, ADR 0005).
  Betik yalnız PowerShell ayrıştırıcısıyla sözdizimi olarak ve birim testlerde
  metin olarak denetlendi; arayüz akışı sahte iş (FakeJob) ile test edildi.

## Sonuçlar

- `core/changes.py` her adım için: doğrulama, çakışma kontrolü, betik üretimi,
  ters işlem üretimi ister → birim testle doğrulanır.
- Kuyruk ve `QUndoStack` aynı kaynaktan beslenir.
