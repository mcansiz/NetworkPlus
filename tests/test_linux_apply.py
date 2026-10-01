"""Linux (NetworkManager) uygulama: nmcli argv uretimi, kopru, DHCP yenileme, platform destegi.

Gercek Mint VM goruntusu (tests/fixtures/linux-mint.raw.json) kullanilir; hicbir
komut CALISTIRILMAZ. Canli deneme: tools/vm_apply_test.py (Mint VM'de, kok).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus.core.changes import (                                  # noqa: E402
    Change, ChangeKind, ChangeSet, HOST_TARGET, build_plan, next_bridge_name,
)
from networkplus.core.discovery import build_topology                   # noqa: E402
from networkplus.core.model import NodeKind, Severity, Status           # noqa: E402
from networkplus.platform.filesource import normalize_any               # noqa: E402
from networkplus.platform.linux.apply import build_payload, commands_for, render_preview  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def load(name):
    return build_topology(normalize_any(json.loads((FIX / name).read_text(encoding="utf-8"))))


def argvs(cmds):
    return [c["argv"] for c in cmds]


class MintFixture(unittest.TestCase):
    """Gercek Mint 22.3 / NM 1.46 goruntusu (2026-09-30)."""

    @classmethod
    def setUpClass(cls):
        cls.topo = load("linux-mint.raw.json")

    def test_topology(self):
        t = self.topo
        self.assertEqual(t.internet_via, "ens33")
        for name in ("ens33", "ens37", "ens38", "ens39"):
            self.assertEqual(t.nodes[name].kind, NodeKind.ETHERNET)
            self.assertEqual(t.nodes[name].status, Status.UP)
            self.assertTrue(t.nodes[name].props["nm"]["uuid"])
            self.assertTrue(t.nodes[name].props["dhcp4"])
            self.assertTrue(t.nodes[name].props["auto_metric4"])
            self.assertTrue(t.nodes[name].props["mtu_auto"])
        self.assertTrue(t.nodes["lo"].hidden)

    def plan(self, *changes):
        cs = ChangeSet()
        for c in changes:
            cs.add(c)
        return build_plan(cs, self.topo)

    def test_static_ip_commands(self):
        uuid = self.topo.nodes["ens39"].props["nm"]["uuid"]
        cmds = argvs(commands_for(Change(ChangeKind.IPV4, "ens39", {
            "mode": "static", "address": "172.31.9.1", "prefix": 24, "gateway": None}), self.topo))
        self.assertEqual(cmds[0], ["nmcli", "connection", "modify", uuid, "ipv4.method", "manual",
                                   "ipv4.addresses", "172.31.9.1/24", "ipv4.gateway", ""])
        self.assertEqual(cmds[1], ["nmcli", "--wait", "30", "connection", "up", uuid])

    def test_rollback_restores_dhcp_and_auto_mtu(self):
        p = self.plan(Change(ChangeKind.IPV4, "ens39", {"mode": "static", "address": "172.31.9.1", "prefix": 24}),
                      Change(ChangeKind.MTU, "ens39", {"mtu": 1400}))
        rb = {c.kind: c.params for c in p.rollback}
        self.assertEqual(rb[ChangeKind.IPV4], {"mode": "dhcp"})
        self.assertEqual(rb[ChangeKind.MTU], {"mtu": 0})
        payload = build_payload(p, self.topo)
        mtu_rb = next(s for s in payload["rollback"] if "MTU" in s["title"])
        self.assertIn("auto", mtu_rb["commands"][0]["argv"])
        dhcp_rb = next(s for s in payload["rollback"] if "DHCP" in s["title"])
        self.assertTrue(dhcp_rb["commands"][-1]["ignore"])        # DHCP sunucusu yoksa adim bozulmaz

    def test_dns_and_metric_use_reapply(self):
        dns = argvs(commands_for(Change(ChangeKind.DNS4, "ens39", {"mode": "manual", "servers": ["1.1.1.1", "9.9.9.9"]}),
                                 self.topo))
        self.assertIn("1.1.1.1,9.9.9.9", dns[0])
        self.assertEqual(dns[-1], ["nmcli", "device", "reapply", "ens39"])
        metric = argvs(commands_for(Change(ChangeKind.METRIC, "ens39", {"auto": True}), self.topo))
        self.assertIn("-1", metric[0])

    def test_ics_shared(self):
        p = self.plan(Change(ChangeKind.ICS, HOST_TARGET, {"public": "ens33", "private": "ens37"}))
        self.assertFalse(p.blocked)
        cmds = argvs(commands_for(p.changes[0], self.topo))
        self.assertIn("shared", cmds[0])
        # geri alma: paylasimi kapat + ens37'yi DHCP'ye dondur
        kinds = [c.kind for c in p.rollback]
        self.assertEqual(kinds, [ChangeKind.ICS, ChangeKind.IPV4])

    def test_ics_on_internet_adapter_blocked(self):
        p = self.plan(Change(ChangeKind.ICS, HOST_TARGET, {"public": "ens37", "private": "ens33"}))
        self.assertTrue(p.blocked)

    def test_bridge_create_and_rollback(self):
        name = next_bridge_name(self.topo)
        self.assertEqual(name, "br-np0")
        p = self.plan(Change(ChangeKind.BRIDGE_CREATE, name, {"members": ["ens38", "ens39"],
                                                               "ipv4": {"mode": "dhcp"}}))
        self.assertFalse(p.blocked, [i.message for it in p.items for i in it.issues])
        cmds = argvs(commands_for(p.changes[0], self.topo))
        self.assertEqual(cmds[0][:8], ["nmcli", "connection", "add", "type", "bridge", "ifname", name,
                                       "con-name"])
        self.assertIn(["nmcli", "connection", "add", "type", "ethernet", "ifname", "ens38", "con-name",
                       f"networkplus-{name}-ens38", "master", name, "slave-type", "bridge"], cmds)
        self.assertEqual(cmds[-1], ["nmcli", "--wait", "30", "connection", "up", f"networkplus-{name}-ens39"])
        rb = p.rollback[0]
        self.assertEqual(rb.kind, ChangeKind.BRIDGE_DELETE)
        self.assertEqual(set(rb.params["restore"]), {"ens38", "ens39"})    # eski profiller geri acilir
        rb_cmds = argvs(commands_for(rb, self.topo))
        self.assertIn(["nmcli", "connection", "delete", f"networkplus-{name}"], rb_cmds)

    def test_bridge_with_internet_adapter_warns(self):
        p = self.plan(Change(ChangeKind.BRIDGE_CREATE, "br-np0", {"members": ["ens33", "ens39"],
                                                                   "ipv4": {"mode": "dhcp"}}))
        self.assertFalse(p.blocked)
        self.assertTrue(any("internet" in i.message for it in p.items for i in it.issues
                            if i.severity == Severity.WARNING))

    def test_rename_unsupported_on_linux(self):
        p = self.plan(Change(ChangeKind.RENAME, "ens39", {"name": "lan2"}))
        self.assertTrue(p.blocked)

    def test_dhcp_renew(self):
        p = self.plan(Change(ChangeKind.DHCP_RENEW, "ens33", {}))
        self.assertFalse(p.blocked)
        self.assertEqual(p.rollback, [])
        self.assertIn("warning", {i.severity.value for it in p.items for i in it.issues})

    def test_enable_dhcp_adapter_ignores_no_lease(self):
        """VM'de yakalandi: DHCP sunucusu yoksa 'device connect' hata doner ama aygit etkindir."""
        cmds = commands_for(Change(ChangeKind.ENABLED, "ens39", {"enabled": True}), self.topo)
        self.assertEqual(cmds, [{"argv": ["nmcli", "--wait", "5", "device", "connect", "ens39"], "ignore": True}])

    def test_preview_text(self):
        p = self.plan(Change(ChangeKind.IPV4, "ens39", {"mode": "static", "address": "172.31.9.1", "prefix": 24}))
        text = render_preview(build_payload(p, self.topo))
        self.assertIn("nmcli connection modify", text)
        self.assertIn("|| true", text)                   # geri almadaki DHCP 'con up' yok sayilabilir


class WindowsPlatformLimits(unittest.TestCase):
    def test_bridge_unsupported_on_windows(self):
        topo = load("win-host.raw.json")
        eth = next(n.id for n in topo.nodes.values() if n.label == "ETH")
        cs = ChangeSet()
        cs.add(Change(ChangeKind.BRIDGE_CREATE, "br-np0", {"members": [eth]}))
        self.assertTrue(build_plan(cs, topo).blocked)

    def test_windows_dhcp_renew_script(self):
        from networkplus.platform.windows.apply import step_body
        topo = load("win-host.raw.json")
        wifi = next(n.id for n in topo.nodes.values() if n.label == "Wi-Fi")
        self.assertIn("ipconfig /renew", step_body(Change(ChangeKind.DHCP_RENEW, wifi, {})))


if __name__ == "__main__":
    unittest.main()
