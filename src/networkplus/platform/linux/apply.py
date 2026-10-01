"""Linux (NetworkManager): degisiklik adimlari -> nmcli argv listeleri; pkexec ile uygulama.

`steps_for` saf fonksiyondur (birim testli). Kok yetkisiyle yalnizca helper.py
calisir; komutlari kabuksuz calistirir ve Windows ile ayni koru/geri al
protokolunu izler (ADR 0003, 0005).

Kurallar (Mint 22.3 / NM 1.46 uzerinde denendi, bkz. docs/testing.md):
- Bagdastirici profili UUID ile hedeflenir; profili yoksa `networkplus-<if>` olusturulur.
- Etkin olmayan (NM 'disconnected') bagdastiricida yalnizca profil degisir, etkinlestirilmez.
- DNS ve metrik `device reapply` ile (baglanti dusmeden) uygulanir.
- DHCP'ye donuste `con up` basarisizligi (sunucu yok) adimi bozmaz, uyari olur.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess

import time
from pathlib import Path

from ...core.changes import Change, ChangeKind, bridge_members, describe
from ...core.model import Node, Status, Topology
from ...paths import new_job_dir
from ...core.i18n import tr

CONFIRM_SECONDS = 30
HELPER = Path(__file__).with_name("helper.py")
UP_WAIT = "30"


class ScriptError(ValueError):
    """nmcli komutuna cevrilemeyen adim."""


def _cmd(*argv, ignore: bool = False) -> dict:
    return {"argv": [str(a) for a in argv], "ignore": ignore}


def _node(topo: Topology, node_id: str) -> Node:
    node = topo.nodes.get(node_id)
    if node is None or not node.is_adapter:
        raise ScriptError(f"bagdastirici yok: {node_id!r}")
    return node


def _profile(node: Node) -> tuple[str, list[dict]]:
    """(profil tanimlayicisi, gerekirse profil olusturma komutlari)."""
    nm = node.props.get("nm") or {}
    if nm.get("uuid"):
        return nm["uuid"], []
    name = f"networkplus-{node.label}"
    return name, [_cmd("nmcli", "connection", "add", "type", "ethernet", "ifname", node.label,
                       "con-name", name, "autoconnect", "yes")]


def _is_active(node: Node) -> bool:
    return node.status == Status.UP and bool((node.props.get("nm") or {}).get("active"))


def _up(node: Node, ident: str, ignore: bool = False) -> list[dict]:
    if not _is_active(node):
        return []
    return [_cmd("nmcli", "--wait", UP_WAIT, "connection", "up", ident, ignore=ignore)]


def _reapply(node: Node) -> list[dict]:
    return [_cmd("nmcli", "device", "reapply", node.label)] if _is_active(node) else []


def _mtu_key(node: Node) -> str:
    kind = ((node.props.get("nm") or {}).get("type") or "")
    return "802-11-wireless.mtu" if "wireless" in kind else "802-3-ethernet.mtu"


def _ipv4_args(ip: dict) -> list[str]:
    mode = ip.get("mode")
    if mode == "dhcp":
        return ["ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", ""]
    if mode == "disabled" or (mode == "static" and not ip.get("address")):
        return ["ipv4.method", "disabled", "ipv4.addresses", "", "ipv4.gateway", ""]
    if mode == "static":
        return ["ipv4.method", "manual", "ipv4.addresses", f"{ip['address']}/{int(ip['prefix'])}",
                "ipv4.gateway", ip.get("gateway") or ""]
    raise ScriptError(f"bilinmeyen IPv4 kipi: {mode!r}")


def commands_for(c: Change, topo: Topology) -> list[dict]:
    p = c.params
    if c.kind == ChangeKind.ICS:
        return _ics(c, topo)
    if c.kind == ChangeKind.BRIDGE_CREATE:
        return _bridge_create(c, topo)
    if c.kind == ChangeKind.BRIDGE_DELETE:
        return _bridge_delete(c, topo)

    node = _node(topo, c.target)
    ident, pre = _profile(node)
    if c.kind == ChangeKind.ENABLED:
        if not p.get("enabled"):
            return [_cmd("nmcli", "device", "disconnect", node.label)]
        # DHCP profilinde 'connect' IP beklerken takilir, IP alamazsa hata doner; aygit yine
        # de etkindir ve DHCP arka planda surer (acilistaki gibi). VM'de yakalandi (DHCP
        # sunucusu olmayan segment): kisa bekle, zaman asimini uyari say.
        if node.props.get("dhcp4"):
            return [_cmd("nmcli", "--wait", "5", "device", "connect", node.label, ignore=True)]
        return [_cmd("nmcli", "--wait", UP_WAIT, "device", "connect", node.label)]
    if c.kind == ChangeKind.IPV4:
        dhcp = p.get("mode") == "dhcp"
        return pre + [_cmd("nmcli", "connection", "modify", ident, *_ipv4_args(p))] + _up(node, ident, ignore=dhcp)
    if c.kind == ChangeKind.DNS4:
        if p.get("mode") == "auto":
            args = ["ipv4.dns", "", "ipv4.ignore-auto-dns", "no"]
        else:
            args = ["ipv4.dns", ",".join(p.get("servers") or []), "ipv4.ignore-auto-dns", "yes"]
        return pre + [_cmd("nmcli", "connection", "modify", ident, *args)] + _reapply(node)
    if c.kind == ChangeKind.METRIC:
        value = -1 if p.get("auto") else int(p["metric"])
        return pre + [_cmd("nmcli", "connection", "modify", ident, "ipv4.route-metric", value)] + _reapply(node)
    if c.kind == ChangeKind.MTU:
        value = "auto" if not p.get("mtu") else int(p["mtu"])
        return pre + [_cmd("nmcli", "connection", "modify", ident, _mtu_key(node), value)] + _up(node, ident)
    if c.kind == ChangeKind.DHCP_RENEW:
        return [_cmd("nmcli", "--wait", UP_WAIT, "connection", "up", ident)]
    raise ScriptError(f"Linux'ta desteklenmeyen adim: {c.kind.value}")


def _ics(c: Change, topo: Topology) -> list[dict]:
    """NM 'shared': hedef profil ipv4.method=shared (NAT + DHCP'yi NM kurar)."""
    priv_id = c.params.get("private")
    if c.params.get("public") and priv_id:
        node = _node(topo, priv_id)
        ident, pre = _profile(node)
        return pre + [
            _cmd("nmcli", "connection", "modify", ident, "ipv4.method", "shared",
                 "ipv4.addresses", "", "ipv4.gateway", ""),
            _cmd("nmcli", "--wait", UP_WAIT, "connection", "up", ident),
        ]
    # Kapat: su an paylasan her profili DHCP'ye dondur (onceki ayari geri alma yukler).
    out: list[dict] = []
    for node in topo.nodes.values():
        if node.is_adapter and node.props.get("sharing") == "private":
            ident, pre = _profile(node)
            out += pre + [_cmd("nmcli", "connection", "modify", ident, *_ipv4_args({"mode": "dhcp"}))]
            out += _up(node, ident, ignore=True)
    return out


def _bridge_create(c: Change, topo: Topology) -> list[dict]:
    name = c.target
    bridge_con = f"networkplus-{name}"
    out = [_cmd("nmcli", "connection", "add", "type", "bridge", "ifname", name, "con-name", bridge_con,
                "bridge.stp", "no", *_ipv4_args(c.params.get("ipv4") or {"mode": "dhcp"}))]
    ports = []
    for mid in c.params.get("members") or []:
        member = _node(topo, mid)
        port_con = f"networkplus-{name}-{member.label}"
        ports.append(port_con)
        out.append(_cmd("nmcli", "connection", "add", "type", "ethernet", "ifname", member.label,
                        "con-name", port_con, "master", name, "slave-type", "bridge"))
    # Portu etkinlestirmek kopruyu de etkinlestirir; kopruyu once acmak DHCP'de bekler.
    for port_con in ports:
        out.append(_cmd("nmcli", "--wait", UP_WAIT, "connection", "up", port_con))
    return out


def _bridge_delete(c: Change, topo: Topology) -> list[dict]:
    name = c.target
    out: list[dict] = []
    if c.params.get("created"):
        for mid in c.params.get("members") or []:
            label = topo.nodes[mid].label if mid in topo.nodes else mid
            out.append(_cmd("nmcli", "connection", "delete", f"networkplus-{name}-{label}", ignore=True))
        out.append(_cmd("nmcli", "connection", "delete", f"networkplus-{name}", ignore=True))
    else:
        bridge = next((n for n in topo.nodes.values() if n.is_adapter and n.label == name), None)
        bridge_uuid = ((bridge.props.get("nm") or {}).get("uuid")) if bridge else None
        for mid in bridge_members(topo, name):
            port_uuid = (topo.nodes[mid].props.get("nm") or {}).get("uuid")
            if port_uuid:
                out.append(_cmd("nmcli", "connection", "delete", port_uuid, ignore=True))
        if bridge_uuid:
            out.append(_cmd("nmcli", "connection", "delete", bridge_uuid))
        else:
            out.append(_cmd("ip", "link", "delete", name, "type", "bridge"))
    for uuid in (c.params.get("restore") or {}).values():
        out.append(_cmd("nmcli", "--wait", UP_WAIT, "connection", "up", uuid, ignore=True))
    return out


def build_payload(plan, topo: Topology, confirm_seconds: int = CONFIRM_SECONDS) -> dict:
    def steps(changes, titles):
        return [{"id": n, "title": title, "commands": commands_for(c, topo)}
                for n, (c, title) in enumerate(zip(changes, titles), 1)]
    return {
        "apply": steps(plan.changes, [i.title for i in plan.items]),
        "rollback": steps(plan.rollback, [describe(c, topo) for c in plan.rollback]),
        "confirm_seconds": int(confirm_seconds),
    }


def render_preview(payload: dict) -> str:
    """Kullaniciya gosterilen / kaydedilen okunur betik (helper'in calistirdigi komutlar)."""
    lines = ["#!/bin/sh", "# " + tr("networkPlus — Linux (NetworkManager) uygulama planı"),
             "# " + tr("Uygulama bunları kök yetkisiyle helper.py üzerinden, kabuksuz çalıştırır."), ""]
    for section, key in ((tr("Uygulanacak adımlar"), "apply"),
                         (tr("Onaylanmazsa ({seconds} sn) geri alma").format(
                             seconds=payload.get("confirm_seconds")), "rollback")):
        lines.append(f"# ---- {section}")
        for step in payload.get(key) or []:
            lines.append(f"# {step['id']}) {step['title']}")
            for cmd in step["commands"]:
                suffix = "  || true" if cmd.get("ignore") else ""
                lines.append(shlex.join(cmd["argv"]) + suffix)
        lines.append("")
    return "\n".join(lines)


class ElevationDenied(RuntimeError):
    """Kullanici parola istemini reddetti / pkexec yok."""


def elevation_prefix() -> list[str]:
    """Kok degilse pkexec (NETWORKPLUS_ELEVATE ile degistirilebilir, ör. 'sudo -n')."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    return shlex.split(os.environ.get("NETWORKPLUS_ELEVATE", "pkexec"))


class LinuxApplyJob:
    def __init__(self, payload: dict):
        self.work_dir = new_job_dir()      # proje/.tmp/apply (Windows TEMP degil)
        self.plan_path = self.work_dir / "plan.json"
        self.plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    def run(self, timeout_s: int = CONFIRM_SECONDS + 600) -> dict:
        prefix = elevation_prefix()
        if prefix and not shutil.which(prefix[0]):
            raise ElevationDenied(tr("Yetki aracı bulunamadı: {tool} (policykit-1 kurulu mu?)").format(tool=prefix[0]))
        from ..selfexec import LINUX_HELPER_FLAG, command_for
        argv = prefix + command_for(HELPER, LINUX_HELPER_FLAG) + [str(self.plan_path), str(self.work_dir)]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise ElevationDenied(tr("Uygulama zaman aşımına uğradı.")) from exc
        final = self._read("final.json")
        if final is None:
            err = proc.stderr.decode("utf-8", "replace").strip()
            if self._read("applied.json") is None:
                why = {126: tr("parola penceresi kapatıldı"), 127: tr("yetki verilmedi")}.get(proc.returncode, "")
                raise ElevationDenied(tr("Yönetici yetkisi alınamadı") + (f" ({why})" if why else "") + "."
                                      + (f"\n\n{err[:400]}" if err else ""))
            raise ElevationDenied(tr("Uygulayıcı beklenmedik şekilde sonlandı (final.json yok).")
                                  + (f"\n\n{err[:400]}" if err else ""))
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
                return json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            except (OSError, ValueError):
                time.sleep(0.1)
        return None
