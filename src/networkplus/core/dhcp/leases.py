"""DHCP havuzu ve kiralar: yapilandirma, dogrulama, ayirma, rezervasyon, kalicilik. Saf Python.

qtDHCPserver'daki hatalarin karsiligi:
- Teklif (OFFER) 60 sn sonra duser; REQUEST gelmezse IP havuza doner (sizinti yok).
- Havuz alt ag icinde olmali; sunucu/ag/yayin adresi otomatik disarida; tek IP'lik havuz gecerli.
- DECLINE edilen IP 10 dk karantinada (baska cihaz kullaniyor).
- Kiralar JSON ile kalici; sunucu yeniden baslayinca ayni cihaz ayni IP'yi alir.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass, field

from ..i18n import tr

OFFER_TTL = 60
DECLINE_QUARANTINE = 600
LEASE_RANGE = (60, 30 * 24 * 3600)
_MAC_RE = re.compile(r"^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$", re.I)


def norm_mac(mac: str) -> str:
    return mac.strip().lower().replace("-", ":")


@dataclass
class DhcpConfig:
    server_ip: str
    prefix: int
    pool_start: str
    pool_end: str
    gateway: str | None = None                  # qtDHCP'de zorunluydu; izole agda rota bozar
    dns: list[str] = field(default_factory=list)
    lease_time: int = 86400
    domain: str | None = None
    interface: str = ""                         # Windows: GUID, Linux: arayuz adi
    ifname: str = ""                            # Linux SO_BINDTODEVICE icin
    reservations: dict[str, dict] = field(default_factory=dict)   # mac -> {"ip", "name"}

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Interface(f"{self.server_ip}/{self.prefix}").network

    @property
    def netmask(self) -> str:
        return str(self.network.netmask)

    @property
    def broadcast(self) -> str:
        return str(self.network.broadcast_address)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DhcpConfig":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        cfg = cls(**known)
        cfg.reservations = {norm_mac(m): dict(v) for m, v in (cfg.reservations or {}).items()}
        return cfg


def _ip(value):
    try:
        return ipaddress.IPv4Address(str(value).strip())
    except (ipaddress.AddressValueError, ValueError):
        return None


def pool_addresses(cfg: DhcpConfig) -> list[str]:
    """Havuzdaki dagitilabilir adresler (sunucu, ag ve yayin adresi haric)."""
    net = cfg.network
    start, end = _ip(cfg.pool_start), _ip(cfg.pool_end)
    if start is None or end is None or start > end:
        return []
    skip = {net.network_address, net.broadcast_address, _ip(cfg.server_ip)}
    out = []
    for n in range(int(start), int(end) + 1):
        ip = ipaddress.IPv4Address(n)
        if ip in net and ip not in skip:
            out.append(str(ip))
        if len(out) > 65534:
            break
    return out


def validate_config(cfg: DhcpConfig) -> list[str]:
    errors: list[str] = []
    server = _ip(cfg.server_ip)
    if server is None:
        return [tr("Geçersiz sunucu IP adresi: {value}").format(value=repr(cfg.server_ip))]
    if not isinstance(cfg.prefix, int) or not 1 <= cfg.prefix <= 30:
        return [tr("Alt ağ maskesi geçersiz.")]
    net = cfg.network
    start, end = _ip(cfg.pool_start), _ip(cfg.pool_end)
    if start is None or end is None:
        errors.append(tr("Havuz başlangıç ve bitiş adresleri girilmeli."))
    else:
        if start not in net or end not in net:
            errors.append(tr("Havuz {net} alt ağının içinde olmalı.").format(net=net))
        if start > end:
            errors.append(tr("Havuz başlangıcı bitişten büyük olamaz."))
        if not errors and not pool_addresses(cfg):
            errors.append(tr("Havuzda dağıtılabilir adres kalmıyor (sunucu/ağ/yayın adresi hariç)."))
    if cfg.gateway:
        gw = _ip(cfg.gateway)
        if gw is None or gw not in net:
            errors.append(tr("Ağ geçidi {net} alt ağında olmalı.").format(net=net))
    for d in cfg.dns:
        if _ip(d) is None:
            errors.append(tr("Geçersiz DNS sunucusu: {value}").format(value=repr(d)))
    if not LEASE_RANGE[0] <= int(cfg.lease_time) <= LEASE_RANGE[1]:
        errors.append(tr("Kira süresi {low}–{high} sn arasında olmalı.").format(low=LEASE_RANGE[0], high=LEASE_RANGE[1]))
    seen: dict[str, str] = {}
    for mac, r in cfg.reservations.items():
        ip = _ip(r.get("ip"))
        if not _MAC_RE.match(mac):
            errors.append(tr("Geçersiz MAC adresi: {mac}").format(mac=mac))
        if ip is None or ip not in net or ip == server or ip in (net.network_address, net.broadcast_address):
            errors.append(tr("Rezervasyon adresi geçersiz: {mac} → {ip}").format(mac=mac, ip=r.get("ip")))
        elif str(ip) in seen:
            errors.append(tr("{ip} iki cihaza rezerve edilmiş ({a}, {b}).").format(ip=ip, a=seen[str(ip)], b=mac))
        else:
            seen[str(ip)] = mac
    return errors


def suggest_config(server_ip: str, prefix: int) -> DhcpConfig:
    """Karta gore oneri: havuz agin .100–.200 araligi (alt aga kirpilmis), gecit/DNS bos."""
    net = ipaddress.IPv4Interface(f"{server_ip}/{prefix}").network
    first, last = int(net.network_address) + 1, int(net.broadcast_address) - 1
    size = last - first + 1
    if size >= 200:
        start, end = first + 99, min(first + 199, last)
    else:                                         # kucuk ag: ust yari
        start, end = first + size // 2, last
    return DhcpConfig(server_ip=server_ip, prefix=prefix,
                      pool_start=str(ipaddress.IPv4Address(start)), pool_end=str(ipaddress.IPv4Address(end)))


@dataclass
class Lease:
    mac: str
    ip: str
    hostname: str = ""
    start: float = 0.0
    expires: float = 0.0
    state: str = "offered"          # offered | bound | released | expired
    client_id: str = ""

    def active(self, now: float) -> bool:
        return self.state in ("offered", "bound") and self.expires > now


class LeaseManager:
    def __init__(self, cfg: DhcpConfig):
        self.cfg = cfg
        self.leases: dict[str, Lease] = {}
        self.declined: dict[str, float] = {}

    # ----------------------------------------------------------------- yardimcilar
    def _reserved_for(self, mac: str) -> str | None:
        r = self.cfg.reservations.get(norm_mac(mac))
        return r.get("ip") if r else None

    def _reserved_ips(self) -> dict[str, str]:
        return {r.get("ip"): m for m, r in self.cfg.reservations.items() if r.get("ip")}

    def _taken(self, ip: str, mac: str, now: float) -> bool:
        if self.declined.get(ip, 0) > now:
            return True
        owner = self._reserved_ips().get(ip)
        if owner and owner != norm_mac(mac):
            return True
        return any(l.ip == ip and l.mac != mac and l.active(now) for l in self.leases.values())

    def allowed(self, mac: str, ip: str, now: float) -> bool:
        """Bu cihaz bu IP'yi alabilir mi (REQUEST dogrulamasi)."""
        reserved = self._reserved_for(mac)
        if reserved:
            return ip == reserved
        return ip in set(pool_addresses(self.cfg)) and not self._taken(ip, mac, now)

    def pick(self, mac: str, requested: str | None, now: float) -> str | None:
        reserved = self._reserved_for(mac)
        if reserved:
            return reserved
        pool = pool_addresses(self.cfg)
        pool_set = set(pool)
        old = self.leases.get(mac)
        if old and old.ip in pool_set and not self._taken(old.ip, mac, now):
            return old.ip                                    # ayni cihaz ayni IP (kalicilik)
        if requested and requested in pool_set and not self._taken(requested, mac, now):
            return requested
        reserved_ips = self._reserved_ips()
        for ip in pool:
            if ip in reserved_ips:
                continue
            if not self._taken(ip, mac, now) and not any(
                    l.ip == ip and l.mac != mac and l.state in ("bound",) for l in self.leases.values()):
                return ip
        return None

    # ----------------------------------------------------------------- islemler
    def offer(self, mac: str, requested: str | None, hostname: str, now: float, client_id: str = "") -> Lease | None:
        ip = self.pick(mac, requested, now)
        if ip is None:
            return None
        old = self.leases.get(mac)
        if old and old.state == "bound" and old.ip == ip and old.expires > now:
            return old                                        # zaten kirada: ayni teklif
        lease = Lease(mac, ip, hostname or (old.hostname if old else ""), now, now + OFFER_TTL, "offered", client_id)
        self.leases[mac] = lease
        return lease

    def request(self, mac: str, ip: str, hostname: str, now: float, client_id: str = "") -> tuple[Lease | None, bool]:
        """(kira, yeni_mi). Kira None ise NAK."""
        if not ip or not self.allowed(mac, ip, now):
            return None, False
        old = self.leases.get(mac)
        is_new = not (old and old.state == "bound" and old.ip == ip)
        lease = Lease(mac, ip, hostname or (old.hostname if old else ""),
                      old.start if (old and not is_new) else now, now + int(self.cfg.lease_time), "bound", client_id)
        self.leases[mac] = lease
        return lease, is_new

    def cancel_offer(self, mac: str) -> None:
        lease = self.leases.get(mac)
        if lease and lease.state == "offered":
            del self.leases[mac]

    def release(self, mac: str, ip: str | None = None) -> Lease | None:
        lease = self.leases.get(mac)
        if lease and (ip is None or lease.ip == ip):
            lease.state = "released"
            lease.expires = 0.0
            return lease
        return None

    def decline(self, mac: str, ip: str, now: float) -> None:
        self.declined[ip] = now + DECLINE_QUARANTINE
        lease = self.leases.get(mac)
        if lease and lease.ip == ip:
            del self.leases[mac]

    def expire(self, now: float) -> list[Lease]:
        """Suresi dolan kiralari isaretle; dolan TEKLIFLERI sil (havuza doner)."""
        expired = []
        for mac, lease in list(self.leases.items()):
            if lease.state == "offered" and lease.expires <= now:
                del self.leases[mac]
            elif lease.state == "bound" and lease.expires <= now:
                lease.state = "expired"
                expired.append(lease)
        self.declined = {ip: t for ip, t in self.declined.items() if t > now}
        return expired

    # ----------------------------------------------------------------- kalicilik
    def to_list(self) -> list[dict]:
        return [asdict(l) for l in sorted(self.leases.values(), key=lambda l: tuple(int(x) for x in l.ip.split(".")))]

    def load(self, items: list[dict]) -> None:
        for d in items or []:
            try:
                lease = Lease(**{k: d[k] for k in Lease.__dataclass_fields__ if k in d})
            except TypeError:
                continue
            if lease.state in ("bound", "expired", "released"):
                self.leases[norm_mac(lease.mac)] = lease
