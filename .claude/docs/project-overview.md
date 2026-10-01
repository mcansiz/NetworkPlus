# networkPlus — Proje Özeti ve Yol Haritası

Tarih: 2026-09-30 (proje başlangıcı).

## Amaç

Windows'ta ağ bağdaştırıcılarını ve **aralarındaki ilişkileri** tek bakışta
anlaşılır bir diyagramda göstermek ve tüm bağdaştırıcı ayarlarını bu diyagram
üzerinden, güvenli biçimde (plan → tek UAC → onayla ya da geri dön) yapmak.

## Neden (pazardaki boşluk)

ncpa.cpl her şeyi yapıyor ama ilişkileri göstermiyor; NetSetMan / Simple IP
Config form ve profil tabanlı; Win7 Network Map yalnız görüntülüyordu ve
kaldırıldı; topoloji araçları (LanTopoLog, NetCrunch) LAN'a bakıyor, host
içine değil. **Host içi ilişkileri (ICS, köprü, vSwitch, VPN varsayılan rota)
graf olarak gösterip graf üzerinden düzenleten bir araç yok.**
Ayrıntı: `benzer-uygulamalar.md`.

## Yol haritası

### M0 — Altyapı (bitti: 2026-09-30)
- [x] `.claude/` düzeni, `CLAUDE.md`, `ai_rules/`, ADR 0001–0004
- [x] Senaryo analizi, benzer uygulama araştırması, host anlık görüntüsü
- [x] Git deposu; oturum geçmişi kalıcılığı hazır (junction kurulumu Claude Code
      kapalıyken yapılacak — `ai_rules/60`)

### M1 — Salt okunur diyagram (MVP-1) — büyük kısmı bitti 2026-09-30
- [x] `snapshot.ps1` + Windows toplayıcı/normalizasyon (UTF-8 JSON, bölüm başına hata)
- [x] Linux toplayıcı/normalizasyon (`ip -j` + `nmcli`) — **VM'de doğrulanmadı**
- [x] `core/`: model, sınıflandırma, ilişki çıkarımı, rozetler, yerleşim + fixture testleri
- [x] Modüler arayüz, her modülün `.ui` dosyası (ADR 0006): liste, diyagram, inspector
- [x] Katmanlı yerleşim, durum renkleri, etkin yol (`Find-NetRoute`),
      ICS / hotspot / VM NAT / VPN tüneli / köprü / vSwitch kenarları, sorun rozetleri
- [x] Anlık görüntü aç/kaydet, PNG dışa aktarma, 30 sn otomatik yenileme
- [ ] Linux'u Mint VM'de doğrula, gerçek fixture al (kullanıcı onayı bekleniyor)
- [ ] Canlı güncelleme (iphlpapi bildirimleri + debounce) — şimdilik 30 sn yoklama
- [ ] Elle taşınan konumların diske kaydı (şimdilik oturum boyunca)
- [ ] SVG dışa aktarma

### M2 — Yapılandırma (MVP-2) — ilk sürüm 2026-09-30
- [x] `core/changes.py`: adım türleri, doğrulama, geri alma; Windows PS betiği
- [x] Uygula penceresi (plan, uyarılar, betik önizleme/kaydet), tek UAC, 30 sn koru/geri al
- [x] IPv4 DHCP/statik, DNS, metrik, MTU, etkin/devre dışı, yeniden adlandır
- [x] **ICS: sürükleyerek kur, sağ tıkla kapat** (tek çift kuralı, IP geri yükleme,
      reboot kalıcılığı)
- [ ] **Windows'ta gerçek deneme** — kullanıcı yapacak (sonuç `docs/testing.md`)
- [x] Linux uygulama (nmcli + pkexec/helper) — Mint VM'de 38/38
- [x] DHCP yenileme (Windows `ipconfig /renew`, Linux `con up`)
- [x] **Yerleşik DHCP sunucusu** (ADR 0010, qtDHCPserver'dan): panel, kiralar, rezervasyon,
      günlük, diyagramda istemciler — Linux VM'de canlı doğrulandı; Windows denemesi bekliyor
- [x] Ağ köprüsü kur/kaldır — **Linux**; Windows'ta yok (Win11 `netsh bridge` sonraki adım)
- [x] Kuyruk için geri al / yinele (`QUndoStack`, Ctrl+Z / Ctrl+Y)
- [ ] Linux masaüstünde pkexec penceresiyle deneme
- [ ] Metrik için Birincil/İkincil/Yedek dili; profiller (kaydet/uygula)

### M3 — v1
- [ ] Bağlamalar, advanced properties (MAC, VLAN, jumbo), IPv6, NetworkCategory
- [ ] Mobil Hotspot (WinRT), köprü (Win11 `netsh bridge`; Win10 yalnız görüntü)
- [ ] Hyper-V vSwitch / WinNAT / WSL görünümü, VPN split tunnel
- [ ] Tanılama menüsü (ping, traceroute, DNS), trafik sparkline'ı

### Sonra
Forwarding + `New-NetNat` yönlendirme, alt ağ tarama, LLDP/CDP, kural motoru,
CLI, draw.io dışa aktarma, çok dil.
