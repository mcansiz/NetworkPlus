# 10 — Çalışma Kuralları

## Dil

- Kullanıcıyla iletişim **Türkçe**.
- Dokümantasyon (`.md`) Türkçe, doğru Türkçe yazımıyla.
- Arayüz metni Türkçe (kaynak dil); ileride çeviri için `tr("...")` ile sarılır.
- Tanımlayıcı adları (değişken, fonksiyon, sınıf) ve commit mesajları **İngilizce**.
- Kod içi yorum ve docstring Türkçe olabilir.

## Geri Alınamaz / Dışa Dönük İşlemler

Aşağıdakiler kullanıcıya sorulmadan **yapılmaz**:

- Ana makinede ağ durumunu değiştiren **her komut** (bkz. `20-guvenlik-ve-test.md`).
- Paket kurulumu (`pip install`), sistem hizmeti başlatma/durdurma.
- Dosya silme, toplu yeniden adlandırma.
- `git commit` / `git push` (kullanıcı istemedikçe).

## Sürüm Yönetimi

- Depo: **Git**, `main` dalı. Uzak depo **herkese açık**: https://github.com/mcansiz/NetworkPlus
  (2026-10-01, kullanıcı kararı). Commit e-postası depoya özel ayarlı (kişisel adres).
- Depo herkese açık olduğu için depoya **girmez**: konuşma dökümleri (`.claude/sessions/`),
  yerel bağlantı bilgileri (`.claude/local/`: VM parolası, yollar), gerçek ağ bilgileri.
  Fixture'lar ve günlükler anonim adres kullanır (ofis LAN → 10.20.30.x). Şirket içi proje
  yolları/adları yazılmaz. Her push'tan önce `git diff --cached` gözden geçirilir.

## Geçici ve Test Dosyaları (kullanıcı kuralı, 2026-09-30)

**Test için kullanılan her şey proje yolunda durur; Windows `%TEMP%` ve Claude'un
oturum scratchpad'i KULLANILMAZ** ("test için kullanılan her şey bu yolda olsun, win
TEMP kullanma").

| Yol (git'e girmez) | İçerik |
|---|---|
| `.tmp/test/` | birim/duman testi çıktıları |
| `.tmp/shots/` | ekran görüntüleri (`main.py --screenshot`) |
| `.tmp/apply/` | Uygula işinin betik + sonuç dosyaları (`paths.new_job_dir`) |
| `.tmp/work/` | tek seferlik yardımcı betikler, geçici çıktılar |

- Kodda yol `networkplus/paths.py` (`work_dir`, `new_job_dir`) üzerinden alınır;
  `tempfile.gettempdir()` / `%TEMP%` doğrudan kullanılmaz.
- Kabuk komutlarında da `$TEMP` yerine `.tmp/...` yazılır.
- Paketlenmiş uygulamada proje klasörü olmadığından `%LOCALAPPDATA%\networkPlus`.
- Saklanacak ölçüm/deneme çıktısı `.claude/logs/` altına `.md` olarak konur.

## Bağımlılık İlkesi

- Çalışma zamanı bağımlılığı **yalnızca PyQt5**. Windows API'lerine
  PowerShell (her Windows'ta var) ve `ctypes` ile erişilir.
- `pywin32`, `wmi`, `comtypes` gibi paketler **eklenmez** — bu makinede kurulu
  değiller (2026-09-30) ve PowerShell aynı işi görüyor. Eklemek gerekirse
  önce ADR yazılır.
- Geliştirme araçları (test, paketleme: PyInstaller) bu kuralın dışındadır.
