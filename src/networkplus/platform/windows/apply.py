"""Windows: degisiklik adimlari -> PowerShell betigi; tek UAC ile yukseltilmis calistirma.

Akis (ADR 0003, 0004):
  1. Uygulama betigi + geri alma adimlari tek .ps1 icinde uretilir (UTF-8 BOM:
     PS 5.1 BOM'suz dosyayi ANSI okur, Turkce adlar bozulur).
  2. Betik `Start-Process -Verb RunAs` ile tek UAC onayiyla calisir.
  3. Betik adimlari uygular, sonucu applied.json'a yazar, sonra keep.flag /
     revert.flag icin CONFIRM_SECONDS bekler. Karar gelmezse KENDISI geri alir;
     uygulama donsa ya da baglanti kopsa bile geri alma calisir.
  4. Sonuc final.json'a yazilir.

Betik metni `render_script` ile uretilir ve saf fonksiyondur (birim testli).
Bu makinede gercek calistirma yalnizca kullanicinin Uygula dugmesiyle olur;
gelistirme sirasinda calistirilmaz (ai_rules/20).
"""

from __future__ import annotations

import base64
import json
import re
import subprocess

import time
from pathlib import Path

from ...core.changes import Change, ChangeKind
from ...paths import new_job_dir
from ...core.i18n import tr

CONFIRM_SECONDS = 30
_GUID_RE = re.compile(r"^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$")
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_KEYWORD_RE = re.compile(r"^\*?[A-Za-z0-9_.\-]{1,64}$")     # surucu kayit anahtari (*JumboPacket)


class ScriptError(ValueError):
    """Betige cevrilemeyen (dogrulanmamis) adim."""


def ps(value) -> str:
    """PowerShell tek tirnakli metin (ic tirnak ikilenir)."""
    return "'" + str(value).replace("'", "''") + "'"


def _guid(value: str) -> str:
    if not _GUID_RE.match(value or ""):
        raise ScriptError(f"gecersiz bagdastirici kimligi: {value!r}")
    return value


def _ip(value: str) -> str:
    if not _IPV4_RE.match(str(value or "")):
        raise ScriptError(f"gecersiz IPv4: {value!r}")
    return value


def step_body(c: Change) -> str:
    """Tek adimin PowerShell govdesi. Bagdastirici her zaman GUID ile bulunur."""
    p = c.params
    if c.kind == ChangeKind.ICS:
        if not p.get("public"):
            return "Disable-AllSharing"
        return (f"Enable-Sharing -Public {ps(_guid(p['public']))} "
                f"-Private {ps(_guid(p['private']))}")

    head = f"$a = Get-AdapterByGuid {ps(_guid(c.target))}; $i = $a.ifIndex\n"
    if c.kind == ChangeKind.ENABLED:
        verb = "Enable-NetAdapter" if p.get("enabled") else "Disable-NetAdapter"
        return head + f"$a | {verb} -Confirm:$false"
    if c.kind == ChangeKind.RENAME:
        return head + f"$a | Rename-NetAdapter -NewName {ps(p['name'])}"
    if c.kind == ChangeKind.DHCP_RENEW:
        return head + ('$out = ipconfig /renew "$($a.Name)" 2>&1\n'
                       'if ($LASTEXITCODE -ne 0) { throw "ipconfig /renew: $($out -join \' \')" }')
    if c.kind == ChangeKind.ADVANCED:
        # Ozellik kayit anahtariyla bulunur (gorunen ad surucu dilinde); hepsi -NoRestart ile yazilir,
        # bagdastirici en sonda BIR KEZ yeniden baslatilir (devre disiysa baslatilmaz: Restart acar).
        lines = []
        for keyword, value in (p.get("values") or {}).items():
            if not _KEYWORD_RE.match(str(keyword)):
                raise ScriptError(f"gecersiz ozellik anahtari: {keyword!r}")
            if value is None:
                lines.append(f"Get-NetAdapterAdvancedProperty -Name $a.Name -IncludeHidden -RegistryKeyword {ps(keyword)} | "
                             "Reset-NetAdapterAdvancedProperty -NoRestart")
            else:
                lines.append(f"Set-NetAdapterAdvancedProperty -Name $a.Name -IncludeHidden -RegistryKeyword {ps(keyword)} "
                             f"-RegistryValue {ps(value)} -NoRestart")
        lines.append("if (\"$($a.AdminStatus)\" -eq 'Up') { Restart-NetAdapter -Name $a.Name -IncludeHidden -Confirm:$false }")
        return head + "\n".join(lines)
    if c.kind == ChangeKind.MTU:
        return head + f"Set-NetIPInterface -InterfaceIndex $i -AddressFamily IPv4 -NlMtuBytes {int(p['mtu'])}"
    if c.kind == ChangeKind.METRIC:
        if p.get("auto"):
            return head + "Set-NetIPInterface -InterfaceIndex $i -AddressFamily IPv4 -AutomaticMetric Enabled"
        return head + f"Set-NetIPInterface -InterfaceIndex $i -AddressFamily IPv4 -InterfaceMetric {int(p['metric'])}"
    if c.kind == ChangeKind.DNS4:
        if p.get("mode") == "auto":
            return head + "Set-DnsClientServerAddress -InterfaceIndex $i -ResetServerAddresses"
        servers = ", ".join(ps(_ip(s)) for s in p.get("servers") or [])
        return head + f"Set-DnsClientServerAddress -InterfaceIndex $i -ServerAddresses @({servers})"
    if c.kind == ChangeKind.IPV4:
        if p.get("mode") == "dhcp":
            return head + "Set-Ipv4Dhcp -Index $i"
        if not p.get("address"):
            return head + "Set-Ipv4Static -Index $i"
        gw = f" -Gateway {ps(_ip(p['gateway']))}" if p.get("gateway") else ""
        return head + (f"Set-Ipv4Static -Index $i -Address {ps(_ip(p['address']))} "
                       f"-Prefix {int(p['prefix'])}{gw}")
    raise ScriptError(f"desteklenmeyen adim: {c.kind}")


_PRELUDE = r"""
# networkPlus tarafindan uretildi. Bu betik AG AYARLARINI DEGISTIRIR.
param([Parameter(Mandatory = $true)][string]$WorkDir, [int]$ConfirmSeconds = __CONFIRM__)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Json([string]$name, $obj) {
    $obj | ConvertTo-Json -Depth 6 | Out-File -FilePath (Join-Path $WorkDir $name) -Encoding utf8
}

function Get-AdapterByGuid([string]$guid) {
    $a = Get-NetAdapter -IncludeHidden | Where-Object { "$($_.InterfaceGuid)" -eq $guid }
    if (-not $a) { throw "Bagdastirici bulunamadi: $guid" }
    $a
}

function Set-Ipv4Dhcp([int]$Index) {
    Get-NetRoute -InterfaceIndex $Index -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetIPAddress -InterfaceIndex $Index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.PrefixOrigin -eq 'Manual' } | Remove-NetIPAddress -Confirm:$false
    Set-NetIPInterface -InterfaceIndex $Index -AddressFamily IPv4 -Dhcp Enabled
}

function Set-Ipv4Static([int]$Index, [string]$Address, [int]$Prefix, [string]$Gateway) {
    Set-NetIPInterface -InterfaceIndex $Index -AddressFamily IPv4 -Dhcp Disabled
    Get-NetRoute -InterfaceIndex $Index -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetIPAddress -InterfaceIndex $Index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    if ($Address) {
        $p = @{ InterfaceIndex = $Index; AddressFamily = 'IPv4'; IPAddress = $Address; PrefixLength = $Prefix }
        if ($Gateway) { $p.DefaultGateway = $Gateway }
        New-NetIPAddress @p | Out-Null
    }
}

function Get-SharingManager { New-Object -ComObject HNetCfg.HNetShare }

function Disable-AllSharing {
    $m = Get-SharingManager
    foreach ($c in $m.EnumEveryConnection) {
        $cfg = $m.INetSharingConfigurationForINetConnection.Invoke($c)
        if ($cfg.SharingEnabled) { $cfg.DisableSharing() }
    }
}

function Enable-Sharing([string]$Public, [string]$Private) {
    # Windows ayni anda tek public/private ciftine izin verir: once hepsini kapat.
    Disable-AllSharing
    $m = Get-SharingManager
    # Yeniden baslatmada calismama sorunu (MS KB) + hizmet otomatik.
    $key = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\SharedAccess'
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    New-ItemProperty -Path $key -Name EnableRebootPersistConnection -Value 1 -PropertyType DWord -Force | Out-Null
    Set-Service -Name SharedAccess -StartupType Automatic
    if ((Get-Service SharedAccess).Status -ne 'Running') { Start-Service SharedAccess }
    $pub = $null; $priv = $null
    foreach ($c in $m.EnumEveryConnection) {
        $g = "$($m.NetConnectionProps.Invoke($c).Guid)"
        if ($g -eq $Public) { $pub = $c }
        if ($g -eq $Private) { $priv = $c }
    }
    if (-not $pub) { throw "Paylasim kaynagi bulunamadi: $Public" }
    if (-not $priv) { throw "Paylasim hedefi bulunamadi: $Private" }
    $m.INetSharingConfigurationForINetConnection.Invoke($pub).EnableSharing(0)
    $m.INetSharingConfigurationForINetConnection.Invoke($priv).EnableSharing(1)
}

function Invoke-Steps($steps) {
    $out = @()
    foreach ($s in $steps) {
        try {
            & $s.body
            $out += [ordered]@{ id = $s.id; title = $s.title; ok = $true; error = $null }
        } catch {
            $out += [ordered]@{ id = $s.id; title = $s.title; ok = $false; error = "$($_.Exception.Message)".Trim() }
        }
    }
    ,$out
}
"""

_MAIN = r"""
$applied = Invoke-Steps $ApplySteps
Write-Json 'applied.json' ([ordered]@{ phase = 'applied'; steps = $applied; confirm_seconds = $ConfirmSeconds })

$decision = 'keep'
if ($ConfirmSeconds -gt 0 -and $RollbackSteps.Count -gt 0) {
    $decision = 'timeout'
    $deadline = (Get-Date).AddSeconds($ConfirmSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path (Join-Path $WorkDir 'keep.flag')) { $decision = 'keep'; break }
        if (Test-Path (Join-Path $WorkDir 'revert.flag')) { $decision = 'revert'; break }
        Start-Sleep -Milliseconds 250
    }
}
$rolled = @()
if ($decision -ne 'keep') { $rolled = Invoke-Steps $RollbackSteps }
Write-Json 'final.json' ([ordered]@{ phase = 'final'; decision = $decision; rollback = $rolled })
"""


def _steps_block(var: str, changes: list[Change], titles: list[str]) -> str:
    lines = [f"${var} = @("]
    for n, (c, title) in enumerate(zip(changes, titles), 1):
        body = step_body(c).replace("\n", "\n        ")
        lines.append(f"    @{{ id = {n}; title = {ps(title)}; body = {{\n        {body}\n    }} }}")
    lines.append(")")
    return "\n".join(lines)


def render_script(apply: list[Change], apply_titles: list[str],
                  rollback: list[Change], rollback_titles: list[str],
                  confirm_seconds: int = CONFIRM_SECONDS) -> str:
    return "\n".join([
        _PRELUDE.replace("__CONFIRM__", str(int(confirm_seconds))).strip(),
        "",
        "# ---- Uygulanacak adimlar",
        _steps_block("ApplySteps", apply, apply_titles),
        "",
        "# ---- Onaylanmazsa geri alma adimlari (degisiklik oncesi durum)",
        _steps_block("RollbackSteps", rollback, rollback_titles),
        _MAIN.rstrip(),
        "",
    ])


class ElevationDenied(RuntimeError):
    """Kullanici UAC istemini reddetti veya betik baslatilamadi."""


class WindowsApplyJob:
    """Tek bir Uygula islemi. run() engelleyicidir (is parcaciginda cagrilir);
    applied()/keep()/revert() arayuz is parcacigindan cagrilabilir."""

    def __init__(self, script: str, confirm_seconds: int = CONFIRM_SECONDS):
        self.work_dir = new_job_dir()      # proje/.tmp/apply (Windows TEMP degil)
        self.script_path = self.work_dir / "apply.ps1"
        self.script_path.write_text(script, encoding="utf-8-sig")
        self.confirm_seconds = max(0, int(confirm_seconds))

    def run(self, timeout_s: int = CONFIRM_SECONDS + 180) -> dict:
        from .elevate import is_admin
        args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.script_path),
                "-WorkDir", str(self.work_dir), "-ConfirmSeconds", str(self.confirm_seconds)]
        if is_admin():
            # Uygulama zaten yonetici: UAC yok, betik dogrudan calisir.
            cmd = ["powershell.exe", *args]
        else:
            inner = subprocess.list2cmdline(args)
            outer = (f"$p = Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden "
                     f"-Wait -PassThru -ArgumentList {ps(inner)}; exit $p.ExitCode")
            encoded = base64.b64encode(outer.encode("utf-16-le")).decode("ascii")
            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise ElevationDenied(tr("Uygulama betiği zaman aşımına uğradı.")) from exc
        final = self._read("final.json")
        if final is None:
            if self._read("applied.json") is None:
                err = proc.stderr.decode("utf-8", "replace").strip()
                raise ElevationDenied(tr("Yönetici izni verilmedi ya da betik başlatılamadı.")
                                      + (f"\n\n{err[:400]}" if err else ""))
            raise ElevationDenied(tr("Betik beklenmedik şekilde sonlandı (final.json yok)."))
        return final

    def applied(self) -> dict | None:
        return self._read("applied.json")

    def keep(self) -> None:
        (self.work_dir / "keep.flag").write_text("keep", encoding="ascii")

    def revert(self) -> None:
        (self.work_dir / "revert.flag").write_text("revert", encoding="ascii")

    def _read(self, name: str) -> dict | None:
        path = self.work_dir / name
        for _ in range(3):
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except FileNotFoundError:
                return None
            except (OSError, ValueError):
                time.sleep(0.1)       # betik henuz yazmayi bitirmemis olabilir
        return None
