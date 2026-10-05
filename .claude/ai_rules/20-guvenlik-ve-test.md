# 20 — Güvenlik ve Test (ZORUNLU)

## Ana makinenin ağına dokunulmaz

Bu makinede Claude Code **yönetici yetkisiyle** çalışıyor (ölçüldü
2026-09-30: `IsInRole('Administrators') = True`). Yani yanlışlıkla çalıştırılan
tek bir `Set-NetIPAddress`, `Disable-NetAdapter` veya `EnableSharing` komutu
**UAC sormadan** ana makinenin ağını değiştirir: kurumsal Wi-Fi (domain) kopar,
Radmin VPN / VMware ağları bozulur, uzak oturum düşer.

Bu yüzden:

1. Ana makinede yalnızca **salt okunur** komutlar çalıştırılır:
   `Get-*`, `netsh ... show`, `ipconfig`, `route print`, `HNetCfg` okuma
   (`SharingEnabled`, `SharingConnectionType`).
2. Değiştiren komutlar (`Set-*`, `New-*`, `Remove-*`, `Enable-*`, `Disable-*`,
   `Rename-*`, `Restart-NetAdapter`, `netsh ... set/add/delete`,
   `EnableSharing`/`DisableSharing`, `Start/Stop-Service SharedAccess`)
   ana makinede **çalıştırılmaz** — kullanıcı açıkça "bu makinede dene"
   demedikçe. Derse bile önce geri alma komutu hazırlanır ve gösterilir.
3. Uygulamanın "Uygula" yolunu test eden her deneme **sanal makinede** yapılır.

## Test Ortamı

**Windows VM kullanılmaz** (kullanıcı kararı 2026-09-30). Test VM'i
**Linux Mint 22.3** (ADR 0005):

| | |
|---|---|
| VM | VMware Player. vmx yolu, SSH kullanıcı/parola ve yedek: **`.claude/local/vm.md`** (yerel; depo herkese açık olduğu için depoya girmez) |
| Bağlantı | SSH; ana makinede `sshpass` yok → PuTTY `plink -batch -ssh`, kopyalama `pscp` |
| Ağ | `ens33` = NAT, SSH buradan (**asla değiştirilmez**). 2026-09-30'da eklendi: `ens37`+`ens38` = VMnet5, `ens39` = VMnet6 — ana makinede adaptörü olmayan **yalıtılmış** segmentler; köprü/paylaşım ana makineye ulaşamaz. İki üyeli köprü farklı segmentlerden kurulur (aynı segment = döngü) |
| Yazılım | Python 3.12.3 + PyQt5, NetworkManager 1.46, dnsmasq-base, pkexec |
| Yedek | NIC eklemeden önceki vmx yedeği (`.claude/local/vm.md`) |

**Bellek:** ana makine 15,7 GB; kullanıcının **win11** VM'i açıkken yalnız ~3,8 GB boş
kalıyor (ölçüldü 2026-09-30). Mint (8 GB) o durumda **düşük bellekle** açılır
(`memsize` 2048, `numvcpus` 2, `coresPerSocket` — VMware bunu da değiştirir) ve test
sonunda eski değerlere döndürülür. **Başka VM'lere dokunulmaz.** Olay: 2026-09-30
15:37'de win11 VM'i (Mint açıldıktan 6 dk sonra) VMware'in kapatma komutuyla
kapandı; Claude win11'e komut göndermedi (yalnız `vmrun start mint`, `list`), neden
belirsiz — kullanıcıya bildirildi.
VM işi bitince: `sudo systemctl poweroff`, VM'deki kök sahipli dosyalar (`__pycache__`)
silinir; testler `PYTHONDONTWRITEBYTECODE=1` ile koşar.

**Onay kuralı:** VM'i hazırlamak (açmak, dosya kopyalamak) serbesttir; ama
**yazılımın kendi testlerini VM'de çalıştırmadan önce kullanıcıdan onay alınır**
(kullanıcının DiskUltimate'te koyduğu kural, bu projeye de uygulanır).

| Katman | Nerede |
|---|---|
| `core/` birim testleri | Ana makine — **fixture JSON** ile, işletim sistemine dokunmadan |
| Arayüz duman testi | Ana makine — `QT_QPA_PLATFORM=offscreen` + fixture |
| Keşif (snapshot) | Ana makine (Windows) — salt okunur olduğu için serbest; Linux keşfi VM'de |
| Değişiklik (Linux) | **Mint VM** |
| GitHub Actions (ADR 0013) | Her push'ta Linux/Windows/macOS sanal makinelerinde yalnız fixture testleri + paketli program duman testi; ağ **değiştirilmez** |
| Değişiklik (Windows) | Test ortamı **yok**: betik üretimi birim testle doğrulanır; gerçek çalıştırma yalnız kullanıcının açık izniyle. "VM'de sınanmadı" diye yazılır |

- Gerçek makineden alınan anlık görüntüler `tests/fixtures/*.json` olarak
  saklanır; ilişki çıkarımı bunlarla test edilir. Fixture'a girmeden önce
  MAC/IP/SSID gibi kişisel veriler **anonimleştirilir**.
- Bir yetenek VM'de sınanamıyorsa bu **açıkça yazılır**, "test edildi" denmez.

## Uygula yolunu kim çalıştırır

- Claude, `WindowsApplyJob.run()`'ı ya da üretilen `apply.ps1`'i **ana makinede
  çalıştırmaz**; arayüz testleri `FakeJob` kullanır. Betik doğrulaması:
  birim testte metin olarak + `[Parser]::ParseFile` ile yalnız sözdizimi.
- Gerçek Windows denemesini **kullanıcı**, uygulamadaki Uygula düğmesiyle yapar.
  Kullanıcının bildirdiği sonuç `docs/testing.md`'ye yazılır (tarih + adımlar).

## Uygulamanın kendi güvenlik katmanları

> 2026-09-30 güncellemesi (ADR 0009): plan **penceresi** varsayılan akıştan kalktı;
> değişiklikler doğrudan uygulanır. Katman 2 yerine doğrulama hatası şeritte gösterilir;
> katman 4 yalnızca riskli değişiklikte, engellemeyen şerit olarak çalışır.

Uygulama kullanıcının makinesinde değişiklik yaparken şu katmanlar gevşetilmez
(gerekçe: `decisions/0003-bekleyen-degisiklik-kuyrugu.md`):

1. **Keşif yetki istemez.** Yetki yalnızca "Uygula" anında, parti başına bir
   kez istenir (UAC).
2. **Önce plan gösterilir:** Uygula penceresi her adımı, üreteceği komutu ve
   **bağlantıyı koparabilecek** adımları işaretli listeler.
3. **Geri alma anlık görüntüsü:** uygulamadan önce etkilenen bağdaştırıcıların
   durumu kaydedilir.
4. **Onayla ya da geri dön zamanlayıcısı:** bağlantıyı etkileyen bir değişiklikten
   sonra "Değişiklikleri koru" 30 sn içinde onaylanmazsa otomatik geri alınır
   (ekran çözünürlüğü değiştirme davranışı gibi).
5. Uygulamanın kendi bağlantısını taşıyan bağdaştırıcıyı (varsayılan rota)
   devre dışı bırakmak ayrıca uyarılır.
