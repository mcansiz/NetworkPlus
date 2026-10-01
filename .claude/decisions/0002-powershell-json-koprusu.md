# ADR 0002 — Windows'a PowerShell (5.1) JSON köprüsüyle erişim

- Tarih: 2026-09-30
- Durum: Önerildi

## Bağlam

Okunacak bilgi çok dağınık: NetAdapter/NetTCPIP/DnsClient CIM sınıfları,
HNetCfg COM (ICS), WinRT (hotspot), Hyper-V. Değiştirme de aynı cmdlet
ailesiyle yapılıyor. Makinede yalnızca **Windows PowerShell 5.1** var
(`pwsh` yok — ölçüldü); `pywin32`/`wmi`/`comtypes` kurulu değil.

## Karar

- Okuma ve yazma **PowerShell betikleri** (`platform/windows/ps/*.ps1`)
  üzerinden yapılır; çıktı yalnızca UTF-8 JSON.
- Anlık görüntü **tek betik, tek süreç** ile alınır.
- Canlı güncelleme için süreç her seferinde açılmaz: bir **kalıcı PowerShell
  süreci** (stdin'den komut, stdout'a satır başına JSON) worker thread'de tutulur.
- Hızlı ve sık gereken tek şey — "bir şey değişti mi?" — `ctypes` ile
  iphlpapi bildirimlerinden gelir (PowerShell'e gerek yok).

## Gerekçe

- Değiştirme işlemleri zaten PowerShell cmdlet'leriyle yapılacak; okuma da
  aynı yerden gelirse tek bir veri sözlüğü ve tek bir test yüzeyi olur.
- Ek Python bağımlılığı yok (kural: yalnız PyQt5).
- Betikler kullanıcıya **plan önizlemesinde** gösterilebilir: ne yapılacağı
  şeffaf, kopyalanıp elle de çalıştırılabilir.

## Sonuçlar

- Süreç açılışı pahalı (~0.6 sn tek cmdlet). Kalıcı süreç bunu açılışa indirir.
- PS 5.1 kısıtları: `ConvertTo-Json` enum'ları sayı yazar, tek elemanı dizi
  yapmaz, varsayılan derinlik 2 → kurallar `ai_rules/40` içinde.
- Kurumsal makinelerde `ExecutionPolicy` / AppLocker betikleri engelleyebilir →
  `-ExecutionPolicy Bypass` + betik metnini `-EncodedCommand` ile geçirme
  seçeneği. TODO: kurumsal kısıtlı makinede dene.
