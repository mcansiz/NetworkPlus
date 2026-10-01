"""DHCP paketi (RFC 2131 / 2132): cozumleme ve paketleme. Saf Python, yalniz stdlib.

qtDHCPserver'daki farklar: secenek 53 ilk yazilir (bazi istemciler bekler), 55 (istenen
parametre listesi), 61 (client-id), 58/59 (T1/T2) desteklenir.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass, field

MAGIC = b"\x63\x82\x53\x63"
BOOTREQUEST, BOOTREPLY = 1, 2
HEADER = struct.Struct("!BBBBIHH4s4s4s4s16s64s128s")      # 236 bayt
MIN_LEN = HEADER.size + len(MAGIC)

# Mesaj turleri (secenek 53)
DISCOVER, OFFER, REQUEST, DECLINE, ACK, NAK, RELEASE, INFORM = 1, 2, 3, 4, 5, 6, 7, 8
MSG_NAMES = {DISCOVER: "DISCOVER", OFFER: "OFFER", REQUEST: "REQUEST", DECLINE: "DECLINE",
             ACK: "ACK", NAK: "NAK", RELEASE: "RELEASE", INFORM: "INFORM"}

# Secenek kodlari
OPT_SUBNET, OPT_ROUTER, OPT_DNS, OPT_HOSTNAME, OPT_DOMAIN = 1, 3, 6, 12, 15
OPT_BROADCAST, OPT_REQUESTED_IP, OPT_LEASE_TIME, OPT_MSG_TYPE, OPT_SERVER_ID = 28, 50, 51, 53, 54
OPT_PARAM_LIST, OPT_MESSAGE, OPT_T1, OPT_T2, OPT_CLIENT_ID = 55, 56, 58, 59, 61
OPT_PAD, OPT_END = 0, 255


class PacketError(ValueError):
    pass


def ip_bytes(ip: str | None) -> bytes:
    return ipaddress.IPv4Address(ip or "0.0.0.0").packed


def ip_str(raw: bytes) -> str:
    return str(ipaddress.IPv4Address(raw))


def mac_str(chaddr: bytes, hlen: int) -> str:
    return ":".join(f"{b:02x}" for b in chaddr[:max(0, min(hlen, 16))])


def mac_bytes(mac: str) -> bytes:
    return bytes(int(x, 16) for x in mac.replace("-", ":").split(":"))


@dataclass
class Packet:
    op: int = BOOTREQUEST
    htype: int = 1
    hlen: int = 6
    hops: int = 0
    xid: int = 0
    secs: int = 0
    flags: int = 0
    ciaddr: str = "0.0.0.0"
    yiaddr: str = "0.0.0.0"
    siaddr: str = "0.0.0.0"
    giaddr: str = "0.0.0.0"
    chaddr: bytes = b"\x00" * 16
    options: dict[int, bytes] = field(default_factory=dict)

    # -- yardimcilar
    @property
    def mac(self) -> str:
        return mac_str(self.chaddr, self.hlen)

    @property
    def msg_type(self) -> int | None:
        v = self.options.get(OPT_MSG_TYPE)
        return v[0] if v else None

    @property
    def broadcast_flag(self) -> bool:
        return bool(self.flags & 0x8000)

    def opt_ip(self, code: int) -> str | None:
        v = self.options.get(code)
        return ip_str(v[:4]) if v and len(v) >= 4 else None

    def opt_text(self, code: int) -> str | None:
        v = self.options.get(code)
        if not v:
            return None
        return v.rstrip(b"\x00").decode("utf-8", "replace")   # qtDHCP Latin1 okuyordu

    @property
    def client_id(self) -> str:
        """Istemci kimligi: secenek 61 varsa o, yoksa MAC."""
        v = self.options.get(OPT_CLIENT_ID)
        return v.hex() if v else self.mac

    # -- paketleme
    def to_bytes(self) -> bytes:
        head = HEADER.pack(self.op, self.htype, self.hlen, self.hops, self.xid, self.secs, self.flags,
                           ip_bytes(self.ciaddr), ip_bytes(self.yiaddr), ip_bytes(self.siaddr),
                           ip_bytes(self.giaddr), self.chaddr.ljust(16, b"\x00")[:16],
                           b"\x00" * 64, b"\x00" * 128)
        opts = bytearray(MAGIC)
        order = sorted(self.options, key=lambda c: (c != OPT_MSG_TYPE, c))     # 53 ilk
        for code in order:
            value = self.options[code]
            for i in range(0, max(len(value), 1), 255):                      # >255 bayt: parcala
                chunk = value[i:i + 255]
                opts += bytes([code, len(chunk)]) + chunk
        opts.append(OPT_END)
        data = head + bytes(opts)
        return data.ljust(300, b"\x00")                                      # BOOTP en az 300


def parse(data: bytes) -> Packet:
    if len(data) < MIN_LEN:
        raise PacketError(f"kisa paket ({len(data)} bayt)")
    (op, htype, hlen, hops, xid, secs, flags, ci, yi, si, gi, ch, _sname, _file) = HEADER.unpack_from(data)
    if data[HEADER.size:MIN_LEN] != MAGIC:
        raise PacketError("magic cookie yok")
    options: dict[int, bytes] = {}
    i = MIN_LEN
    while i < len(data):
        code = data[i]
        if code == OPT_END:
            break
        if code == OPT_PAD:
            i += 1
            continue
        if i + 1 >= len(data):
            raise PacketError("secenek uzunlugu eksik")
        length = data[i + 1]
        value = data[i + 2:i + 2 + length]
        if len(value) != length:
            raise PacketError(f"secenek {code} kesik")
        options[code] = options.get(code, b"") + value     # RFC 3396: ayni kod birlestirilir
        i += 2 + length
    return Packet(op, htype, hlen, hops, xid, secs, flags, ip_str(ci), ip_str(yi), ip_str(si),
                  ip_str(gi), ch, options)


def u32(value: int) -> bytes:
    return struct.pack("!I", int(value))


def ip_list(ips: list[str]) -> bytes:
    return b"".join(ip_bytes(ip) for ip in ips)
