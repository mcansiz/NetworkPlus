# Mimari (taslak — 2026-09-30)

Kod henüz yazılmadı; bu belge hedef mimaridir. Kararlar: `decisions/0001–0004`.

## Veri akışı

```
          (yetkisiz)                         (saf Python)                  (PyQt5)
 snapshot.ps1 ──JSON──▶ platform.windows.bridge ──dict──▶ core.discovery ──Topology──▶ ui.diagram
                                                           core.relations                 │
                                                                                          │ kullanıcı düzenler
                                                                                          ▼
 apply.ps1 ◀──betik── platform.windows.elevate ◀── core.changes (kuyruk → plan → PS betiği)
  (UAC, tek sefer)            │
                              └─ sonuç JSON ──▶ yeniden snapshot ──▶ fark diyagramda gösterilir
```

## Modüller

| Modül | Sorumluluk |
|---|---|
| `platform/windows/ps/snapshot.ps1` | Tüm okuma cmdlet'leri tek betikte; her bölüm try/catch; UTF-8 JSON |
| `platform/windows/bridge.py` | PowerShell süreci yönetimi (kalıcı süreç + tek seferlik), zaman aşımı, JSON ayrıştırma |
| `platform/windows/watch.py` | Değişiklik bildirimi: `ctypes` ile `NotifyIpInterfaceChange` / `NotifyUnicastIpAddressChange` (iphlpapi) → debounce → yeniden snapshot |
| `platform/windows/elevate.py` | `ShellExecuteW(runas)` ile betiği yükseltilmiş çalıştırma, sonucu dosyadan okuma |
| `core/model.py` | `Topology`, `Node`, `Edge`, `NodeKind`, `EdgeKind` (spec: `specs/topology-model.md`) |
| `core/discovery.py` | Snapshot → düğümler (sınıflandırma: fiziksel/Wi-Fi/VPN/VM/gizli) |
| `core/relations.py` | İlişki çıkarımı: uplink, etkin rota, ICS, köprü, NAT, tünel, hotspot; sorun rozetleri |
| `core/changes.py` | Adım türleri, doğrulama, çakışma kontrolü (ICS tek çift), PS betiği üretimi, geri alma betiği |
| `core/profiles.py` | Ayar profilleri (NetSetMan tarzı), JSON |
| `ui/main_window.py` | Yerleşim, araç çubuğu, durum çubuğu |
| `ui/diagram/` | `QGraphicsScene`, düğüm/kenar öğeleri, sürükleyerek bağlama, otomatik yerleşim |
| `ui/inspector/` | Sekmeli ayar paneli |
| `ui/apply_dialog.py` | Plan önizleme + "koru/geri al" zamanlayıcısı |

## Yenileme stratejisi

1. Açılışta tam snapshot (~1–2 sn beklenen; ölçülecek).
2. iphlpapi bildirimi gelince 500 ms debounce → snapshot.
3. ICS/hotspot gibi bildirimi olmayan durumlar için 10 sn'de bir hafif yoklama.
4. Kullanıcı "Yenile" ile zorlayabilir.

## Yetki modeli

Uygulama **yükseltilmemiş** başlar. "Uygula" → plan betiği geçici dosyaya
yazılır → `runas` ile tek UAC → betik sonucu JSON'a yazar → uygulama okur.
(ADR 0004)
