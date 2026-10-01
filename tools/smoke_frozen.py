"""Paketlenmis (PyInstaller) exe'nin duman sinamasi — sisteme DOKUNMAZ.

    python tools/smoke_frozen.py dist/networkPlus-<surum>-<os>-<mimari>[.exe]

1. DHCP sunucusu rolu: gecersiz ayarla --np-dhcp-daemon -> stdout'ta JSON 'config' hatasi
   (soket ACILMADAN cikar). Pencereli exe'de boru (stdin/stdout) calisiyor mu?
2. Linux uygulayici rolu (yalniz Linux): argumansiz --np-linux-helper -> kullanim + kod 2
   (hicbir nmcli komutu calismaz).
3. Arayuz: --snapshot fixture --screenshot -> .ui/.ts/.qss paketten yuklenip goruntu alinir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tmp" / "build" / "smoke"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'GECTI' if ok else 'KALDI'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    exe = Path(sys.argv[1]).resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    print(f"sinanan: {exe} ({exe.stat().st_size / 1e6:.1f} MB)")

    bad = WORK / "bad-config.json"
    bad.write_text(json.dumps({"server_ip": "999.1.1.1", "prefix": 24, "pool_start": "x", "pool_end": "y"}),
                   encoding="utf-8")
    r = subprocess.run([str(exe), "--np-dhcp-daemon", "--src", ".", "--config", str(bad),
                        "--leases", str(WORK / "leases.json")],
                       capture_output=True, timeout=120, stdin=subprocess.PIPE)
    try:
        out = r.stdout.decode("utf-8")                 # arayuz de katı UTF-8 bekler
        events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
        utf8 = True
    except UnicodeDecodeError as exc:
        events, utf8 = [], False
        out = f"UTF-8 degil: {exc}"
    check("DHCP sunucusu rolu: JSON boru (UTF-8) + ayar hatasi",
          utf8 and r.returncode == 2 and any(e.get("code") == "config" for e in events),
          f"kod {r.returncode}, {events[:1] or out[:200]} {r.stderr.decode('utf-8', 'replace').strip()[-200:]}")

    if sys.platform.startswith("linux"):
        r = subprocess.run([str(exe), "--np-linux-helper"], capture_output=True, text=True, timeout=120)
        check("Linux uygulayici rolu: kullanim, degisiklik yok", r.returncode == 2, f"kod {r.returncode}")

    shot = WORK / "frozen-screenshot.png"
    if shot.exists():
        shot.unlink()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    if sys.platform == "win32":
        env.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
    start = time.monotonic()
    r = subprocess.run([str(exe), "--snapshot", str(ROOT / "tests" / "fixtures" / "win-host.raw.json"),
                        "--screenshot", str(shot)], capture_output=True, text=True, timeout=180, env=env)
    check("Arayuz paketten acildi (.ui, ceviri, tema) ve goruntu alindi",
          shot.exists() and shot.stat().st_size > 10000,
          f"kod {r.returncode}, {time.monotonic() - start:.1f} sn, {r.stderr.strip()[-300:]}")

    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"SONUC: {passed}/{len(RESULTS)} gecti")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
