# 00 — Proje Geneli

## Ne yapıyoruz

**networkPlus**: PC'deki ağ bağdaştırıcılarının durumunu ve aralarındaki
ilişkileri (ICS paylaşımı, köprü, sanal anahtar, NAT, VPN tüneli, varsayılan
rota...) Creately / draw.io Cisco diyagramları gibi **düğüm-kenar diyagramında**
gösteren ve tüm bağdaştırıcı ayarlarını bu diyagram üzerinden yapan uygulama.

Üç temel iş:

1. **Keşif (salt okunur):** bağdaştırıcılar, IP/DNS/ağ geçidi, rotalar,
   bağlantı profili (İnternet var mı), ICS, köprü, Hyper-V/VMware/VirtualBox
   sanal ağları, VPN, hotspot. Yönetici yetkisi **istemez**.
2. **Görselleştirme:** İnternet bulutu → ağ geçidi/router → bağdaştırıcı →
   aşağı akış (ICS istemcileri, sanal makineler, hotspot) şeklinde katmanlı
   diyagram. İlişkiler etiketli kenar olarak çizilir.
3. **Yapılandırma:** düğüm seçilince yan panelde (inspector) tüm ayarlar;
   iki düğüm arasında yol çizmek bir ilişki önerir (ör. Wi-Fi → ETH = ICS aç).
   Değişiklikler **kuyruğa girer**, tek "Uygula" ile, tek UAC onayıyla yapılır.

## Kapsam

- Hedef platformlar: **Windows 10 / 11** (geliştirme makinesi Win10 Pro 19045)
  ve **Linux / NetworkManager** (test VM'i Mint 22.3). ADR 0005.
  macOS kapsam dışı.
- Lisans: **GPLv3, açık kaynak** (ADR 0001). Her yeni bağımlılık GPLv3 uyumlu olmalı.
- Kaynak dil **Türkçe** arayüz; kod adları İngilizce.
- Uzak cihaz yönetimi (router'a SSH/SNMP) **kapsam dışı**; router yalnızca
  ağ geçidi IP/MAC'i ve ARP komşuluğundan çıkarılan bir düğüm olarak çizilir.

Ayrıntılı özellik listesi ve yol haritası: `.claude/docs/project-overview.md`.

## Klasör Yerleşimi (hedef)

```
networkPlus/
  CLAUDE.md                 AI bellek girişi (bu kuralları import eder)
  main.py                   giriş noktası
  requirements.txt
  src/networkplus/
    core/                   saf Python, Qt import ETMEZ
      model.py              Topology / Node / Edge veri modeli
      discovery.py          anlık görüntü → model (analiz kuralları)
      relations.py          ilişki çıkarımı (ICS, köprü, NAT, rota...)
      changes.py            bekleyen değişiklik kuyruğu, PS betiği üretimi
    platform/               işletim sistemine dokunan TEK katman
      windows/              PowerShell köprüsü, elevation
        ps/                 .ps1 betikleri (snapshot.ps1, apply.ps1)
      linux/                ip -j + nmcli
      filesource.py         kayıtlı snapshot JSON'u yükler (test/demo)
    ui/                     PyQt5 (ADR 0006)
      modules/<modul>/      <modul>.ui (Designer) + <modul>.py (davranis)
      icons.py theme.py     QPainter ikonlari, anlamsal renkler
      uiloader.py worker.py .ui yukleyici, arka plan snapshot is parcacigi
  tools/capture_snapshot.py anonim fixture alma (salt okunur)
  tests/                    fixture JSON'larla çekirdek testleri
  .claude/                  AI kuralları, dokümanlar, ADR'ler, oturumlar
```
