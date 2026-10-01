# ADR 0007 — Sistem tepsisi, sistemle başlatma, açılışta UAC'siz yönetici

- Tarih: 2026-09-30
- Durum: Uygulandı (Windows'ta gerçek görev kurulumu kullanıcı denemesi bekliyor)
- Kullanıcı: "uygulama sistem tepsisinde başlatılsın, küçültünce tepside olsun, sistemle
  açılabilsin; kullanıcı yetkisini açılışta otomatik aldıramıyor muyuz?"

## Karar
1. **Tepsi** (`ui/tray.py`): durum simgesi (internet çıkışının türü + renk), menü
   `main_window.ui::menuTray` (Designer'da düzenlenir) + kodda eklenen durum satırı ve
   "Bağdaştırıcılar" alt menüsü (etkinleştir/devre dışı, DHCP yenile, özellikler).
   Küçültünce ve (ayar açıksa) kapatınca tepsiye. Çıkış: tepsi › "networkPlus'tan çık" / Ctrl+Q.
2. **Bildirimler**: internet kesildi/geldi/çıkış değişti, bağdaştırıcı bağlandı/koptu
   (`tray.diff_notifications`); açıksa arka planda 60 sn'de bir okuma.
3. **Sistemle başlat** (Ayarlar ve tepsi): Kapalı / Normal (HKCU Run) / **Yönetici**.
   Yönetici = Görev Zamanlayıcı, `RunLevel Highest`, `-AtLogOn` (+10 sn), pilde de,
   süre sınırsız, tek kopya. Kurmak **bir kez** UAC ister.
4. **Elle açılışta da UAC'siz yönetici**: görev kuruluysa ve süreç yetkisizse `app.py`
   görevi tetikler (`schtasks /Run`) ve çıkar; yeni (yönetici) kopyaya tek-kopya
   borusundan "göster" gönderir. `--no-elevate` ile kapatılır.
5. **Tek kopya** (`ui/single_instance.py`, QLocalServer, WorldAccess): ikinci açılış
   çalışan kopyayı öne getirir. Dosya görüntüleme / ekran görüntüsü kiplerinde kapalı.
6. Linux: XDG autostart; yönetici kipi YOK (GUI'yi kök çalıştırmak güvensiz; pkexec sürer).

## Neden
- Run anahtarıyla yüksek yetki her açılışta UAC sorar; UAC'siz yüksek yetkinin
  desteklenen yolu Görev Zamanlayıcı'dır.
- `schtasks /Create` varsayılanları dizüstünde pilde başlatmaz ve 3 günde durdurur →
  PowerShell `New-ScheduledTaskSettingsSet` ile açıkça ayarlanır.

## Sonuçlar / riskler
- Yönetici kipinde ağ ayarları UAC sormadan değişir; kullanıcıya kurulurken açıkça
  söylenir. Plan/geri alma/koru korumaları aynen çalışır.
- Yükseltilmiş kopya ile yetkisiz ikinci açılış arasında boru erişimi WorldAccess ile.
- Doğrulanmayan: görev kurulumu ve `schtasks /Run` ile yükseltme (Claude'un kabuğu zaten
  yönetici, ayrıca ana makinede sistem ayarı kurmuyoruz) → kullanıcı denemesi.
