"""Gelistirici araci: ham anlik goruntu alir, kisisel veriyi anonimlestirip kaydeder.

Kullanim:
    python tools/capture_snapshot.py tests/fixtures/win-host.raw.json
    python tools/capture_snapshot.py --from ham.json tests/fixtures/x.raw.json

Anonimlestirilen: MAC/BSSID (deterministik sahte, iliskiler korunur),
makine adi, SSID, ag profili adlari. IP adresleri korunur (ozel aglar;
iliski cikarimi onlara dayanir). SALT OKUNUR: toplayici hicbir ayari degistirmez.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}$")


class Anonymizer:
    def __init__(self):
        self.macs: dict[str, str] = {}
        self.names: dict[str, str] = {}

    def mac(self, value: str) -> str:
        key = value.upper().replace(":", "-")
        if key not in self.macs:
            n = len(self.macs) + 1
            self.macs[key] = f"02-00-00-00-{n >> 8:02X}-{n & 0xFF:02X}"
        sep = ":" if ":" in value else "-"
        out = self.macs[key]
        return out.replace("-", sep) if sep == ":" else out

    def alias(self, prefix: str, value: str) -> str:
        key = f"{prefix}:{value}"
        if key not in self.names:
            self.names[key] = f"{prefix}{sum(1 for k in self.names if k.startswith(prefix + ':')) + 1}"
        return self.names[key]

    def walk(self, obj, key: str = ""):
        if isinstance(obj, dict):
            return {k: self.walk(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.walk(v, key) for v in obj]
        if isinstance(obj, str):
            if _MAC_RE.match(obj):
                return self.mac(obj)
            if key == "hostname":
                return "DEVPC"
            if key == "ssid" and obj:
                return self.alias("WiFi_", obj)
            if key in ("network_name",) and obj:
                return self.alias("Ag_", obj)
        return obj


def anonymize(raw: dict) -> dict:
    anon = Anonymizer()
    data = anon.walk(raw)
    # Ag profili adi (Windows: profiles[].name) alan adi/SSID tasir.
    for p in data.get("profiles") or []:
        if isinstance(p, dict) and p.get("name"):
            p["name"] = anon.alias("Ag_", p["name"])
    # Surucu "Ag Adresi" (NetworkAddress): elle verilen MAC, ayracsiz 12 hane -> _MAC_RE yakalamaz.
    for a in data.get("advanced") or []:
        if isinstance(a, dict) and a.get("keyword") == "NetworkAddress":
            if a.get("value"):
                a["value"] = "020000000001"
            a["registry"] = ["020000000001" if r else r for r in a.get("registry") or []]
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("output")
    ap.add_argument("--from", dest="source", help="Canli toplamak yerine bu ham JSON'u kullan")
    args = ap.parse_args()

    if args.source:
        raw = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    else:
        from networkplus.platform import get_collector
        raw = get_collector().collect_raw()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(anonymize(raw), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"yazildi: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
