# networkPlus — Proje Belleği

Windows PC'nin ağ bağdaştırıcılarını **diyagram üzerinde görselleştiren** ve
bağdaştırıcıların **tüm ayarlarını** (IP/DHCP, DNS, ağ geçidi, metrik, MTU,
etkin/devre dışı, bağlamalar, ICS paylaşımı, köprü...) görsel olarak
yapılandıran masaüstü uygulaması. Diyagramda "Wi-Fi → Ethernet'e internet
paylaşıyor (ICS)" gibi ilişkiler **yol (kenar)** olarak görünür; kullanıcı iki
düğüm arasında yol çizerek ilişki kurabilir.

Bu dosya her oturumda otomatik yüklenir. Ayrıntılı kurallar
`.claude/ai_rules/` altındadır ve aşağıdan import edilir.

@.claude/ai_rules/00-proje-genel.md
@.claude/ai_rules/10-calisma-kurallari.md
@.claude/ai_rules/20-guvenlik-ve-test.md
@.claude/ai_rules/30-mimari-ve-kod.md
@.claude/ai_rules/40-windows-ag-api.md
@.claude/ai_rules/50-arayuz-diyagram.md
@.claude/ai_rules/60-kayit-ve-oturum.md

## Hızlı Referans

| Konu | Yol |
|---|---|
| Proje kökü | `D:\pythonProjeler\networkPlus` |
| AI kuralları | `.claude/ai_rules/` (bkz. `README.md`) |
| Proje özeti ve yol haritası | `.claude/docs/project-overview.md` |
| Mimari | `.claude/docs/architecture.md` |
| Senaryo / ilişki analizi | `.claude/docs/senaryo-analizi.md` |
| Benzer uygulama araştırması | `.claude/docs/benzer-uygulamalar.md` |
| Topoloji veri modeli | `.claude/specs/topology-model.md` |
| Teknik kararlar (ADR) | `.claude/decisions/` |
| Çeviriler | `src/networkplus/i18n/*.ts` (ADR 0008) |
| qtDHCPserver analizi | `.claude/docs/qtdhcpserver-analizi.md` |
| Paketleme (tek dosya) | `packaging/networkplus.spec`, `build_win.sh`, `build_linux.sh` (ADR 0012) |
| CI / sürüm (3 platform) | `.github/workflows/` (ci, tests, release), `build_appimage.sh`, `build_macos.sh` (ADR 0013) |
| İş günlüğü | `.claude/docs/worklog.md` |
| Oturum geçmişi | `.claude/sessions/` |

## Değişiklik Kaydı

Projeye dair koddan çıkarılamayan kalıcı bir bilgi öğrenildiğinde (karar,
kısıt, Windows davranışı, tuzak), ilgili `ai_rules/*.md` veya `decisions/`
dosyası **güncellenir** — sohbette bırakılmaz. Her anlamlı değişiklikten sonra
`.claude/docs/worklog.md` güncellenir.
