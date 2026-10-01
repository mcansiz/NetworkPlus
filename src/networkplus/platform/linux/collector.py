"""Linux toplayicisi: iproute2 (`ip -j`) + NetworkManager (`nmcli -t`). SALT OKUNUR.

Ham komut ciktilari oldugu gibi saklanir ki VM'den alinan goruntu birebir
fixture olarak kullanilabilsin; ayristirma normalize.py icindedir.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from datetime import datetime, timezone

from ..base import Collector
from .normalize import normalize, split_terse

TIMEOUT_S = 15


class LinuxCollector(Collector):
    name = "linux"

    def __init__(self):
        self.errors: list[dict] = []

    def _run(self, section: str, args: list[str]) -> str | None:
        env = dict(os.environ, LC_ALL="C", LANG="C")
        try:
            proc = subprocess.run(args, capture_output=True, timeout=TIMEOUT_S, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.errors.append({"section": section, "message": str(exc)})
            return None
        if proc.returncode != 0:
            msg = proc.stderr.decode("utf-8", "replace").strip() or f"kod {proc.returncode}"
            self.errors.append({"section": section, "message": msg[:300]})
            return None
        return proc.stdout.decode("utf-8", "replace")

    def _json(self, section: str, args: list[str]):
        out = self._run(section, args)
        if not out:
            return []
        try:
            return json.loads(out)
        except ValueError as exc:
            self.errors.append({"section": section, "message": f"gecersiz JSON: {exc}"})
            return []

    def collect_raw(self) -> dict:
        self.errors = []
        raw: dict = {
            "platform": "linux",
            "schema": 1,
            "hostname": socket.gethostname(),
            "taken_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "os": _os_release(),
            "is_admin": hasattr(os, "geteuid") and os.geteuid() == 0,
        }
        raw["ip_addr"] = self._json("ip_addr", ["ip", "-j", "-d", "addr", "show"])
        raw["routes"] = self._json("routes", ["ip", "-j", "route", "show", "table", "main"])
        raw["routes6"] = self._json("routes6", ["ip", "-6", "-j", "route", "show", "default"])
        raw["route_get"] = self._json("route_get", ["ip", "-j", "route", "get", "8.8.8.8"])
        raw["neigh"] = self._json("neigh", ["ip", "-j", "neigh", "show"])

        nm = ["nmcli", "-t", "-e", "yes"]
        raw["nm_devices"] = self._run("nm_devices", nm + ["-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
        raw["nm_active"] = self._run("nm_active", nm + ["-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active"])
        # Tum profiller (aktif olmayanlar da): geri alma profil ayarini bilmek zorunda.
        raw["nm_profiles"] = self._run("nm_profiles", nm + ["-f", "NAME,UUID,TYPE,DEVICE,ACTIVE",
                                                            "connection", "show"])
        raw["nm_conn"] = {}
        for line in (raw["nm_profiles"] or "").splitlines()[:40]:
            parts = split_terse(line)
            if len(parts) >= 2 and parts[1]:
                raw["nm_conn"][parts[1]] = self._run("nm_conn", nm + ["connection", "show", parts[1]])
        raw["nm_devshow"] = self._run("nm_devshow", nm + ["-f", "GENERAL,IP4,IP6", "device", "show"])
        raw["nm_connectivity"] = (self._run("nm_connectivity", nm + ["networking", "connectivity"]) or "").strip()
        raw["nm_wifi"] = self._run("nm_wifi", nm + ["-f", "ACTIVE,SSID,BSSID,SIGNAL,DEVICE",
                                                    "device", "wifi", "list", "--rescan", "no"])
        raw["errors"] = list(self.errors)
        return raw

    def normalize(self, raw: dict) -> dict:
        return normalize(raw)


def _os_release() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""
