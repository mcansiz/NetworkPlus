# Mint VM — Linux uygulama yolu canli denemesi

Tarih: 2026-09-30. VM: Linux Mint 22.3, NetworkManager 1.46, Python 3.12.3.
Komut: `sudo python3 tools/vm_apply_test.py` (kok; pkexec yerine dogrudan helper).
Ag: ens33 = NAT/SSH (DOKUNULMADI), ens37+ens38 = VMnet5, ens39 = VMnet6 (ana makineye bagli olmayan yalitilmis segmentler).

**Sonuc: 38/38.** Ilk calistirmada 38/38 ama "devre disi -> geri al" adimi hata raporluyordu (DHCP sunucusu olmayan segmentte `nmcli device connect` IP beklerken takiliyor); `--wait 5` + uyari olarak duzeltildi, ikinci calistirma temiz.

```text
SSH/internet arayuzu: ens33 (ag gecidi 192.168.42.2) — dokunulmayacak

== ICS (NM shared): ens37 paylasir, ens38 ayni segmentten DHCP alir
    + İnternet paylaşımı: ens33 → ens37
    ↺ İnternet paylaşımını (ICS) kapat
    ↺ ens37: IPv4 adresini otomatik al (DHCP)
    ✔ İnternet paylaşımı: ens33 → ens37
    karar: keep
  [GECTI] ICS: adimlar basarili ve korundu
  [GECTI] ICS: ens37 = 10.42.0.1 — ['10.42.0.1']
  [GECTI] ICS: ens37 profili shared — shared
  [GECTI] ICS: ens38 paylasimdan DHCP adresi aldi — ['10.42.0.239']
  [GECTI] ICS: diyagramda ICS kenari
  [GECTI] ics: ens33 (SSH) hala calisiyor

== DHCP yenileme: ens38
    + ens38: DHCP adresini yenile
    ✔ ens38: DHCP adresini yenile
    karar: keep
  [GECTI] Yenile: adim basarili — [{'id': 1, 'title': 'ens38: DHCP adresini yenile', 'ok': True, 'error': None, 'warnings': []}]
  [GECTI] Yenile: geri alma adimi yok, beklemeden bitti
  [GECTI] Yenile: ens38 yine 10.42.0.x — ['10.42.0.239']
  [GECTI] renew: ens33 (SSH) hala calisiyor

== Statik IP + DNS + metrik + MTU, sonra GERI AL: ens39
    + ens39: statik IPv4 172.31.9.1/24, ağ geçidi yok
    + ens39: DNS 1.1.1.1
    + ens39: arayüz metriği 500
    + ens39: MTU 1400
    ↺ ens39: MTU otomatik
    ↺ ens39: arayüz metriği otomatik
    ↺ ens39: DNS sunucularını otomatik al
    ↺ ens39: IPv4 adresini otomatik al (DHCP)
    ✔ ens39: statik IPv4 172.31.9.1/24, ağ geçidi yok
    ✔ ens39: DNS 1.1.1.1
    ✔ ens39: arayüz metriği 500
    ✔ ens39: MTU 1400
    ↺✔ ens39: MTU otomatik
    ↺✔ ens39: arayüz metriği otomatik
    ↺✔ ens39: DNS sunucularını otomatik al
    ↺✔ ens39: IPv4 adresini otomatik al (DHCP)
    karar: revert
  [GECTI] Geri al: 4 adim uygulandi — [None, None, None, None]
  [GECTI] Geri al: karar revert
  [GECTI] Geri al: ens39 DHCP'ye, MTU otomatige dondu — method=auto ip=[]
  [GECTI] revert: ens33 (SSH) hala calisiyor

== Statik IP, onay VERILMEDI (5 sn): ens39
    + ens39: statik IPv4 172.31.9.1/24, ağ geçidi yok
    ↺ ens39: IPv4 adresini otomatik al (DHCP)
    ✔ ens39: statik IPv4 172.31.9.1/24, ağ geçidi yok
    ↺✔ ens39: IPv4 adresini otomatik al (DHCP)
    karar: timeout
  [GECTI] Sure dolmasi: karar timeout
  [GECTI] Sure dolmasi: kendiliginden geri alindi — method=auto ip=[]
  [GECTI] timeout: ens33 (SSH) hala calisiyor

== Devre disi birak, sonra geri al: ens39
    + ens39: devre dışı bırak
    ↺ ens39: etkinleştir
    ✔ ens39: devre dışı bırak
    ↺✔ ens39: etkinleştir
    karar: revert
  [GECTI] Devre disi: uygulandi
  [GECTI] Devre disi: geri alininca yeniden etkin — up / 70 (connecting (getting IP configuration))
  [GECTI] disable: ens33 (SSH) hala calisiyor

== Kopru: ens38 + ens39 -> br-np0 (IPv4 ens38'den: DHCP), koru; sonra kaldir
    + Köprü br-np0 oluştur: ens38, ens39 (IPv4 DHCP)
    ↺ Köprü br-np0 kaldır (üyeler: ens38, ens39)
    ✔ Köprü br-np0 oluştur: ens38, ens39 (IPv4 DHCP)
    karar: keep
  [GECTI] Kopru: adimlar basarili — [None]
  [GECTI] Kopru: br-np0 olustu (tur kopru)
  [GECTI] Kopru: uyeler ens38, ens39 — ['ens38', 'ens39']
  [GECTI] Kopru: br-np0 paylasimdan DHCP aldi (ens38 uzerinden) — ['10.42.0.144']
  [GECTI] Kopru: diyagramda kopru kenarlari

== Kopru kaldir (ileri yonde BRIDGE_DELETE), koru
    + Köprü br-np0 kaldır (üyeler: ens38, ens39)
    ↺ Köprü br-np0 oluştur: ens38, ens39 (IPv4 DHCP)
    ✔ Köprü br-np0 kaldır (üyeler: ens38, ens39)
    karar: keep
  [GECTI] Kopru kaldir: adimlar basarili — [None]
  [GECTI] Kopru kaldir: br-np0 yok
  [GECTI] Kopru kaldir: uyeler serbest
  [GECTI] bridge: ens33 (SSH) hala calisiyor

== Kopru olustur, sonra GERI AL
    + Köprü br-np0 oluştur: ens38, ens39 (IPv4 yok (yalnız L2))
    ↺ Köprü br-np0 kaldır (üyeler: ens38, ens39)
    ✔ Köprü br-np0 oluştur: ens38, ens39 (IPv4 yok (yalnız L2))
    ↺✔ Köprü br-np0 kaldır (üyeler: ens38, ens39)
    karar: revert
  [GECTI] Kopru geri al: olusturma basarili — [None]
  [GECTI] Kopru geri al: br-np0 silindi
  [GECTI] Kopru geri al: uyeler eski profillerine dondu — {'ens38': '9942b65d-e477-39a0-b047-2c29382de9e1', 'ens39': 'd4c7ec3d-372d-31a6-9a66-fa940c94ae82'}
  [GECTI] Kopru geri al: artik profil kalmadi — []
  [GECTI] bridge_revert: ens33 (SSH) hala calisiyor

== ICS kapat (ileri yon), koru
    + İnternet paylaşımını (ICS) kapat
    ↺ İnternet paylaşımı: ens33 → ens37
    ✔ İnternet paylaşımını (ICS) kapat
      (uyarı) nmcli --wait 30 connection…: Error: Timeout expired (30 seconds)
    karar: keep
  [GECTI] ICS kapat: adimlar basarili
  [GECTI] ICS kapat: ens37 profili auto — auto
  [GECTI] ics_off: ens33 (SSH) hala calisiyor
  [GECTI] Son durum: ens37-39 baslangictaki ipv4.method'a dondu — once={'ens37': 'auto', 'ens38': 'auto', 'ens39': 'auto'} sonra={'ens37': 'auto', 'ens38': 'auto', 'ens39': 'auto'}

SONUC: 38/38 gecti
```
