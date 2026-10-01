# ADR 0009 — Değişiklikler doğrudan uygulanır; onay penceresi yok (ADR 0003'ü günceller)

- Tarih: 2026-09-30
- Durum: Uygulandı
- Kullanıcı: "Uygulama formuna gerek var mı, sürekli onay istiyor; amacımız hızlı ayar
  yapmak, kaldıralım, işlemler direkt uygulansın; başka problemlere yol açarsa öneri ver."
  · "Açılışta yönetici yetkisi isteyelim." (direkt UAC, sorusuz)

## Karar
1. **Varsayılan: doğrudan uygulama.** Inspector "Uygula", kart üstü ⏻, sağ tık, sürükle-bağla,
   tepsi → pencere açmadan `MainWindow.apply_now` → `ui/apply_runner.py::ApplyRunner`
   (arka plan iş parçacığı). Doğrulama hatası varsa uygulanmaz, şeritte gösterilir.
2. **Riskli değişiklikte ince şerit** (`ui/modules/confirm_bar`): internet taşıyan karta
   dokunan / bağlı kartı kapatan / paylaşım-köprü değişikliklerinde diyagramın üstünde
   "Uygulandı · 30 sn · Koru / Geri al". Pencere değil, çalışmayı engellemez; karar
   gelmezse betik kendisi geri alır. **Ayarlar › Riskli değişiklikte 30 sn geri alma
   süresi** ile kapatılabilir (varsayılan açık).
3. Adım başarısız olursa şerit hata + "Geri al" (başarılı adımların geri alma planı yeni
   bir iş olarak uygulanır).
4. **Açılışta doğrudan UAC** (`app.py`, Windows, `--tray` hariç): reddedilirse normal
   yetkiyle devam. Ayarlar › "Açılışta yönetici yetkisi iste" (varsayılan açık). Yönetici
   görevi kuruluysa UAC hiç çıkmaz. Yönetici olarak çalışınca Uygula hiç sormaz.
5. **Toplu düzenleme** isteğe bağlı (Ayarlar › Toplu düzenleme, varsayılan kapalı): eski
   kuyruk + "Planı ve betiği göster…" (ApplyDialog) bu kipte durur.

## Neden onay tamamen kaldırılmadı (kullanıcıya öneri)
- İnternet taşıyan karta yanlış IP / uzak masaüstündeyken kartı kapatmak = makineye
  erişim kaybı; geri alacak kimse kalmaz. 30 sn şerit bunu engeller, diğer tüm
  işlemler sorusuz ve anında.
- UAC her işlemde çıkar → çözüm açılışta yönetici yetkisi (4).

## Sonuçlar
- Kapanışta süren iş: `ApplyRunner.shutdown()` → geri al kararı + iş parçacığı beklenir;
  yenileme iş parçacığı da sonuna kadar beklenir (yoksa süreç çöküyordu — testte yakalandı).
- `show_window()` artık `showNormal()` çağırmaz (tam ekranı bozuyordu).
