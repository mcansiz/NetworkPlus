"""Linux uygulama yolunun CANLI denemesi — YALNIZCA test VM'inde, kok olarak calistirilir.

    sudo python3 tools/vm_apply_test.py [--only ics,renew,...]

Gercek uygulama yolunu kullanir: LinuxCollector -> build_plan -> build_payload ->
LinuxApplyJob (helper.py, koru / geri al / sure dolmasi). Arayuzun yaptigini,
kullanicinin tiklamalari yerine otomatik kararla yapar.

GUVENLIK: SSH'in gectigi arayuz (varsayilan rota, ens33) HICBIR degisikligin
hedefi olamaz; olursa betik durur. Her adimdan sonra varsayilan ag gecidine ping
atilir; kesilirse betik durur. Sonunda baslangic durumu ile karsilastirilir.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus.core.changes import (                          # noqa: E402
    Change, ChangeKind, ChangeSet, HOST_TARGET, build_plan, describe,
)
from networkplus.core.discovery import build_topology           # noqa: E402
from networkplus.platform.linux.apply import LinuxApplyJob, build_payload  # noqa: E402
from networkplus.platform.linux.collector import LinuxCollector  # noqa: E402

# Varsayilan: Mint test VM'i (A,B: VMnet5 ; C: VMnet6; yalitilmis, host yok).
# Baska makinede: --nics A,B,C (A ile B ayni segmentte, C farkli segmentte olmali).
A, B, C = "ens37", "ens38", "ens39"
RESULTS: list[tuple[str, bool, str]] = []


class Abort(RuntimeError):
    pass


def snapshot():
    return build_topology(LinuxCollector().collect())


def sh(*argv) -> str:
    return subprocess.run(argv, capture_output=True, text=True, env=dict(os.environ, LC_ALL="C")).stdout


def ssh_nic_alive(gw: str) -> bool:
    return subprocess.run(["ping", "-c", "1", "-W", "2", gw], capture_output=True).returncode == 0


def ipv4_of(topo, dev) -> list[str]:
    n = topo.nodes.get(dev)
    return [x["address"] for x in (n.props.get("ipv4") or [])] if n else []


def apply(changes: list[Change], decision: str, confirm: int = 20) -> tuple[dict, dict, object]:
    topo = snapshot()
    guard = topo.internet_via
    cs = ChangeSet()
    for c in changes:
        cs.add(c)
    # Gercekten DEGISTIRILEN arayuzler (Linux ICS'te kaynak degismez, yalniz hedef).
    touched = set()
    for c in cs:
        if c.kind == ChangeKind.ICS:
            touched |= {x for x in (c.params.get("private"),) if x}
        elif c.kind in (ChangeKind.BRIDGE_CREATE, ChangeKind.BRIDGE_DELETE):
            touched |= set(c.params.get("members") or [])
        else:
            touched.add(c.target)
    if guard in touched:
        raise Abort(f"GUVENLIK: {guard} (SSH arayuzu) degisiklik hedefinde: {touched}")
    plan = build_plan(cs, topo)
    if plan.blocked:
        raise Abort("plan engelli: " + "; ".join(i.message for it in plan.items for i in it.issues
                                                  if i.severity.value == "error"))
    for c in plan.changes:
        print(f"    + {describe(c, topo)}")
    for c in plan.rollback:
        print(f"    ↺ {describe(c, topo)}")
    job = LinuxApplyJob(build_payload(plan, topo, confirm_seconds=confirm))
    box: dict = {}
    t = threading.Thread(target=lambda: box.setdefault("final", job.run()))
    t.start()
    applied = None
    while t.is_alive() and applied is None:
        applied = job.applied()
        time.sleep(0.2)
    if applied is None:
        t.join()
        applied = job.applied() or {}
    if decision == "keep":
        job.keep()
    elif decision == "revert":
        job.revert()
    t.join()
    final = box.get("final") or {}
    for st in applied.get("steps") or []:
        print(f"    {'✔' if st['ok'] else '✖'} {st['title']}" + (f" — {st['error']}" if st.get("error") else "")
              + "".join(f"\n      (uyarı) {w}" for w in st.get("warnings") or []))
    for st in final.get("rollback") or []:
        print(f"    ↺{'✔' if st['ok'] else '✖'} {st['title']}" + (f" — {st['error']}" if st.get("error") else ""))
    print(f"    karar: {final.get('decision')}")
    return applied, final, topo


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'GECTI' if ok else 'KALDI'}] {name}" + (f" — {detail}" if detail else ""))


def wait_for(pred, timeout=40, step=1.0):
    end = time.time() + timeout
    while time.time() < end:
        topo = snapshot()
        if pred(topo):
            return topo
        time.sleep(step)
    return snapshot()


def method(dev) -> str:
    return sh("nmcli", "-g", "ipv4.method", "connection", "show",
              sh("nmcli", "-g", "GENERAL.CONNECTION", "device", "show", dev).strip()).strip()


def steps_ok(applied) -> bool:
    return all(s["ok"] for s in applied.get("steps") or [])


# --------------------------------------------------------------------------- senaryolar

def t_ics():
    print("\n== ICS (NM shared): ens37 paylasir, ens38 ayni segmentten DHCP alir")
    applied, final, _ = apply([Change(ChangeKind.ICS, HOST_TARGET, {"public": "ens33", "private": A})], "keep")
    topo = wait_for(lambda t: any(ip.startswith("10.42.0.") for ip in ipv4_of(t, B)), 60)
    check("ICS: adimlar basarili ve korundu", steps_ok(applied) and final.get("decision") == "keep")
    check("ICS: ens37 = 10.42.0.1", "10.42.0.1" in ipv4_of(topo, A), str(ipv4_of(topo, A)))
    check("ICS: ens37 profili shared", method(A) == "shared", method(A))
    check("ICS: ens38 paylasimdan DHCP adresi aldi", any(ip.startswith("10.42.0.") for ip in ipv4_of(topo, B)),
          str(ipv4_of(topo, B)))
    check("ICS: diyagramda ICS kenari", any(e.kind.value == "ics" and e.dst == A for e in topo.edges))


def t_renew():
    print("\n== DHCP yenileme: ens38")
    applied, final, _ = apply([Change(ChangeKind.DHCP_RENEW, B, {})], "keep")
    topo = wait_for(lambda t: any(ip.startswith("10.42.0.") for ip in ipv4_of(t, B)), 40)
    check("Yenile: adim basarili", steps_ok(applied), str(applied.get("steps")))
    check("Yenile: geri alma adimi yok, beklemeden bitti", final.get("decision") == "keep")
    check("Yenile: ens38 yine 10.42.0.x", any(ip.startswith("10.42.0.") for ip in ipv4_of(topo, B)),
          str(ipv4_of(topo, B)))


def _static_c():
    return [Change(ChangeKind.IPV4, C, {"mode": "static", "address": "172.31.9.1", "prefix": 24, "gateway": None}),
            Change(ChangeKind.DNS4, C, {"mode": "manual", "servers": ["1.1.1.1"]}),
            Change(ChangeKind.METRIC, C, {"auto": False, "metric": 500}),
            Change(ChangeKind.MTU, C, {"mtu": 1400})]


def _restored_c(topo) -> bool:
    mtu = sh("nmcli", "-g", "802-3-ethernet.mtu", "connection", "show", topo.nodes[C].props["nm"]["uuid"]).strip()
    return method(C) == "auto" and "172.31.9.1" not in ipv4_of(topo, C) and mtu in ("auto", "0")


def t_revert():
    print("\n== Statik IP + DNS + metrik + MTU, sonra GERI AL: ens39")
    applied, final, _ = apply(_static_c(), "revert")
    check("Geri al: 4 adim uygulandi", steps_ok(applied) and len(applied.get("steps") or []) == 4,
          str([s.get("error") for s in applied.get("steps") or []]))
    topo = wait_for(_restored_c, 30)
    check("Geri al: karar revert", final.get("decision") == "revert")
    check("Geri al: ens39 DHCP'ye, MTU otomatige dondu", _restored_c(topo), f"method={method(C)} ip={ipv4_of(topo, C)}")


def t_timeout():
    print("\n== Statik IP, onay VERILMEDI (5 sn): ens39")
    applied, final, _ = apply(_static_c()[:1], "timeout", confirm=5)
    topo = wait_for(_restored_c, 30)
    check("Sure dolmasi: karar timeout", final.get("decision") == "timeout")
    check("Sure dolmasi: kendiliginden geri alindi", _restored_c(topo), f"method={method(C)} ip={ipv4_of(topo, C)}")


def t_disable():
    print("\n== Devre disi birak, sonra geri al: ens39")
    applied, final, _ = apply([Change(ChangeKind.ENABLED, C, {"enabled": False})], "revert")
    check("Devre disi: uygulandi", steps_ok(applied))
    # NM'in yeniden etkinlestirmeyi islemesi zaman alabilir; birkac kez bak.
    topo = wait_for(lambda t: t.nodes[C].status.value == "up" and method(C) == "auto", 60, 3)
    check("Devre disi: geri alininca yeniden etkin", topo.nodes[C].status.value == "up",
          f"{topo.nodes[C].status.value} / {sh('nmcli', '-g', 'GENERAL.STATE', 'device', 'show', C).strip()}")


def t_bridge():
    print("\n== Kopru: ens38 + ens39 -> br-np0 (IPv4 ens38'den: DHCP), koru; sonra kaldir")
    applied, final, _ = apply([Change(ChangeKind.BRIDGE_CREATE, "br-np0",
                                      {"members": [B, C], "ipv4": {"mode": "dhcp"}})], "keep")
    topo = wait_for(lambda t: "br-np0" in t.nodes and any(ip.startswith("10.42.0.") for ip in ipv4_of(t, "br-np0")), 60)
    check("Kopru: adimlar basarili", steps_ok(applied), str([s.get("error") for s in applied.get("steps") or []]))
    check("Kopru: br-np0 olustu (tur kopru)", "br-np0" in topo.nodes and topo.nodes["br-np0"].kind.value == "bridge")
    members = sorted(n.id for n in topo.nodes.values() if n.props.get("bridge_master") == "br-np0")
    check("Kopru: uyeler ens38, ens39", members == [B, C], str(members))
    check("Kopru: br-np0 paylasimdan DHCP aldi (ens38 uzerinden)",
          any(ip.startswith("10.42.0.") for ip in ipv4_of(topo, "br-np0")), str(ipv4_of(topo, "br-np0")))
    check("Kopru: diyagramda kopru kenarlari",
          {(e.src, e.dst) for e in topo.edges if e.kind.value == "bridge"} == {(B, "br-np0"), (C, "br-np0")})

    print("\n== Kopru kaldir (ileri yonde BRIDGE_DELETE), koru")
    applied, final, _ = apply([Change(ChangeKind.BRIDGE_DELETE, "br-np0", {"members": [B, C]})], "keep")
    topo = wait_for(lambda t: "br-np0" not in t.nodes and t.nodes[B].props.get("bridge_master") is None, 40)
    check("Kopru kaldir: adimlar basarili", steps_ok(applied), str([s.get("error") for s in applied.get("steps") or []]))
    check("Kopru kaldir: br-np0 yok", "br-np0" not in topo.nodes)
    check("Kopru kaldir: uyeler serbest", all(topo.nodes[m].props.get("bridge_master") is None for m in (B, C)))


def t_bridge_revert():
    print("\n== Kopru olustur, sonra GERI AL")
    before = {m: snapshot().nodes[m].props["nm"]["uuid"] for m in (B, C)}
    applied, final, _ = apply([Change(ChangeKind.BRIDGE_CREATE, "br-np0",
                                      {"members": [B, C], "ipv4": {"mode": "disabled"}})], "revert")
    topo = wait_for(lambda t: "br-np0" not in t.nodes and all(
        (t.nodes[m].props.get("nm") or {}).get("uuid") == before[m] for m in (B, C)), 40)
    check("Kopru geri al: olusturma basarili", steps_ok(applied), str([s.get("error") for s in applied.get("steps") or []]))
    check("Kopru geri al: br-np0 silindi", "br-np0" not in topo.nodes)
    check("Kopru geri al: uyeler eski profillerine dondu",
          all((topo.nodes[m].props.get("nm") or {}).get("uuid") == before[m] for m in (B, C)),
          str({m: (topo.nodes[m].props.get("nm") or {}).get("uuid") for m in (B, C)}))
    leftovers = [l for l in sh("nmcli", "-g", "NAME", "connection", "show").splitlines() if l.startswith("networkplus-")]
    check("Kopru geri al: artik profil kalmadi", not leftovers, str(leftovers))


def t_ics_off():
    print("\n== ICS kapat (ileri yon), koru")
    applied, final, _ = apply([Change(ChangeKind.ICS, HOST_TARGET, {"public": None, "private": None})], "keep")
    check("ICS kapat: adimlar basarili", steps_ok(applied))
    check("ICS kapat: ens37 profili auto", method(A) == "auto", method(A))


SCENARIOS = {"ics": t_ics, "renew": t_renew, "revert": t_revert, "timeout": t_timeout,
             "disable": t_disable, "bridge": t_bridge, "bridge_revert": t_bridge_revert, "ics_off": t_ics_off}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nics", help="test kartlari: A,B,C (varsayilan ens37,ens38,ens39)")
    ap.add_argument("--only", help="virgulle senaryo adlari: " + ",".join(SCENARIOS))
    args = ap.parse_args()
    global A, B, C
    if args.nics:
        A, B, C = args.nics.split(",")
    if os.geteuid() != 0:
        print("kok olarak calistirin (sudo)")
        return 2
    topo0 = snapshot()
    via = topo0.internet_via
    gw = next((r["next_hop"] for r in topo0.snapshot["default_routes"] if r["adapter"] == via), None)
    print(f"SSH/internet arayuzu: {via} (ag gecidi {gw}) — dokunulmayacak")
    if via in (A, B, C) or not gw:
        print("beklenmeyen ag duzeni; durduruldu")
        return 3
    initial = {d: method(d) for d in (A, B, C)}
    names = args.only.split(",") if args.only else list(SCENARIOS)
    try:
        for name in names:
            SCENARIOS[name]()
            if not ssh_nic_alive(gw):
                raise Abort(f"{via} uzerinden {gw}'ye ping gitmiyor — durduruldu")
            check(f"{name}: {via} (SSH) hala calisiyor", True)
    except Abort as exc:
        check("DURDURULDU", False, str(exc))
    final_methods = {d: method(d) for d in (A, B, C)}
    check("Son durum: ens37-39 baslangictaki ipv4.method'a dondu", final_methods == initial,
          f"once={initial} sonra={final_methods}")
    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\nSONUC: {passed}/{len(RESULTS)} gecti")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
