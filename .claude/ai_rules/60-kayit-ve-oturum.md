# 60 — Kayıt ve Oturum Geçmişi (ZORUNLU)

Yapılan **tüm işlemler, kararlar, ilerleme ve notlar** proje içindeki
`.claude/` klasörüne yazılır. Bu PC'nin lokaline (`~/.claude/...`, global
hafıza) proje bilgisi yazılmaz.

| Yol | İçerik |
|---|---|
| `.claude/ai_rules/` | Kalıcı kurallar (her oturumda yüklenir) |
| `.claude/docs/project-overview.md` | Amaç, kapsam, yol haritası |
| `.claude/docs/architecture.md` | Mimari, modüller, veri akışı |
| `.claude/docs/senaryo-analizi.md` | Ağ ilişki senaryoları ve tespit yöntemleri |
| `.claude/docs/benzer-uygulamalar.md` | Rakip/benzer uygulama araştırması |
| `.claude/docs/worklog.md` | Tarihli iş günlüğü — **her oturumda güncellenir** |
| `.claude/decisions/NNNN-*.md` | Teknik kararlar (ADR) |
| `.claude/specs/*.md` | Veri modeli, betik arayüzü spesifikasyonları |
| `.claude/logs/*.md` | Ölçüm ve hata ayıklama dökümleri |
| `.claude/sessions/` | Oturum transcript'leri (aşağıya bakın) |
| `.claude/memory/` | Claude otomatik hafızası (`MEMORY.md` + notlar) |
| `.claude/hooks/` | Kayıt otomasyonu betikleri |

## Oturum geçmişi nasıl projede tutulur

İki mekanizma birlikte çalışır:

1. **Canlı transcript'ler (session-persistence skill'i):**
   `~/.claude/projects/d--pythonProjeler-networkPlus/` klasörü
   `.claude/sessions/d--pythonProjeler-networkPlus/` içine taşınır, yerine
   **junction** bırakılır. Claude Code hiçbir şey değişmemiş gibi yazar ama
   dosyalar artık projede kalıcı durur (30 gün silmesinden korunur). Depo herkese
   açık olduğu için **Git'e girmez** (`.gitignore`: `.claude/sessions/`); makineler
   arası taşınmaz.
   - Kurulum/denetim (Claude Code **kapalıyken**, **proje dizininden** —
     script proje dizinini çalışma dizininden alır):
     ```
     cd /d D:\pythonProjeler\networkPlus
     python %USERPROFILE%\.claude\skills\session-persistence\scripts\setup_sessions.py [--dry-run|--check]
     ```
     2026-09-30'da kullanıcı klasöründen çalıştırıldı; açık Claude
     Code'u görüp hiçbir şey yapmadan durdu. VS Code eklentisi de "açık
     Claude Code" sayılır → VS Code kapatılıp düz `cmd`'den çalıştırılır.
   - **Neden kapalıyken:** klasör taşınırken açık oturum onu hemen yeniden
     oluşturur, transcript ikiye bölünür.
   - Repo başka bir yola klonlanırsa slug değişir; script durumu bildirir.
   - **Makine başına BİR KEZ** yapılır; junction kalıcıdır, sonraki oturumlar
     kendiliğinden projeye yazar. Yeniden gerekmesi: başka makine / başka yola klon.
   - `SessionStart` kancası (`.claude/hooks/check-sessions.py`) bağlantı yoksa
     Claude'a hatırlatma yazar; Claude kullanıcıya komutu söyler. Bağlıysa sessizdir.
2. **Arşiv kopyası (SessionEnd kancası):** `.claude/settings.json` →
   `.claude/hooks/archive-session.py` her oturum sonunda dökümü
   `.claude/sessions/<tarih>-<id>.jsonl` olarak kopyalar ve `INDEX.md`'yi günceller.
   Arşiv kopyaları `.gitignore`'dadır (aynı veri iki kez depoya girmesin).

## Ayarlar

- `.claude/settings.json` (depoda): `cleanupPeriodDays: 36500` — Claude Code
  varsayılanı 30 gündür ve eski transcript'leri **siler**; global ayar başka
  makineye taşınmadığı için proje ayarına yazılır.
- `.claude/settings.local.json` (depoda değil): `autoMemoryDirectory` hafızayı
  `.claude/memory/` içine yönlendirir. Yol mutlaktır; depo başka yola
  klonlanırsa yeniden yazılır.
- `.gitattributes`: `.claude/sessions/** -text -diff` — CRLF çevrimi canlı
  yazılan JSONL'i bozar.
- `.gitignore`: `.claude/sessions/` ve `.claude/local/` **tamamen** yok sayılır (depo
  herkese açık, 2026-10-01). Bu satırlar kaldırılmaz.

## Güvenlik

Transcript konuşmanın tamamıdır: IP, MAC, SSID, iç ağ adresleri, varsa
parolalar. **Depo herkese açık (2026-10-01):** `.claude/sessions/` tamamen `.gitignore`'dadır;
transcript'ler yalnız bu makinede kalır, depoya **asla** girmez. Wi-Fi parolası gibi gizli bilgiler
sohbete yapıştırılmaz.
