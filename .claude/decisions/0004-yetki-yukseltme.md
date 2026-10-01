# ADR 0004 — Uygulama yükseltilmemiş çalışır, yetki yalnız Uygula'da istenir

- Tarih: 2026-09-30
- Durum: **Uygulandı** (2026-09-30)

## Bağlam

Tüm okuma işlemleri (ICS durumu dahil) yönetici olmadan çalışıyor (ölçüldü).
Yazma işlemleri yönetici ister.

## Karar

- Uygulama normal kullanıcı olarak açılır; manifest `asInvoker`.
- Uygula anında: plan betiği + geri alma betiği geçici dizine yazılır,
  `ShellExecuteW(None, "runas", "powershell.exe", ...)` ile **tek UAC**;
  sonuç `result.json` dosyasına yazılır, uygulama onu okur.
- Kullanıcı isterse "Yönetici olarak yeniden başlat" seçeneği vardır (sık
  değişiklik yapanlar için); varsayılan değildir.

## Gerekçe

En az yetki ilkesi: yalnızca bakmak isteyen kullanıcıdan UAC istenmez;
tüm uygulamayı yükseltmek sürükle-bırak (UIPI) ve dosya diyaloğu sorunları
da çıkarır.

## Sonuçlar

- Yükseltilmiş betik ile uygulama arasında dosya tabanlı IPC var; geçici
  dosyalar kullanıcıya özel dizinde ve işten sonra silinir.
- Betik metni imzalanmadığı için kurumsal kısıtlarda engellenebilir (ADR 0002).
