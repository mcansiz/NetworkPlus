"""DHCP sunucu mantigi (RFC 2131 4.3): paket gelir, yanit(lar) ve olaylar cikar. Soket YOK.

qtDHCPserver'a gore:
- REQUEST'te secenek 54 baska sunucuyu gosteriyorsa sessiz kalinir ve teklif geri alinir
  (qtDHCP ACK/NAK gonderiyordu: ayni agdaki baska sunucuya dusmanca).
- INIT-REBOOT / RENEW'de kaydi olmayan istemciye sessiz kalinir (RFC), yanlis IP'ye NAK.
- INFORM ve DECLINE islenir; T1/T2 gonderilir; ag gecidi/DNS istege bagli.
- Yanit hedefi RFC 4.1: giaddr -> relay; ciaddr -> unicast; aksi hâlde yayin.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from . import packet as P
from .leases import DhcpConfig, Lease, LeaseManager


@dataclass
class Reply:
    packet: P.Packet
    dest: str
    port: int


@dataclass
class Event:
    kind: str           # lease_new | lease_renew | release | decline | nak | exhausted | ignored | inform
    mac: str = ""
    ip: str = ""
    hostname: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "mac": self.mac, "ip": self.ip, "hostname": self.hostname, "detail": self.detail}


class DhcpServerCore:
    def __init__(self, cfg: DhcpConfig, leases: LeaseManager | None = None):
        self.cfg = cfg
        self.leases = leases or LeaseManager(cfg)

    # ----------------------------------------------------------------- yanit kurma
    def _options(self, kind: int, lease_time: int | None) -> dict[int, bytes]:
        cfg = self.cfg
        opts = {P.OPT_MSG_TYPE: bytes([kind]), P.OPT_SERVER_ID: P.ip_bytes(cfg.server_ip)}
        if kind == P.NAK:
            opts[P.OPT_MESSAGE] = b"networkPlus: address not available"
            return opts
        opts[P.OPT_SUBNET] = P.ip_bytes(cfg.netmask)
        opts[P.OPT_BROADCAST] = P.ip_bytes(cfg.broadcast)
        if cfg.gateway:
            opts[P.OPT_ROUTER] = P.ip_bytes(cfg.gateway)
        if cfg.dns:
            opts[P.OPT_DNS] = P.ip_list(cfg.dns)
        if cfg.domain:
            opts[P.OPT_DOMAIN] = cfg.domain.encode("ascii", "ignore")
        if lease_time:
            opts[P.OPT_LEASE_TIME] = P.u32(lease_time)
            opts[P.OPT_T1] = P.u32(lease_time // 2)
            opts[P.OPT_T2] = P.u32(lease_time * 7 // 8)
        return opts

    def _reply(self, req: P.Packet, kind: int, yiaddr: str = "0.0.0.0", lease_time: int | None = None) -> Reply:
        pkt = P.Packet(op=P.BOOTREPLY, htype=req.htype, hlen=req.hlen, xid=req.xid, flags=req.flags,
                       ciaddr=req.ciaddr if kind in (P.ACK,) else "0.0.0.0", yiaddr=yiaddr,
                       siaddr=self.cfg.server_ip if kind != P.NAK else "0.0.0.0",
                       giaddr=req.giaddr, chaddr=req.chaddr, options=self._options(kind, lease_time))
        if req.giaddr != "0.0.0.0":
            return Reply(pkt, req.giaddr, 67)                      # relay ajani
        if kind != P.NAK and req.ciaddr != "0.0.0.0":
            return Reply(pkt, req.ciaddr, 68)                      # RENEW / INFORM: unicast
        return Reply(pkt, "255.255.255.255", 68)                   # yayin

    # ----------------------------------------------------------------- isleme
    def handle(self, pkt: P.Packet, now: float) -> tuple[list[Reply], list[Event]]:
        if pkt.op != P.BOOTREQUEST or pkt.msg_type is None:
            return [], []
        mac, kind = pkt.mac, pkt.msg_type
        host = pkt.opt_text(P.OPT_HOSTNAME) or ""
        lt = int(self.cfg.lease_time)

        if kind == P.DISCOVER:
            lease = self.leases.offer(mac, pkt.opt_ip(P.OPT_REQUESTED_IP), host, now, pkt.client_id)
            if lease is None:
                return [], [Event("exhausted", mac, detail="pool exhausted")]   # RFC: NAK yok
            return [self._reply(pkt, P.OFFER, lease.ip, lt)], []

        if kind == P.REQUEST:
            server_id = pkt.opt_ip(P.OPT_SERVER_ID)
            requested = pkt.opt_ip(P.OPT_REQUESTED_IP)
            if server_id is not None:                                    # SELECTING
                if server_id != self.cfg.server_ip:
                    self.leases.cancel_offer(mac)                        # istemci baska sunucuyu secti
                    return [], [Event("ignored", mac, detail=f"other server {server_id}")]
                return self._ack_or_nak(pkt, requested, host, now)
            if requested and pkt.ciaddr == "0.0.0.0":                    # INIT-REBOOT
                return self._confirm_known(pkt, requested, host, now)
            if pkt.ciaddr != "0.0.0.0":                                  # RENEW / REBIND
                return self._confirm_known(pkt, pkt.ciaddr, host, now)
            return [], [Event("ignored", mac, detail="malformed REQUEST")]

        if kind == P.RELEASE:
            lease = self.leases.release(mac, pkt.ciaddr if pkt.ciaddr != "0.0.0.0" else None)
            return [], [Event("release", mac, lease.ip if lease else pkt.ciaddr, lease.hostname if lease else "")]

        if kind == P.DECLINE:
            ip = pkt.opt_ip(P.OPT_REQUESTED_IP) or ""
            if ip:
                self.leases.decline(mac, ip, now)
            return [], [Event("decline", mac, ip, detail="address in use (DECLINE)")]

        if kind == P.INFORM:
            return [self._reply(pkt, P.ACK)], [Event("inform", mac, pkt.ciaddr)]
        return [], []

    def _ack_or_nak(self, pkt, ip, host, now):
        lease, is_new = self.leases.request(pkt.mac, ip or "", host, now, pkt.client_id)
        if lease is None:
            return [self._reply(pkt, P.NAK)], [Event("nak", pkt.mac, ip or "")]
        ev = Event("lease_new" if is_new else "lease_renew", pkt.mac, lease.ip, lease.hostname)
        return [self._reply(pkt, P.ACK, lease.ip, int(self.cfg.lease_time))], [ev]

    def _confirm_known(self, pkt, ip, host, now):
        """INIT-REBOOT/RENEW: kaydi yoksa SESSIZ (RFC 2131 4.3.2); kayit baska IP ise NAK."""
        net = self.cfg.network
        if ipaddress.IPv4Address(ip) not in net:
            return [self._reply(pkt, P.NAK)], [Event("nak", pkt.mac, ip, detail="wrong subnet")]
        record: Lease | None = self.leases.leases.get(pkt.mac)
        reserved = self.leases._reserved_for(pkt.mac)
        if record is None and not reserved:
            return [], [Event("ignored", pkt.mac, ip, detail="no record")]
        if (record and record.ip != ip) or (reserved and reserved != ip):
            return [self._reply(pkt, P.NAK)], [Event("nak", pkt.mac, ip)]
        return self._ack_or_nak(pkt, ip, host, now)

    def tick(self, now: float) -> list[Event]:
        return [Event("expired", l.mac, l.ip, l.hostname) for l in self.leases.expire(now)]
