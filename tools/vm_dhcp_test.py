"""DHCP sunucusunun CANLI denemesi — YALNIZCA test VM'inde, kok olarak (ADR 0010).

    sudo PYTHONDONTWRITEBYTECODE=1 python3 tools/vm_dhcp_test.py [--nics ens37,ens38]

Sunucu A kartinda (statik 10.50.0.1/24), B karti ayni yalitilmis segmentte (VMnet5)
NetworkManager DHCP istemcisi. SSH karti (varsayilan rota) HIC degismez; sonunda A/B
profilleri eski haline doner. Gercek sunucu sureci (platform/dhcp_daemon.py) kullanilir.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DAEMON = SRC / "networkplus" / "platform" / "dhcp_daemon.py"
WORK = ROOT / ".tmp" / "dhcp-vm"
SERVER_IP = "10.50.0.1"
RESULTS: list[tuple[str, bool, str]] = []


def sh(*argv, check=False) -> str:
    r = subprocess.run(argv, capture_output=True, text=True, env=dict(os.environ, LC_ALL="C"))
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(argv)}: {r.stderr.strip()}")
    return r.stdout.strip()


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'GECTI' if ok else 'KALDI'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def ipv4(dev) -> list[str]:
    data = json.loads(sh("ip", "-j", "-4", "addr", "show", "dev", dev) or "[]")
    return [a["local"] for d in data for a in d.get("addr_info", [])]


def uuid_of(dev) -> str:
    name = sh("nmcli", "-g", "GENERAL.CONNECTION", "device", "show", dev)
    if name:
        return sh("nmcli", "-g", "connection.uuid", "connection", "show", name)
    # Etkin degil (ör. yeniden baslatma sonrasi DHCP zaman asimi): profil arayuz adina bagli
    for line in sh("nmcli", "-t", "-f", "UUID,TYPE", "connection", "show").splitlines():
        uuid, _, kind = line.partition(":")
        if kind == "802-3-ethernet" and sh("nmcli", "-g", "connection.interface-name",
                                           "connection", "show", uuid) == dev:
            return uuid
    raise RuntimeError(f"{dev}: NetworkManager profili yok")


def wait(pred, timeout=40, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


class Daemon:
    def __init__(self, cfg: dict, tag: str):
        WORK.mkdir(parents=True, exist_ok=True)
        self.cfg_path = WORK / f"{tag}-config.json"
        self.leases_path = WORK / f"{tag}-leases.json"
        self.cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.events: list[dict] = []
        self.proc = subprocess.Popen(
            [sys.executable, str(DAEMON), "--src", str(SRC), "--config", str(self.cfg_path),
             "--leases", str(self.leases_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                self.events.append(json.loads(line))
            except ValueError:
                pass

    def has(self, **kw) -> bool:
        return any(all(e.get(k) == v for k, v in kw.items()) for e in self.events)

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def close_stdin(self):
        self.proc.stdin.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nics", default="ens37,ens38")
    args = ap.parse_args()
    a, b = args.nics.split(",")
    if os.geteuid() != 0:
        print("kok olarak calistirin")
        return 2
    via = sh("ip", "-j", "route", "get", "8.8.8.8")
    via_dev = json.loads(via)[0]["dev"] if via else ""
    if via_dev in (a, b):
        print(f"GUVENLIK: {via_dev} internet/SSH karti; durduruldu")
        return 3
    ua, ub = uuid_of(a), uuid_of(b)
    before = {u: (sh("nmcli", "-g", "ipv4.method", "connection", "show", u),
                  sh("nmcli", "-g", "ipv4.addresses", "connection", "show", u)) for u in (ua, ub)}
    mac_b = Path(f"/sys/class/net/{b}/address").read_text().strip()
    print(f"sunucu: {a} ({SERVER_IP}), istemci: {b} ({mac_b}); SSH: {via_dev} (dokunulmaz)")

    daemon = None
    try:
        sh("nmcli", "connection", "modify", ua, "ipv4.method", "manual",
           "ipv4.addresses", f"{SERVER_IP}/24", "ipv4.gateway", "", check=True)
        sh("nmcli", "--wait", "20", "connection", "up", ua, check=True)
        sh("nmcli", "connection", "modify", ub, "ipv4.method", "auto", "ipv4.addresses", "", check=True)

        cfg = {"server_ip": SERVER_IP, "prefix": 24, "pool_start": "10.50.0.100", "pool_end": "10.50.0.150",
               "dns": [], "lease_time": 300, "ifname": a, "interface": a}
        daemon = Daemon(cfg, "a")
        check("Sunucu basladi", wait(lambda: daemon.has(event="started"), 10),
              str([e for e in daemon.events if e.get("event") == "error"]))

        # Ikinci sunucu ayni kartta: port 67 cakismasi ACIKCA bildirilmeli (qtDHCP gizliyordu)
        second = Daemon(cfg, "b")
        second.proc.wait(10)
        err = next((e for e in second.events if e.get("event") == "error"), {})
        check("Ikinci sunucu port cakismasini bildiriyor", err.get("code") == "bind", str(err))

        sh("nmcli", "--wait", "45", "connection", "up", ub)
        ok = wait(lambda: any(ip.startswith("10.50.0.1") for ip in ipv4(b)), 45)
        check("Istemci havuzdan adres aldi", ok, str(ipv4(b)))
        check("lease_new olayi (dogru cihaz)", daemon.has(event="lease_event", kind="lease_new", mac=mac_b))
        check("DORA paketleri", daemon.has(event="packet", type="DISCOVER") and daemon.has(event="packet", type="REQUEST"))

        daemon.send({"cmd": "reservations", "items": {mac_b: {"ip": "10.50.0.50", "name": "test"}}})
        time.sleep(1)
        sh("nmcli", "--wait", "45", "connection", "up", ub)
        ok = wait(lambda: "10.50.0.50" in ipv4(b), 45)
        check("Rezervasyon: istemci 10.50.0.50 aldi", ok, str(ipv4(b)))

        daemon.close_stdin()                       # arayuz kapandi gibi
        code = daemon.proc.wait(10)
        check("stdin kapaninca sunucu durdu", code == 0 and daemon.has(event="stopped"), f"kod {code}")
        saved = json.loads(daemon.leases_path.read_text(encoding="utf-8"))
        check("Kiralar diske yazildi", any(l["mac"] == mac_b and l["ip"] == "10.50.0.50" for l in saved), str(saved))
    finally:
        if daemon and daemon.proc.poll() is None:
            daemon.proc.kill()
        for u, (method, addrs) in before.items():
            sh("nmcli", "connection", "modify", u, "ipv4.method", method or "auto", "ipv4.addresses", addrs or "")
        sh("nmcli", "--wait", "5", "connection", "up", ua)
        sh("nmcli", "--wait", "5", "connection", "up", ub)
    after = {u: sh("nmcli", "-g", "ipv4.method", "connection", "show", u) for u in (ua, ub)}
    check("Profiller eski haline dondu", all(after[u] == before[u][0] for u in (ua, ub)), str(after))
    check(f"{via_dev} (SSH) hala calisiyor",
          subprocess.run(["ping", "-c", "1", "-W", "2", "192.168.42.2"], capture_output=True).returncode == 0)
    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\nSONUC: {passed}/{len(RESULTS)} gecti")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
