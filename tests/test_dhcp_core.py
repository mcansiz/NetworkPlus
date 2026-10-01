"""DHCP cekirdegi (ADR 0010): paket, havuz/kira, sunucu mantigi. Soket yok, sistem degismez."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus.core.dhcp import packet as P                           # noqa: E402
from networkplus.core.dhcp.leases import (                              # noqa: E402
    OFFER_TTL, DhcpConfig, LeaseManager, pool_addresses, suggest_config, validate_config,
)
from networkplus.core.dhcp.server import DhcpServerCore                  # noqa: E402

MAC1, MAC2 = "02:00:00:00:00:01", "02:00:00:00:00:02"


def cfg(**kw) -> DhcpConfig:
    base = dict(server_ip="10.50.0.1", prefix=24, pool_start="10.50.0.100", pool_end="10.50.0.102",
                dns=["10.50.0.1"], lease_time=600)
    base.update(kw)
    return DhcpConfig(**base)


def client(kind, mac=MAC1, xid=0x1234, requested=None, server=None, ciaddr="0.0.0.0", host=None, flags=0):
    opts = {P.OPT_MSG_TYPE: bytes([kind])}
    if requested:
        opts[P.OPT_REQUESTED_IP] = P.ip_bytes(requested)
    if server:
        opts[P.OPT_SERVER_ID] = P.ip_bytes(server)
    if host:
        opts[P.OPT_HOSTNAME] = host.encode()
    pkt = P.Packet(op=P.BOOTREQUEST, xid=xid, ciaddr=ciaddr, flags=flags,
                   chaddr=P.mac_bytes(mac).ljust(16, b"\x00"), options=opts)
    return P.parse(pkt.to_bytes())            # gercek gidis-donus


class PacketTests(unittest.TestCase):
    def test_roundtrip_and_option_order(self):
        pkt = client(P.DISCOVER, host="cihaz-1", requested="10.50.0.101")
        data = pkt.to_bytes()
        self.assertGreaterEqual(len(data), 300)
        self.assertEqual(data[240:243], bytes([P.OPT_MSG_TYPE, 1, P.DISCOVER]))   # 53 ilk secenek
        back = P.parse(data)
        self.assertEqual((back.mac, back.msg_type, back.opt_text(P.OPT_HOSTNAME), back.opt_ip(P.OPT_REQUESTED_IP)),
                         (MAC1, P.DISCOVER, "cihaz-1", "10.50.0.101"))

    def test_bad_packets(self):
        with self.assertRaises(P.PacketError):
            P.parse(b"\x01" * 100)
        data = bytearray(client(P.DISCOVER).to_bytes())
        data[236:240] = b"\x00\x00\x00\x00"
        with self.assertRaises(P.PacketError):
            P.parse(bytes(data))


class ConfigTests(unittest.TestCase):
    def test_valid_and_pool(self):
        self.assertEqual(validate_config(cfg()), [])
        self.assertEqual(pool_addresses(cfg()), ["10.50.0.100", "10.50.0.101", "10.50.0.102"])

    def test_single_ip_pool_ok_and_server_excluded(self):
        self.assertEqual(validate_config(cfg(pool_start="10.50.0.100", pool_end="10.50.0.100")), [])
        c = cfg(pool_start="10.50.0.1", pool_end="10.50.0.2")
        self.assertEqual(pool_addresses(c), ["10.50.0.2"])            # sunucu IP'si haric

    def test_errors(self):
        self.assertTrue(validate_config(cfg(pool_start="10.60.0.5")))          # alt ag disi
        self.assertTrue(validate_config(cfg(pool_start="10.50.0.200")))        # baslangic > bitis
        self.assertTrue(validate_config(cfg(gateway="10.99.0.1")))
        self.assertTrue(validate_config(cfg(lease_time=10)))
        self.assertTrue(validate_config(cfg(reservations={MAC1: {"ip": "10.50.0.1"}})))   # sunucu IP'si
        self.assertTrue(validate_config(cfg(reservations={MAC1: {"ip": "10.50.0.50"},
                                                          MAC2: {"ip": "10.50.0.50"}})))
        self.assertEqual(validate_config(cfg(gateway=None, dns=[])), [])     # gecit/DNS istege bagli

    def test_suggestion_fits_subnet(self):
        s = suggest_config("192.168.1.1", 24)
        self.assertEqual((s.pool_start, s.pool_end), ("192.168.1.100", "192.168.1.200"))
        s = suggest_config("10.0.0.1", 25)                           # qtDHCP +200 ile yayini asiyordu
        self.assertEqual(validate_config(s), [])
        self.assertIsNone(s.gateway)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.srv = DhcpServerCore(cfg())

    def dora(self, mac=MAC1, host=None, now=1000.0):
        replies, _ = self.srv.handle(client(P.DISCOVER, mac=mac, host=host), now)
        offer = replies[0].packet
        self.assertEqual(offer.msg_type, P.OFFER)
        replies, events = self.srv.handle(client(P.REQUEST, mac=mac, requested=offer.yiaddr,
                                                 server="10.50.0.1", host=host), now)
        return offer, replies[0], events

    def test_dora_options_and_broadcast(self):
        offer, ack, events = self.dora(host="plc-1")
        self.assertEqual(ack.packet.msg_type, P.ACK)
        self.assertEqual(ack.packet.yiaddr, "10.50.0.100")
        self.assertEqual((ack.dest, ack.port), ("255.255.255.255", 68))
        o = ack.packet.options
        self.assertEqual(o[P.OPT_SUBNET], P.ip_bytes("255.255.255.0"))
        self.assertNotIn(P.OPT_ROUTER, o)                          # gecit verilmedi -> gonderilmez
        self.assertEqual(o[P.OPT_T1], P.u32(300))
        self.assertEqual([e.kind for e in events], ["lease_new"])
        self.assertEqual(events[0].hostname, "plc-1")

    def test_renew_is_unicast_and_not_new(self):
        _o, ack, _e = self.dora()
        replies, events = self.srv.handle(client(P.REQUEST, ciaddr=ack.packet.yiaddr), 1300.0)
        self.assertEqual(replies[0].packet.msg_type, P.ACK)
        self.assertEqual(replies[0].dest, ack.packet.yiaddr)
        self.assertEqual([e.kind for e in events], ["lease_renew"])   # yeni cihaz bildirimi yok

    def test_other_server_selected_is_silent_and_frees_offer(self):
        replies, _ = self.srv.handle(client(P.DISCOVER), 1000.0)
        ip = replies[0].packet.yiaddr
        replies, events = self.srv.handle(client(P.REQUEST, requested=ip, server="10.50.0.254"), 1000.5)
        self.assertEqual(replies, [])                              # qtDHCP burada ACK/NAK gonderiyordu
        self.assertNotIn(MAC1, self.srv.leases.leases)

    def test_offer_expires_no_pool_leak(self):
        for i in range(3):
            self.srv.handle(client(P.DISCOVER, mac=f"02:00:00:00:01:0{i}"), 1000.0)   # REQUEST yok
        replies, events = self.srv.handle(client(P.DISCOVER, mac=MAC2), 1001.0)
        self.assertEqual(replies, [])
        self.assertEqual(events[0].kind, "exhausted")
        self.srv.tick(1000.0 + OFFER_TTL + 1)                      # teklifler duser
        replies, _ = self.srv.handle(client(P.DISCOVER, mac=MAC2), 1000.0 + OFFER_TTL + 2)
        self.assertEqual(replies[0].packet.msg_type, P.OFFER)

    def test_reservation(self):
        srv = DhcpServerCore(cfg(reservations={MAC2: {"ip": "10.50.0.50", "name": "kamera"}}))
        replies, _ = srv.handle(client(P.DISCOVER, mac=MAC2), 1000.0)
        self.assertEqual(replies[0].packet.yiaddr, "10.50.0.50")     # havuz disi da olabilir
        replies, _ = srv.handle(client(P.REQUEST, mac=MAC2, requested="10.50.0.100", server="10.50.0.1"), 1000.0)
        self.assertEqual(replies[0].packet.msg_type, P.NAK)          # rezerveli cihaz baska IP isteyemez
        replies, _ = srv.handle(client(P.DISCOVER, mac=MAC1, requested="10.50.0.50"), 1000.0)
        self.assertNotEqual(replies[0].packet.yiaddr, "10.50.0.50")  # baskasinin rezervi verilmez

    def test_init_reboot_rules(self):
        replies, events = self.srv.handle(client(P.REQUEST, requested="10.50.0.101"), 1000.0)
        self.assertEqual(replies, [])                              # kayit yok -> sessiz (RFC)
        replies, _ = self.srv.handle(client(P.REQUEST, requested="192.168.9.9"), 1000.0)
        self.assertEqual(replies[0].packet.msg_type, P.NAK)        # yanlis alt ag -> NAK
        _o, ack, _e = self.dora()
        replies, _ = self.srv.handle(client(P.REQUEST, requested=ack.packet.yiaddr), 1100.0)
        self.assertEqual(replies[0].packet.msg_type, P.ACK)

    def test_same_client_gets_same_ip_after_restart(self):
        _o, ack, _e = self.dora()
        saved = self.srv.leases.to_list()
        fresh = LeaseManager(cfg())
        fresh.load(saved)
        srv2 = DhcpServerCore(cfg(), fresh)
        replies, _ = srv2.handle(client(P.DISCOVER), 5000.0)
        self.assertEqual(replies[0].packet.yiaddr, ack.packet.yiaddr)

    def test_decline_quarantine_and_release(self):
        replies, _ = self.srv.handle(client(P.DISCOVER), 1000.0)
        ip = replies[0].packet.yiaddr
        self.srv.handle(client(P.DECLINE, requested=ip, server="10.50.0.1"), 1000.0)
        replies, _ = self.srv.handle(client(P.DISCOVER, mac=MAC2), 1001.0)
        self.assertNotEqual(replies[0].packet.yiaddr, ip)
        _o, ack, _e = self.dora(mac=MAC2, now=1002.0)
        _r, events = self.srv.handle(client(P.RELEASE, mac=MAC2, ciaddr=ack.packet.yiaddr), 1003.0)
        self.assertEqual(events[0].kind, "release")
        self.assertEqual(self.srv.leases.leases[MAC2].state, "released")

    def test_inform_and_expiry_event(self):
        replies, _ = self.srv.handle(client(P.INFORM, ciaddr="10.50.0.7"), 1000.0)
        r = replies[0]
        self.assertEqual((r.packet.msg_type, r.packet.yiaddr, r.dest), (P.ACK, "0.0.0.0", "10.50.0.7"))
        self.assertNotIn(P.OPT_LEASE_TIME, r.packet.options)
        self.dora(now=2000.0)
        events = self.srv.tick(2000.0 + 601)
        self.assertEqual([e.kind for e in events], ["expired"])


class DaemonPipe(unittest.TestCase):
    def test_output_is_utf8_whatever_the_locale(self):
        """Windows'ta boru yerel kod sayfasiyla (cp1254) yaziliyordu: Turkce hata metni bozuk
        geliyordu. Gecersiz ayar -> soket ACILMADAN cikar; sistem degismez."""
        import json
        import os
        import subprocess
        work = ROOT / ".tmp" / "test"
        work.mkdir(parents=True, exist_ok=True)
        cfg = work / "daemon-bad.json"
        cfg.write_text(json.dumps({"server_ip": "999.1.1.1", "prefix": 24, "pool_start": "a", "pool_end": "b"}),
                       encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        r = subprocess.run([sys.executable, str(ROOT / "src" / "networkplus" / "platform" / "dhcp_daemon.py"),
                            "--src", str(ROOT / "src"), "--config", str(cfg), "--leases", str(work / "daemon-leases.json")],
                           capture_output=True, timeout=60, env=env, stdin=subprocess.DEVNULL)
        text = r.stdout.decode("utf-8")                               # kati: bozuk bayt hata verir
        event = json.loads(text.splitlines()[0])
        self.assertEqual((r.returncode, event["code"]), (2, "config"))
        self.assertIn("Geçersiz", event["detail"])


if __name__ == "__main__":
    unittest.main()
