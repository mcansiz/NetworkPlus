# Test Yöntemi ve Sonuçlar

## Otomatik testler (ana makine, işletim sistemine dokunmaz)

```bash
python -m unittest discover -s tests -v
```

| Dosya | Kapsam |
|---|---|
| `tests/test_core.py` | Normalizasyon, sınıflandırma, ilişkiler, rozetler, yerleşim (fixture) |
| `tests/test_changes.py` | Kuyruk, doğrulama, geri alma, PowerShell betiği **metni** |
| `tests/test_ui_smoke.py` | Tüm `.ui` yüklenir; ana pencere; M2 akışı **FakeJob** ile |

| `tests/test_linux_apply.py` | nmcli argv üretimi, köprü, DHCP yenileme, platform desteği (gerçek Mint fixture) |
| `tests/test_dhcp_core.py` | DHCP paket, havuz/kira, DORA, rezervasyon, NAK, DECLINE, kalıcılık |
| `tests/test_dhcp_ui.py` | Kart denetimi, diyagram katmanı, panel akışı (**FakeService**, sahte iş) |

Son durum (2026-09-30, DHCP sonrası): **106/106 geçti**, ardışık koşularda kararlı.
Çıktısız çökme olursa: `QT_FORCE_STDERR_LOGGING=1` ile Qt'nin fatal mesajı görünür.
Önceki durum: **59/59 geçti** — Windows ana makinede (Python 3.14) ve Mint VM'de (Python 3.12).
`test_ui_smoke` art arda 6 çalıştırmada kararlı (çöp toplama çökmesi giderildi, bkz. worklog).

## Linux'ta gerçek değişiklik denemesi (Mint VM, otomatik)

```bash
# VM'de, kök olarak (SSH'in geçtiği ens33'e dokunan her değişiklik betiği durdurur)
sudo PYTHONDONTWRITEBYTECODE=1 python3 tools/vm_apply_test.py [--only ics,renew,revert,timeout,disable,bridge,bridge_revert,ics_off]
```

| Tarih | Senaryo | Sonuç |
|---|---|---|
| 2026-09-30 | ICS (NM shared) ens37 → ens38 aynı segmentten 10.42.0.x aldı | ✔ |
| 2026-09-30 | DHCP yenileme (ens38) | ✔ |
| 2026-09-30 | Statik IP + DNS + metrik + MTU → **Geri al** → DHCP / otomatik MTU | ✔ |
| 2026-09-30 | Statik IP → onay yok (5 sn) → **kendiliğinden geri alındı** | ✔ |
| 2026-09-30 | Devre dışı → geri al | ✔ (ilk koşuda hata raporu; düzeltildi) |
| 2026-09-30 | Köprü ens38+ens39 → br-np0 ICS'ten DHCP aldı; diyagramda kenarlar; sonra kaldır | ✔ |
| 2026-09-30 | Köprü oluştur → **Geri al** → üyeler eski profillerine döndü, artık profil yok | ✔ |
| 2026-09-30 | ICS kapat; son durum başlangıçla aynı; SSH hiç kopmadı | ✔ |

Toplam **38/38**; döküm: `.claude/logs/2026-09-30-vm-linux-apply.md`.
**Sınanmayan:** masaüstündeki pkexec parola penceresi (SSH'te ajan yok). Yetkisiz
durumda anlamlı hata verdiği doğrulandı.

## DHCP sunucusu canlı denemesi (Mint VM, yalıtılmış VMnet5)

```bash
sudo PYTHONDONTWRITEBYTECODE=1 python3 tools/vm_dhcp_test.py                       # süreç düzeyi
sudo PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 tools/vm_dhcp_gui_test.py [--disconnect-first]
```

| Tarih | Senaryo | Sonuç |
|---|---|---|
| 2026-09-30 | Süreç: başla, 2. sunucu port çakışması (errno 98), istemci kira, rezervasyon, stdin kapanınca dur, kalıcılık | 10/10 |
| 2026-09-30 | Arayüz: panelden statik IP (onaysız) + başlat, istemci 10.50.0.100, diyagram "DHCP istemcileri (1)", bildirim, kapanınca süreç yok | 15/15 |
| 2026-09-30 | Arayüz, NM'nin bıraktığı kart: statik IP → etkinleştir → başlat | 16/16 |

Ana makinede DHCP sunucusu Claude tarafından ÇALIŞTIRILMAZ (kurumsal ağa sahte DHCP).

## Windows'ta gerçek değişiklik denemesi (kullanıcı yapar)

Claude ana makinede Uygula'yı çalıştırmaz (`ai_rules/20`). Önerilen ilk denemeler,
riski düşükten yükseğe:

1. **Geri alma denemesi:** `VMware Network Adapter VMnet1` → Genel → adını değiştir →
   Kuyruğa ekle → Uygula → UAC onayla → **Geri al**. Beklenen: ad eski hâline döner.
2. **Süre dolması:** aynısını yapıp hiçbir şeye basmadan 30 sn bekle. Beklenen: geri alınır.
3. **Kablosuz olmayan bağdaştırıcıda IP:** ETH (kablo takılı değil) → IPv4 → adresi
   değiştir → Uygula → Koru. Sonra eski adrese geri çevir.
4. **İnternet paylaşımı:** Wi-Fi'nin sağındaki noktadan ETH'ye sürükle → ICS →
   Uygula → Koru. ETH'nin adresi 192.168.1.1 olmalı (bu makinedeki ICS kapsamı).
   Kapatmak: ICS okuna sağ tık → "Bu paylaşımı kapat" → Uygula.

İnternet taşıyan bağdaştırıcıda (Wi-Fi) denemeyi en sona bırakın.

## Sonuç kaydı

| Tarih | Deneme | Sonuç | Not |
|---|---|---|---|
| 2026-09-30 16:02 | **ETH (kablosuz değil, bağlı değil) → DHCP** — kullanıcı, ana makinede | ✔ | UAC + betik + adım **3 sn** (06→09); kullanıcı 17 sn sonra "Koru"ya bastı. İş klasörü: `.tmp/apply/networkplus-apply-kz6ylx09/`. İlk gerçek Windows doğrulaması: `Start-Process -Verb RunAs`, BOM'lu betik, `applied.json`/`keep.flag`/`final.json` protokolü çalışıyor |

Kullanıcı geri bildirimi (aynı gün): "kuyruğa alma/onaylama süreci çok uzun" → düşük
riskli değişikliklerde onay beklemesi kaldırıldı (`core.changes.needs_confirmation`),
"Hemen uygula…" düğmesi, "Yönetici olarak yeniden başlat" / yönetici görevi eklendi.
