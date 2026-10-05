> [!WARNING]
> **Pre-release.** networkPlus changes network settings. Keep another way to reach the machine if you work remotely; risky changes roll back automatically unless you confirm them.

## Download

| Platform | File | Notes |
|---|---|---|
| **Windows 10/11 (64-bit)** | `networkPlus-{VERSION}-windows-x64.exe` | Single portable file. Reading the network needs no admin rights; applying changes asks once (UAC). Not code-signed: SmartScreen → **More info → Run anyway**. |
| **Linux (64-bit, NetworkManager)** | `networkPlus-{VERSION}-x86_64.AppImage` | `chmod +x` and run; Python and Qt are inside. Needs glibc 2.17+, `nmcli` and `pkexec` (policykit-1). Without FUSE: `--appimage-extract-and-run`. |
{MACOS_ROW}

Running from source works everywhere: see the [README](https://github.com/{REPO}#run-from-source). Checksums: `SHA256SUMS`.

Built and tested automatically by GitHub Actions from tag `{TAG}` ([run]({RUN_URL})).

## Türkçe

- **Windows:** `networkPlus-{VERSION}-windows-x64.exe` — taşınabilir tek dosya; ağı okumak yönetici yetkisi istemez, değişiklik uygularken bir kez UAC sorar. İmzasız olduğu için SmartScreen'de **Ek bilgi → Yine de çalıştır**.
- **Linux:** `networkPlus-{VERSION}-x86_64.AppImage` — `chmod +x` ile çalıştırılabilir yapın; glibc 2.17+, `nmcli` ve `pkexec` gerekir. FUSE yoksa `--appimage-extract-and-run`.
{MACOS_TR}
