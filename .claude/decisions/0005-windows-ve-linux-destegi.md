# ADR 0005 — Windows + Linux (NetworkManager) desteği, test VM'i Linux Mint

- Tarih: 2026-09-30
- Durum: Kabul edildi (kullanıcı kararı: "VM Mint (Linux) kullan, Windows kullanma")

## Bağlam

İlk tasarım yalnız Windows'u hedefliyordu ve yazma testleri için Windows VM
öngörülmüştü. Kullanıcı test ortamı olarak **Linux Mint VM**'i seçti; Windows
VM kullanılmayacak. Ana makinede (Windows) yazma zaten yasak (`ai_rules/20`).

## Karar

1. Uygulama **iki platformda** çalışır: Windows 10/11 ve Linux
   (NetworkManager + iproute2; hedef Mint 22 / Ubuntu 24.04 ailesi).
2. Platform farkı `platform/<os>/` içinde kalır. Her toplayıcı (collector)
   **normalize edilmiş anlık görüntü** üretir (`specs/snapshot-schema.md`);
   `core/` platformdan habersizdir.
3. Linux'ta okuma `ip -j` (JSON) + `nmcli -t`; yazma `nmcli` ile.
   Kavram eşleşmesi:
   | Windows | Linux (NetworkManager) |
   |---|---|
   | ICS (public → private) | `ipv4.method shared` (private taraf); public = varsayılan rota |
   | Ağ köprüsü | `nmcli con add type bridge` + `bridge-slave` |
   | Mobil Hotspot | `nmcli dev wifi hotspot` |
   | InterfaceMetric | `ipv4.route-metric` |
   | Statik/DHCP | `ipv4.method manual/auto` |
4. **Yazma yolları Mint VM'de sınanır.** Windows yazma yolları için
   test ortamı yok: betik üretimi birim testle doğrulanır; gerçek çalıştırma
   yalnız kullanıcı açıkça izin verdiğinde ve kendi makinesinde yapılır.
   Bu durum her Windows yazma özelliğinde "VM'de sınanmadı" diye açıkça yazılır.
5. Bir de **dosya toplayıcısı** var: kayıtlı anlık görüntü JSON'unu yükler.
   Arayüz testleri ve demo bununla her platformda yapılır
   (`python main.py --snapshot tests/fixtures/win-host.json`).

## Gerekçe

- Test ortamı Linux ise Linux arka ucu olmadan VM'de sınanabilecek tek şey
  saf çekirdek olurdu; oysa asıl risk yazma yollarındadır.
- NetworkManager'ın device/connection modeli araştırmada en temiz veri modeli
  olarak öne çıktı (`docs/benzer-uygulamalar.md`); iki platformu aynı
  modele indirmek çekirdeği sadeleştirir.
- Kullanıcının DiskUltimate projesi de çapraz platform ve aynı VM'i kullanıyor.

## Durum (2026-09-30, akşam)

- Linux okuma: gerçek Mint çıktısıyla doğrulandı (`tests/fixtures/linux-mint.raw.json`).
- Linux yazma: `platform/linux/apply.py` + `helper.py`; Mint VM'de **38/38** canlı
  senaryo (ICS, DHCP yenileme, geri al, süre dolması, devre dışı, köprü kur/kaldır/geri al).
- Platform farkları `core/changes.py::SUPPORTED` tablosunda: Windows'ta köprü yok,
  Linux'ta yeniden adlandırma yok; desteklenmeyen tür doğrulamada hata verir.
- Sınanmayan: masaüstünde pkexec parola penceresi.

## Sonuçlar

- Snapshot şeması platformdan bağımsız tutulmalı; platforma özgü alanlar
  `extra` altında.
- Windows'a özgü ilişkiler (VMware NAT, Hyper-V) Linux'ta boş gelir; Linux'a
  özgü olanlar (veth, docker0, virbr0, tun/wireguard) sınıflandırmaya eklenir.
- Mint VM'de şu an tek NAT NIC var; ICS/köprü testleri için ikinci NIC
  eklenmesi gerekecek (VM yapılandırma değişikliği — kullanıcıya sorulur).
