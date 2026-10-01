"""Cekirdek testleri: fixture JSON ile, isletim sistemine dokunmadan.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus.core.classify import classify                         # noqa: E402
from networkplus.core.discovery import INTERNET_ID, build_topology      # noqa: E402
from networkplus.core.layout import COL_X, compute_layout               # noqa: E402
from networkplus.core.model import EdgeKind, NodeKind, Status           # noqa: E402
from networkplus.platform.filesource import normalize_any               # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def by_label(topo, label):
    return next(n for n in topo.nodes.values() if n.label == label)


class WindowsHostFixture(unittest.TestCase):
    """Gelistirme makinesinin anonim goruntusu (2026-09-30)."""

    @classmethod
    def setUpClass(cls):
        cls.raw = load("win-host.raw.json")
        cls.snap = normalize_any(cls.raw)
        cls.topo = build_topology(cls.snap)

    def test_normalized_basics(self):
        self.assertEqual(self.snap["platform"], "windows")
        self.assertEqual(len(self.snap["adapters"]), 23)
        wifi = next(a for a in self.snap["adapters"] if a["name"] == "Wi-Fi")
        self.assertTrue(wifi["dhcp4"])
        self.assertEqual(wifi["connectivity"], "internet")
        self.assertEqual(wifi["metric4"], 35)
        self.assertEqual(self.snap["sharing"]["scope"], "192.168.1.1")

    def test_turkish_names_survive(self):
        names = [a["name"] for a in self.snap["adapters"]]
        self.assertIn("Bluetooth Ağ Bağlantısı", names)

    def test_classification(self):
        t = self.topo
        self.assertEqual(by_label(t, "ETH").kind, NodeKind.ETHERNET)   # "Realtek" != LTE
        self.assertEqual(by_label(t, "Wi-Fi").kind, NodeKind.WIFI)
        self.assertEqual(by_label(t, "Radmin VPN").kind, NodeKind.VPN)
        self.assertEqual(by_label(t, "VMware Network Adapter VMnet8").kind, NodeKind.VM_NAT)
        self.assertEqual(by_label(t, "VMware Network Adapter VMnet1").kind, NodeKind.VM_HOST_ONLY)
        self.assertEqual(by_label(t, "Ethernet 3").kind, NodeKind.VM_HOST_ONLY)   # VirtualBox
        self.assertEqual(by_label(t, "Teredo Tunneling Pseudo-Interface").kind, NodeKind.SYSTEM)

    def test_hidden_defaults(self):
        visible = {n.label for n in self.topo.visible_nodes()}
        self.assertIn("ETH", visible)
        self.assertNotIn("Teredo Tunneling Pseudo-Interface", visible)
        self.assertNotIn("Ethernet 2", visible)            # Fortinet, Not Present

    def test_internet_path(self):
        t = self.topo
        self.assertEqual(t.nodes[t.internet_via].label, "Wi-Fi")
        active = [e for e in t.edges if e.active]
        kinds = {e.kind for e in active}
        self.assertEqual(kinds, {EdgeKind.INTERNET, EdgeKind.UPLINK})
        self.assertTrue(any(e.src == INTERNET_ID for e in active))

    def test_relations(self):
        t = self.topo
        wifi = by_label(t, "Wi-Fi")
        nat = [e for e in t.edges if e.kind == EdgeKind.NAT]
        self.assertEqual([(e.src, t.nodes[e.dst].label) for e in nat],
                         [(wifi.id, "VMware Network Adapter VMnet8")])
        tunnels = [e for e in t.edges if e.kind == EdgeKind.TUNNEL]
        self.assertEqual([t.nodes[e.dst].label for e in tunnels], ["Radmin VPN"])
        self.assertFalse([e for e in t.edges if e.kind == EdgeKind.ICS])

    def test_badges(self):
        eth = by_label(self.topo, "ETH")
        self.assertIn("static_no_link", [b.code for b in eth.badges])
        self.assertIn("multiple_default_routes", [b.code for b in self.topo.host_badges])

    def test_layout_columns(self):
        pos = compute_layout(self.topo)
        self.assertEqual(pos[INTERNET_ID][0], COL_X[0])
        wifi = by_label(self.topo, "Wi-Fi")
        self.assertEqual(pos[wifi.id], (COL_X[2], 0.0))     # etkin cikis en ustte
        self.assertEqual(pos[by_label(self.topo, "ETH").id][0], COL_X[3])
        self.assertEqual(len(set(pos.values())), len(pos))  # cakisan konum yok


class IcsScenario(unittest.TestCase):
    """S1: Wi-Fi -> ETH internet paylasimi (fixture'dan turetilmis senaryo)."""

    def setUp(self):
        raw = copy.deepcopy(load("win-host.raw.json"))
        guid = {a["name"]: a["guid"] for a in raw["adapters"]}
        for c in raw["ics"]:
            if c["name"] == "Wi-Fi":
                c.update(enabled=True, type=0)
            if c["name"] == "ETH":
                c.update(enabled=True, type=1)
        self.raw, self.guid = raw, guid

    def test_ics_edge(self):
        t = build_topology(normalize_any(self.raw))
        ics = [e for e in t.edges if e.kind == EdgeKind.ICS]
        self.assertEqual(len(ics), 1)
        self.assertEqual((ics[0].src, ics[0].dst), (self.guid["Wi-Fi"], self.guid["ETH"]))
        self.assertIn("192.168.1.1", ics[0].label)         # kapsam okunur, 137.1 varsayilmaz
        self.assertTrue(ics[0].active)

    def test_ics_service_stopped_badge(self):
        for s in self.raw["services"]:
            if s["name"] == "SharedAccess":
                s["status"] = "Stopped"
        t = build_topology(normalize_any(self.raw))
        eth = t.nodes[self.guid["ETH"]]
        self.assertIn("ics_service_stopped", [b.code for b in eth.badges])

    def test_hotspot_via_wifi_direct(self):
        wd = next(a for a in self.raw["adapters"] if a["name"] == "Yerel Ağ Bağlantısı* 10")
        wd["status"] = "Up"
        for c in self.raw["ics"]:
            if c["name"] == "ETH":
                c.update(enabled=False)
        self.raw["ics"].append({"name": wd["name"], "guid": wd["guid"], "device": wd["description"],
                                "enabled": True, "type": 1})
        t = build_topology(normalize_any(self.raw))
        hs = [e for e in t.edges if e.kind == EdgeKind.HOTSPOT]
        self.assertEqual(len(hs), 1)
        self.assertEqual(t.nodes[hs[0].dst].kind, NodeKind.HOTSPOT)
        self.assertFalse(t.nodes[hs[0].dst].hidden)       # iliskiye katilan gizli dugum gorunur


class Badges(unittest.TestCase):
    def test_apipa_and_conflict(self):
        raw = copy.deepcopy(load("win-host.raw.json"))
        idx = {a["name"]: a["index"] for a in raw["adapters"]}
        for a in raw["adapters"]:
            if a["name"] == "ETH":
                a["status"] = "Up"
        raw["ip_addresses"] = [x for x in raw["ip_addresses"] if x["index"] != idx["ETH"]]
        raw["ip_addresses"].append({"index": idx["ETH"], "address": "169.254.10.20", "prefix": 16,
                                    "family": "IPv4", "origin": "WellKnown"})
        raw["ip_addresses"].append({"index": idx["Ethernet 3"], "address": "10.20.30.57", "prefix": 24,
                                    "family": "IPv4", "origin": "Manual"})
        for x in raw["ip_interfaces"]:
            if x["index"] == idx["ETH"] and x["family"] == "IPv4":
                x["dhcp"] = "Enabled"
        t = build_topology(normalize_any(raw))
        eth = by_label(t, "ETH")
        self.assertIn("apipa", [b.code for b in eth.badges])
        self.assertIn("ip_conflict", [b.code for b in by_label(t, "Wi-Fi").badges])
        self.assertIn("duplicate_subnet", [b.code for b in by_label(t, "Ethernet 3").badges])


class Classification(unittest.TestCase):
    def test_windows_descriptions(self):
        cases = {
            "Intel(R) Ethernet Connection I219-LM": NodeKind.ETHERNET,
            "Realtek USB GbE Family Controller": NodeKind.ETHERNET,
            "Qualcomm Snapdragon X55 LTE Modem": NodeKind.CELLULAR,
            "TAP-Windows Adapter V9": NodeKind.VPN,
            "WireGuard Tunnel": NodeKind.VPN,
            "Hyper-V Virtual Ethernet Adapter": NodeKind.VETHERNET,
            "Microsoft Wi-Fi Direct Virtual Adapter #2": NodeKind.HOTSPOT,
            "WAN Miniport (IKEv2)": NodeKind.SYSTEM,
        }
        for desc, kind in cases.items():
            with self.subTest(desc=desc):
                self.assertEqual(classify({"description": desc, "name": "x",
                                           "hints": {"media_type": "802.3"}}, "windows"), kind)

    def test_default_switch_is_nat(self):
        a = {"description": "Hyper-V Virtual Ethernet Adapter", "name": "vEthernet (Default Switch)"}
        self.assertEqual(classify(a, "windows"), NodeKind.VM_NAT)


class LinuxSynthetic(unittest.TestCase):
    """SENTETIK Linux fixture: Mint VM ciktisiyla degistirilecek (VM'de dogrulanmadi)."""

    def test_shared_connection(self):
        t = build_topology(normalize_any(load("linux-synthetic.raw.json")))
        self.assertEqual(t.internet_via, "enp0s3")
        self.assertEqual(t.nodes["enp0s3"].kind, NodeKind.ETHERNET)
        self.assertEqual(t.nodes["enp0s3"].status, Status.UP)
        self.assertEqual(t.nodes["virbr0"].kind, NodeKind.VM_NAT)
        self.assertEqual(t.nodes["br0"].kind, NodeKind.BRIDGE)
        ics = [e for e in t.edges if e.kind == EdgeKind.ICS]
        self.assertEqual([(e.src, e.dst) for e in ics], [("enp0s3", "enp0s8")])
        self.assertIn("10.42.0.1", ics[0].label)
        bridge = [e for e in t.edges if e.kind == EdgeKind.BRIDGE]
        self.assertEqual([(e.src, e.dst) for e in bridge], [("enp0s9", "br0")])
        self.assertTrue(t.nodes["lo"].hidden)


if __name__ == "__main__":
    unittest.main()
