# ADR 0011 — QSS ile açık ve koyu tema

- Tarih: 2026-10-01
- Durum: Uygulandı
- Kullanıcı: "projeye qss formatında koyu ve açık tema ekleyelim".

## Bağlam
Arayüz o güne kadar sistemin Qt görünümünü kullanıyordu (stil sayfası yok). Qt5,
Windows'un koyu modunu izlemez. Diyagram `QPainter` ile **paletten** çizilir
(`theme.palette_color`); QSS ise paleti **değiştirmez**. Yalnız QSS ile koyu tema,
koyu paneller içinde beyaz bir diyagram verirdi.

## Karar
1. Temalar `src/networkplus/ui/themes/*.qss`. Dosya = menüde tema (diller gibi). Kullanıcı
   düzenleyebilir ya da yeni `.qss` ekleyebilir.
2. Her `.qss`'in baş yorumunda `@name:` ve `@palette <rol>: <renk>` (isteğe bağlı
   `disabled <rol>`) satırları. Yükleyici paleti buradan kurar; tema tek dosyada kalır.
3. Tema uygulanınca stil **Fusion** olur (paleti ve QSS'i en tutarlı uygulayan stil),
   sonra palet, sonra stil sayfası. "Sistem görünümü" eski davranıştır: yerel stil +
   standart palet, stil sayfası yok.
4. Ayar `ui/theme`: `auto` (varsayılan; işletim sisteminin açık/koyu tercihi), `system`,
   ya da tema kodu. İşletim sistemi tercihi `platform.system_prefers_dark()` ile okunur
   (salt okunur): Windows kayıt defteri `AppsUseLightTheme`, Linux `gsettings`.
5. Tema çalışırken değişir (yeniden başlatma yok): uygula → lejant + diyagram yeniden kurulur.

## Sonuçlar
- QSS'te `QSpinBox`/`QComboBox`'a kenarlık **verilmez**: ok düğmeleri çizilmiyordu
  (ölçüldü); Fusion bunları paletle uyumlu çizer.
- Anlamlı sabit renkler (durum yeşil/sarı/kırmızı, ilişki renkleri) iki temada da aynıdır.
- Koyu modda olan Windows'ta (geliştirme makinesi, ölçüldü 2026-10-01) varsayılan açılış koyu temadır.
- Test: `tests/test_themes.py` (palet rolleri eksiksiz, QSS Qt uyarısı vermeden ayrışır,
  çözümleme, canlı geçiş, kullanıcı teması menüye düşer).
