"""M2 cekirdek testleri: degisiklik kuyrugu, dogrulama, geri alma, betik uretimi.

Betik yalnizca METIN olarak denetlenir; hicbir komut calistirilmaz (ai_rules/20).
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus.core.changes import (                                   # noqa: E402
    Change, ChangeKind, ChangeSet, HOST_TARGET, build_plan, parse_prefix, prefix_to_mask,
)
from networkplus.core.discovery import build_topology                    # noqa: E402
from networkplus.core.model import Severity                              # noqa: E402
from networkplus.platform import render_apply_script                     # noqa: E402
from networkplus.platform.filesource import normalize_any                # noqa: E402
from networkplus.platform.windows.apply import ScriptError, ps, step_body  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def topo_from(raw):
    return build_topology(normalize_any(raw))


class Base(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((FIX / "win-host.raw.json").read_text(encoding="utf-8"))
        self.topo = topo_from(self.raw)
        self.id = {n.label: n.id for n in self.topo.nodes.values() if n.is_adapter}

    def plan(self, *changes):
        cs = ChangeSet()
        for c in changes:
            cs.add(c)
        return build_plan(cs, self.topo)

    def errors(self, plan):
        return [i.message for it in plan.items for i in it.issues if i.severity == Severity.ERROR]

    def warnings(self, plan):
        return [i.message for it in plan.items for i in it.issues if i.severity == Severity.WARNING]


class Helpers(unittest.TestCase):
    def test_prefix(self):
        self.assertEqual(parse_prefix("24"), 24)
        self.assertEqual(parse_prefix("/16"), 16)
        self.assertEqual(parse_prefix("255.255.255.0"), 24)
        self.assertIsNone(parse_prefix("255.0.255.0"))
        self.assertIsNone(parse_prefix("33"))
        self.assertEqual(prefix_to_mask(20), "255.255.240.0")

    def test_ps_quoting(self):
        self.assertEqual(ps("Ali'nin ağı"), "'Ali''nin ağı'")


class ChangeSetBehaviour(unittest.TestCase):
    def test_same_field_replaces(self):
        cs = ChangeSet()
        cs.add(Change(ChangeKind.MTU, "{A}", {"mtu": 1400}))
        cs.add(Change(ChangeKind.MTU, "{A}", {"mtu": 1300}))
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs.get(ChangeKind.MTU, "{A}").params["mtu"], 1300)

    def test_order_enable_first_disable_last(self):
        cs = ChangeSet()
        cs.add(Change(ChangeKind.ENABLED, "{B}", {"enabled": False}))
        cs.add(Change(ChangeKind.IPV4, "{A}", {"mode": "dhcp"}))
        cs.add(Change(ChangeKind.ENABLED, "{A}", {"enabled": True}))
        kinds = [(c.kind, c.params.get("enabled")) for c in cs]
        self.assertEqual(kinds[0], (ChangeKind.ENABLED, True))
        self.assertEqual(kinds[-1], (ChangeKind.ENABLED, False))


class Validation(Base):
    def test_static_ok_on_disconnected_eth(self):
        p = self.plan(Change(ChangeKind.IPV4, self.id["ETH"],
                             {"mode": "static", "address": "192.168.50.10", "prefix": 24,
                              "gateway": "192.168.50.1"}))
        self.assertEqual(self.errors(p), [])
        self.assertFalse(p.blocked)

    def test_gateway_outside_subnet(self):
        p = self.plan(Change(ChangeKind.IPV4, self.id["ETH"],
                             {"mode": "static", "address": "192.168.50.10", "prefix": 24,
                              "gateway": "192.168.51.1"}))
        self.assertTrue(p.blocked)

    def test_duplicate_ip_and_overlap(self):
        p = self.plan(Change(ChangeKind.IPV4, self.id["ETH"],
                             {"mode": "static", "address": "10.20.30.57", "prefix": 24}))
        self.assertTrue(any("zaten" in e for e in self.errors(p)))
        p = self.plan(Change(ChangeKind.IPV4, self.id["ETH"],
                             {"mode": "static", "address": "10.20.30.99", "prefix": 24}))
        self.assertFalse(p.blocked)
        self.assertTrue(any("çakışıyor" in w for w in self.warnings(p)))

    def test_network_address_rejected(self):
        p = self.plan(Change(ChangeKind.IPV4, self.id["ETH"],
                             {"mode": "static", "address": "192.168.50.0", "prefix": 24}))
        self.assertTrue(p.blocked)

    def test_disable_internet_adapter_warns(self):
        p = self.plan(Change(ChangeKind.ENABLED, self.id["Wi-Fi"], {"enabled": False}))
        self.assertFalse(p.blocked)
        self.assertTrue(any("internet" in w for w in self.warnings(p)))

    def test_rename_collision(self):
        p = self.plan(Change(ChangeKind.RENAME, self.id["ETH"], {"name": "wi-fi"}))
        self.assertTrue(p.blocked)

    def test_bad_dns_mtu_metric(self):
        eth = self.id["ETH"]
        p = self.plan(Change(ChangeKind.DNS4, eth, {"mode": "manual", "servers": ["8.8.8.8", "x"]}),
                      Change(ChangeKind.MTU, eth, {"mtu": 100}),
                      Change(ChangeKind.METRIC, eth, {"auto": False, "metric": 0}))
        self.assertEqual(len(self.errors(p)), 3)

    def test_ics_plan_warnings(self):
        p = self.plan(Change(ChangeKind.ICS, HOST_TARGET,
                             {"public": self.id["Wi-Fi"], "private": self.id["ETH"]}))
        self.assertFalse(p.blocked)
        w = " ".join(self.warnings(p))
        self.assertIn("192.168.1.1/24", w)          # kapsam okunur
        self.assertIn("192.168.1.2", w)             # ezilecek statik adres

    def test_ics_same_adapter_blocked(self):
        p = self.plan(Change(ChangeKind.ICS, HOST_TARGET,
                             {"public": self.id["Wi-Fi"], "private": self.id["Wi-Fi"]}))
        self.assertTrue(p.blocked)


class Confirmation(Base):
    def test_ipv4_on_up_adapter_risky_only_with_address(self):
        """Bagli kartta IP degisikligi uzak baglantiyi koparabilir; adresi yoksa (DHCP sunucusu
        kurulacak yalitilmis kart) kopacak baglanti yoktur -> onaysiz (ADR 0010)."""
        from networkplus.core.changes import needs_confirmation
        from networkplus.core.model import Status
        vm = self.id["Ethernet 3"]                     # bagli, statik 192.168.56.1
        change = Change(ChangeKind.IPV4, vm, {"mode": "static", "address": "192.168.56.9", "prefix": 24,
                                              "gateway": None})
        self.assertEqual(self.topo.nodes[vm].status, Status.UP)
        self.assertTrue(needs_confirmation(self.plan(change), self.topo)[0])
        self.topo.nodes[vm].props["ipv4"] = [{"address": "169.254.10.1", "prefix": 16, "origin": "link_local"}]
        self.assertFalse(needs_confirmation(self.plan(change), self.topo)[0])
        self.topo.nodes[vm].props["ipv4"] = []
        self.assertFalse(needs_confirmation(self.plan(change), self.topo)[0])


class Rollback(Base):
    def test_ics_rollback_restores_private_ip(self):
        p = self.plan(Change(ChangeKind.ICS, HOST_TARGET,
                             {"public": self.id["Wi-Fi"], "private": self.id["ETH"]}))
        kinds = [(c.kind, c.params) for c in p.rollback]
        self.assertEqual(kinds[0], (ChangeKind.ICS, {"public": None, "private": None}))
        self.assertEqual(kinds[1][0], ChangeKind.IPV4)
        self.assertEqual(kinds[1][1]["address"], "192.168.1.2")
        self.assertEqual(kinds[1][1]["mode"], "static")

    def test_wifi_rollback_is_dhcp_and_auto_metric(self):
        wifi = self.id["Wi-Fi"]
        p = self.plan(Change(ChangeKind.IPV4, wifi, {"mode": "static", "address": "10.20.30.200", "prefix": 24,
                                                     "gateway": "10.20.30.253"}),
                      Change(ChangeKind.METRIC, wifi, {"auto": False, "metric": 5}))
        rb = {c.kind: c.params for c in p.rollback}
        self.assertEqual(rb[ChangeKind.IPV4], {"mode": "dhcp"})
        self.assertEqual(rb[ChangeKind.METRIC], {"auto": True})

    def test_radmin_manual_metric_rollback(self):
        p = self.plan(Change(ChangeKind.METRIC, self.id["Radmin VPN"], {"auto": True}))
        self.assertEqual(p.rollback[0].params, {"auto": False, "metric": 1})

    def test_dns_manual_detection(self):
        raw = copy.deepcopy(self.raw)
        eth_guid = next(a["guid"] for a in raw["adapters"] if a["name"] == "ETH")
        raw["dns_static"] = [{"guid": eth_guid, "name_server": "1.1.1.1,8.8.8.8"}]
        idx = next(a["index"] for a in raw["adapters"] if a["name"] == "ETH")
        raw["dns"].append({"index": idx, "family": 2, "servers": ["1.1.1.1", "8.8.8.8"]})
        self.topo = topo_from(raw)
        p = self.plan(Change(ChangeKind.DNS4, eth_guid, {"mode": "auto"}))
        self.assertEqual(p.rollback[0].params, {"mode": "manual", "servers": ["1.1.1.1", "8.8.8.8"]})


class Script(Base):
    def test_render_full_script(self):
        wifi, eth = self.id["Wi-Fi"], self.id["ETH"]
        p = self.plan(Change(ChangeKind.ICS, HOST_TARGET, {"public": wifi, "private": eth}),
                      Change(ChangeKind.RENAME, eth, {"name": "Paylaşım'lı ETH"}),
                      Change(ChangeKind.DNS4, eth, {"mode": "manual", "servers": ["1.1.1.1"]}))
        s = render_apply_script(p, self.topo)
        self.assertIn("param([Parameter(Mandatory = $true)][string]$WorkDir, [int]$ConfirmSeconds = 30)", s)
        self.assertIn(f"Enable-Sharing -Public '{wifi}' -Private '{eth}'", s)
        self.assertIn("Rename-NetAdapter -NewName 'Paylaşım''lı ETH'", s)
        self.assertIn("-ServerAddresses @('1.1.1.1')", s)
        self.assertIn("Set-Ipv4Static -Index $i -Address '192.168.1.2' -Prefix 24", s)   # geri alma
        self.assertIn("EnableRebootPersistConnection", s)
        self.assertEqual(s.count("$ApplySteps = @("), 1)
        self.assertEqual(s.count("$RollbackSteps = @("), 1)
        # Uygula bolumu geri alma bolumunden once
        self.assertLess(s.index("Enable-Sharing -Public"), s.index("$RollbackSteps = @("))

    def test_injection_rejected(self):
        with self.assertRaises(ScriptError):
            step_body(Change(ChangeKind.DNS4, self.id["ETH"], {"mode": "manual", "servers": ["1.1.1.1'; rm x"]}))
        with self.assertRaises(ScriptError):
            step_body(Change(ChangeKind.MTU, "notaguid; Stop-Computer", {"mtu": 1500}))


if __name__ == "__main__":
    unittest.main()
