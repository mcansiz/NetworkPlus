# ADR 0008 — Dil desteği: Qt .ts dosyaları, çalışma anında okunur

- Tarih: 2026-09-30
- Durum: Uygulandı (Türkçe kaynak + İngilizce tam). 2026-10-01: Almanca (`de`), Rusça (`ru`),
  İspanyolca (`es`), Fransızca (`fr`), Basitleştirilmiş Çince (`zh_CN`) eklendi — kullanıcı seçti.
  Bu beş dil yapay zekâ çevirisidir (yer tutucu/hızlandırıcı denetimi geçti); açık kaynak sürümden
  önce **ana dili konuşan biri gözden geçirmeli**. Çince dosya `zh_CN` (sistem yereli ve Qt'nin
  `qtbase_zh_CN` çevirisiyle eşleşir).
- Kullanıcı: "projeye dil seçeneği de ekleyelim, ileriye dönük dil eklemeleri de
  yapılabilsin" · "işletim dili neyse onu açsın, yoksa İngilizce".

## Karar
1. **Kaynak dil Türkçe.** Çeviriler `src/networkplus/i18n/<kod>.ts` (Qt Linguist biçimi).
2. `.ts` dosyası **çalışma anında doğrudan okunur** (`TsTranslator`, `QTranslator.translate`
   Python'dan ezildi); `lrelease`/`.qm` derleme adımı yok.
3. **Dil seçimi:** Ayarlar › Dil = "Otomatik" ise işletim sistemi dili destekleniyorsa o,
   yoksa **İngilizce**. Elle seçim `QSettings ui/language`; değişiklik yeniden başlatınca
   geçerli ("Şimdi yeniden başlat" sunulur). `NETWORKPLUS_LANG` ortam değişkeni önceliklidir.
4. Metin kaynakları:
   - `.ui`: uic `QCoreApplication.translate(<sınıf adı>, metin)` ile çevirir (bağlam = `<class>`).
   - Python: `core/i18n.py::tr("...")` (bağlam `networkplus`); modül düzeyindeki sabitler
     `N_("...")` ile işaretlenip gösterirken `tr()` edilir. `core/` Qt'siz kalır: çevirmen
     kanca ile bağlanır.
   - Değişkenli metinler **yer tutuculu**: `tr("{name}: MTU {mtu}").format(...)` —
     çevirmen sırayı değiştirebilir. f-string içinde çevrilmez.
5. **Yeni dil:** `python tools/i18n_update.py --new de` → `de.ts`'yi Qt Linguist ile çevir
   (`@meta/LANGUAGE_NAME` = dilin kendi adı) → menüde kendiliğinden görünür. Kod değişmez.
6. Qt'nin kendi metinleri (Evet/Hayır...) PyQt5 ile gelen `qtbase_<dil>.qm` ile.
7. **Sözde dil `qps`**: tüm metinleri `[!…!]` yapar (yer tutucu/HTML korunur).

## Denetimler (tests/test_i18n.py)
- Her `.ts` eksiksiz ve yer tutucular kaynakla aynı (`i18n_update.py --check`).
- Koddaki her metin `.ts`'de (kod değişip `.ts` güncellenmezse test kırılır).
- Kodda `tr()`/`N_()` dışında Türkçe harfli metin yok (`i18n_find_untranslated.py`;
  bilerek çevrilmeyen satır `# notr`).
- Sözde dilde ana pencerede her statik metin çeviriden geçiyor — Türkçe harfi olmayan
  unutulmuş metinleri de yakalar.

## Sonuçlar
- Metin artık karar girdisi olamaz (ör. kenar "internet yok" etiketi yerine `Edge.dim`).
- Arayüz metni eklerken: `.ui`'da yaz (otomatik) ya da `.py`'de `tr()`; sonra
  `python tools/i18n_update.py` ve çeviri. Test eksik çeviriyi yakalar.
- Qt Linguist: `C:\Qt\5.15.2\msvc2019_64\bin\linguist.exe`.
