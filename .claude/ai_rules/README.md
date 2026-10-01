# ai_rules — networkPlus AI Çalışma Kuralları

Bu klasör networkPlus üzerinde çalışan AI asistanının uyacağı kalıcı kuralları
ve proje bilgisini tutar. Dosyalar kökteki `CLAUDE.md` içinden `@` ile import
edilir, yani her oturumda otomatik yüklenir.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `00-proje-genel.md` | Ne yapıyoruz, kapsam, hedef platform, klasör yerleşimi |
| `10-calisma-kurallari.md` | Dil, iletişim, geri alınamaz işlemler, sürüm yönetimi |
| `20-guvenlik-ve-test.md` | **Ana makinenin ağına dokunmama** kuralı, VM test ortamı |
| `30-mimari-ve-kod.md` | Katmanlar, kod kuralları, bekleyen değişiklik kuyruğu |
| `40-windows-ag-api.md` | Hangi bilgi nereden okunur / nasıl değiştirilir, tuzaklar |
| `50-arayuz-diyagram.md` | Diyagram, düğüm/kenar türleri, renkler, etkileşim |
| `60-kayit-ve-oturum.md` | `.claude/` kayıt düzeni, oturum geçmişi kalıcılığı |

## Kural Ekleme

1. Yeni konu için `NN-konu-adi.md` oluştur (`NN` = sıra no, 10'ar artır).
2. Kökteki `CLAUDE.md` içine `@.claude/ai_rules/NN-konu-adi.md` satırını ekle.
3. Bu tabloya bir satır ekle.

## Yazım İlkeleri

- **Kısa ve buyurgan yaz.** "X yapılır", "Y yapılmaz". Anlatı değil kural.
- **Kuralın gerekçesini yaz.** Gerekçesiz kural yanlış yorumlanır; uzun
  gerekçe `decisions/` altına ADR olarak gider, buradan bağlantı verilir.
- **Doğrulanmamış bilgiyi kural yapma.** Emin olunmayanı `TODO:` ile işaretle.
  Ölçülen şey "ölçüldü (tarih)" diye yazılır.
- **Göreli tarih yazma.** "geçen hafta" değil, `2026-09-30` gibi mutlak tarih.
- **Kod tabanından okunabilen şeyi tekrarlama.** Buraya yalnızca koddan
  çıkarılamayan karar ve kısıtlar yazılır.
