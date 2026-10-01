"""Bekleyen degisiklik kuyrugu (ADR 0003): tipli adimlar, dogrulama, plan
uyarilari ve GERI ALMA adimlarinin uretimi. Saf Python; hicbir sey uygulamaz.

Platform katmani (platform/<os>/apply.py) bu adimlari betige cevirir.
Geri alma adimlari, degisiklik ONCESI snapshot'tan uretilir.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from enum import Enum

from .i18n import N_, tr
from .model import Connectivity, NodeKind, Severity, Status, Topology

HOST_TARGET = "host"
MTU_RANGE = (576, 9216)
METRIC_RANGE = (1, 9999)


class ChangeKind(str, Enum):
    ENABLED = "enabled"   # params: enabled: bool
    IPV4 = "ipv4"         # params: mode "dhcp"|"static", address, prefix, gateway
    DNS4 = "dns4"         # params: mode "auto"|"manual", servers: list[str]
    METRIC = "metric"     # params: auto: bool, metric: int
    MTU = "mtu"           # params: mtu: int (0 = otomatik; yalniz geri almada)
    ICS = "ics"           # target=host; params: public, private (None/None = paylasim kapali)
    RENAME = "rename"     # params: name
    DHCP_RENEW = "dhcp_renew"         # eylem; geri almasi yok
    BRIDGE_CREATE = "bridge_create"   # target=kopru adi; params: members[ids], ipv4{...}
    BRIDGE_DELETE = "bridge_delete"   # target=kopru adi; params: members, restore{uye: onceki profil}


# Platform destegi. Burada olmayan bir tur o platformda dogrulamada HATA verir.
SUPPORTED = {
    "windows": {ChangeKind.ENABLED, ChangeKind.IPV4, ChangeKind.DNS4, ChangeKind.METRIC,
                ChangeKind.MTU, ChangeKind.ICS, ChangeKind.RENAME, ChangeKind.DHCP_RENEW},
    "linux": {ChangeKind.ENABLED, ChangeKind.IPV4, ChangeKind.DNS4, ChangeKind.METRIC,
              ChangeKind.MTU, ChangeKind.ICS, ChangeKind.DHCP_RENEW,
              ChangeKind.BRIDGE_CREATE, ChangeKind.BRIDGE_DELETE},
}
UNSUPPORTED_REASON = {
    ("windows", ChangeKind.BRIDGE_CREATE): N_("Windows'ta köprü oluşturma henüz yok (Win10'da resmi araç yok; "
                                              "Win11 22H2+ için netsh bridge eklenecek)."),
    ("windows", ChangeKind.BRIDGE_DELETE): N_("Windows'ta köprü kaldırma henüz yok."),
    ("linux", ChangeKind.RENAME): N_("Linux'ta arayüz adı değiştirilmez (udev/sistem adı); desteklenmiyor."),
}
BRIDGE_PREFIX = "br-np"


@dataclass
class Change:
    kind: ChangeKind
    target: str
    params: dict = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind.value, self.target)


@dataclass
class Issue:
    severity: Severity
    message: str


@dataclass
class PlanItem:
    change: Change
    title: str
    issues: list[Issue]

    @property
    def blocked(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)


@dataclass
class Plan:
    items: list[PlanItem]
    rollback: list[Change]

    @property
    def blocked(self) -> bool:
        return any(i.blocked for i in self.items)

    @property
    def changes(self) -> list[Change]:
        return [i.change for i in self.items]


# Uygulama sirasi: once etkinlestirme ve kopru kaldirma, en son devre disi birakma.
def _order(c: Change) -> int:
    if c.kind == ChangeKind.ENABLED:
        return 0 if c.params.get("enabled") else 20
    return {ChangeKind.BRIDGE_DELETE: 1, ChangeKind.IPV4: 2, ChangeKind.DNS4: 3,
            ChangeKind.METRIC: 4, ChangeKind.MTU: 5, ChangeKind.ICS: 6,
            ChangeKind.BRIDGE_CREATE: 7, ChangeKind.RENAME: 8, ChangeKind.DHCP_RENEW: 9}[c.kind]


class ChangeSet:
    """Hedef + tur basina tek degisiklik; ayni alana yeni duzenleme eskisinin yerini alir."""

    def __init__(self):
        self._items: dict[tuple[str, str], Change] = {}

    def add(self, change: Change) -> None:
        self._items[change.key] = change

    def remove(self, key: tuple[str, str]) -> None:
        self._items.pop(key, None)

    def clear(self) -> None:
        self._items.clear()

    def get(self, kind: ChangeKind, target: str) -> Change | None:
        return self._items.get((kind.value, target))

    def targets(self) -> set[str]:
        out = set()
        for c in self._items.values():
            if c.kind == ChangeKind.ICS:
                out |= {x for x in (c.params.get("public"), c.params.get("private")) if x}
            elif c.kind in (ChangeKind.BRIDGE_CREATE, ChangeKind.BRIDGE_DELETE):
                out |= set(c.params.get("members") or [])
                out.add(c.target)
            else:
                out.add(c.target)
        return out

    def items(self) -> dict[tuple[str, str], Change]:
        """Geri al/yinele icin kopya (Change nesneleri degismez kabul edilir)."""
        return dict(self._items)

    def restore(self, items: dict[tuple[str, str], Change]) -> None:
        self._items = dict(items)

    def ordered(self) -> list[Change]:
        return sorted(self._items.values(), key=_order)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self.ordered())


# --------------------------------------------------------------------------- yardimcilar

def parse_prefix(value) -> int | None:
    """'24', '/24' veya '255.255.255.0' -> 24."""
    text = str(value or "").strip().lstrip("/")
    if not text:
        return None
    if text.isdigit():
        n = int(text)
        return n if 0 < n <= 32 else None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{text}").prefixlen
    except ValueError:
        return None


def prefix_to_mask(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def _ipv4(value) -> ipaddress.IPv4Address | None:
    try:
        return ipaddress.IPv4Address(str(value).strip())
    except ValueError:
        return None


def _name(topo: Topology, node_id: str | None) -> str:
    node = topo.nodes.get(node_id or "")
    return node.label if node else str(node_id)


def describe(c: Change, topo: Topology) -> str:
    name = _name(topo, c.target)
    p = c.params
    if c.kind == ChangeKind.ENABLED:
        return (tr("{name}: etkinleştir") if p.get("enabled") else tr("{name}: devre dışı bırak")).format(name=name)
    if c.kind == ChangeKind.IPV4:
        if p.get("mode") == "dhcp":
            return tr("{name}: IPv4 adresini otomatik al (DHCP)").format(name=name)
        addr = p.get("address")
        if not addr:
            return tr("{name}: IPv4 adreslerini kaldır").format(name=name)
        if p.get("gateway"):
            return tr("{name}: statik IPv4 {address}/{prefix}, ağ geçidi {gateway}").format(
                name=name, address=addr, prefix=p.get("prefix"), gateway=p["gateway"])
        return tr("{name}: statik IPv4 {address}/{prefix}, ağ geçidi yok").format(
            name=name, address=addr, prefix=p.get("prefix"))
    if c.kind == ChangeKind.DNS4:
        if p.get("mode") == "auto":
            return tr("{name}: DNS sunucularını otomatik al").format(name=name)
        return tr("{name}: DNS {servers}").format(name=name, servers=", ".join(p.get("servers") or []))
    if c.kind == ChangeKind.METRIC:
        if p.get("auto"):
            return tr("{name}: arayüz metriği otomatik").format(name=name)
        return tr("{name}: arayüz metriği {metric}").format(name=name, metric=p.get("metric"))
    if c.kind == ChangeKind.MTU:
        if not p.get("mtu"):
            return tr("{name}: MTU otomatik").format(name=name)
        return tr("{name}: MTU {mtu}").format(name=name, mtu=p.get("mtu"))
    if c.kind == ChangeKind.RENAME:
        return tr("{name}: adı “{new}” yap").format(name=name, new=p.get("name"))
    if c.kind == ChangeKind.ICS:
        if not p.get("public"):
            return tr("İnternet paylaşımını (ICS) kapat")
        return tr("İnternet paylaşımı: {source} → {target}").format(
            source=_name(topo, p.get("public")), target=_name(topo, p.get("private")))
    if c.kind == ChangeKind.DHCP_RENEW:
        return tr("{name}: DHCP adresini yenile").format(name=name)
    if c.kind == ChangeKind.BRIDGE_CREATE:
        members = ", ".join(_name(topo, m) for m in p.get("members") or [])
        ip = p.get("ipv4") or {}
        if ip.get("mode") == "dhcp":
            how = tr("IPv4 DHCP")
        elif ip.get("mode") == "disabled":
            how = tr("IPv4 yok (yalnız L2)")
        else:
            how = f"IPv4 {ip.get('address')}/{ip.get('prefix')}"
        return tr("Köprü {bridge} oluştur: {members} ({how})").format(bridge=c.target, members=members, how=how)
    if c.kind == ChangeKind.BRIDGE_DELETE:
        members = ", ".join(_name(topo, m) for m in p.get("members") or [])
        if members:
            return tr("Köprü {bridge} kaldır (üyeler: {members})").format(bridge=c.target, members=members)
        return tr("Köprü {bridge} kaldır").format(bridge=c.target)
    return f"{c.kind.value} {name}"


def next_bridge_name(topo: Topology, changes: "ChangeSet | None" = None) -> str:
    used = {n.label for n in topo.nodes.values()}
    if changes is not None:
        used |= {c.target for c in changes if c.kind == ChangeKind.BRIDGE_CREATE}
    i = 0
    while f"{BRIDGE_PREFIX}{i}" in used:
        i += 1
    return f"{BRIDGE_PREFIX}{i}"


def bridge_members(topo: Topology, bridge: str) -> list[str]:
    return [n.id for n in topo.nodes.values() if n.is_adapter and n.props.get("bridge_master") == bridge]


# --------------------------------------------------------------------------- dogrulama

def validate(c: Change, topo: Topology) -> list[Issue]:
    err = lambda m: Issue(Severity.ERROR, m)       # noqa: E731
    warn = lambda m: Issue(Severity.WARNING, m)    # noqa: E731
    issues: list[Issue] = []
    p = c.params
    node = topo.nodes.get(c.target)

    if c.kind not in SUPPORTED.get(topo.platform, set()):
        reason = UNSUPPORTED_REASON.get((topo.platform, c.kind))
        return [err(tr(reason) if reason else
                    tr("Bu platformda desteklenmiyor: {kind}").format(kind=c.kind.value))]
    if c.kind in (ChangeKind.BRIDGE_CREATE, ChangeKind.BRIDGE_DELETE):
        return _validate_bridge(c, topo)

    if c.kind != ChangeKind.ICS:
        if node is None or not node.is_adapter:
            return [err(tr("Hedef bağdaştırıcı artık yok (yenileyip tekrar deneyin)."))]
        carries_internet = node.id == topo.internet_via

    if c.kind == ChangeKind.DHCP_RENEW:
        if not node.props.get("dhcp4"):
            issues.append(err(tr("Bu bağdaştırıcıda DHCP kapalı; yenilenecek adres yok.")))
        elif node.status != Status.UP:
            issues.append(err(tr("Bağdaştırıcı bağlı değil; DHCP yenilenemez.")))
        elif carries_internet:
            issues.append(warn(tr("İnternet bağlantınız birkaç saniye kesilebilir.")))
        return issues

    if c.kind == ChangeKind.IPV4 and p.get("mode") == "static":
        ip = _ipv4(p.get("address"))
        prefix = p.get("prefix")
        if ip is None:
            issues.append(err(tr("Geçersiz IPv4 adresi: {value}").format(value=repr(p.get("address")))))
        if not isinstance(prefix, int) or not 1 <= prefix <= 32:
            issues.append(err(tr("Alt ağ maskesi geçersiz.")))
        if ip is not None and isinstance(prefix, int) and 1 <= prefix <= 32:
            net = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
            if ip.is_multicast or ip.is_loopback or ip.is_unspecified:
                issues.append(err(tr("{ip} bir bağdaştırıcıya atanamaz.").format(ip=ip)))
            elif prefix <= 30 and ip == net.network_address:
                issues.append(err(tr("{ip}, {net} ağının ağ adresi.").format(ip=ip, net=net)))
            elif prefix <= 30 and ip == net.broadcast_address:
                issues.append(err(tr("{ip}, {net} ağının yayın adresi.").format(ip=ip, net=net)))
            if ip.is_link_local:
                issues.append(warn(tr("169.254.x.x otomatik özel adres aralığıdır.")))
            gw_text = p.get("gateway")
            if gw_text:
                gw = _ipv4(gw_text)
                if gw is None:
                    issues.append(err(tr("Geçersiz ağ geçidi: {value}").format(value=repr(gw_text))))
                elif gw == ip:
                    issues.append(err(tr("Ağ geçidi, bağdaştırıcının kendi adresi olamaz.")))
                elif gw not in net:
                    issues.append(err(tr("Ağ geçidi {gateway}, {net} alt ağının dışında.").format(gateway=gw, net=net)))
            for other in topo.nodes.values():
                if not other.is_adapter or other.id == c.target:
                    continue
                for x in other.props.get("ipv4") or []:
                    if x.get("address") == str(ip):
                        issues.append(err(tr("{ip} zaten {name} üzerinde tanımlı.").format(ip=ip, name=other.label)))
                    elif other.status == Status.UP and x.get("prefix") and x.get("origin") != "link_local":
                        try:
                            onet = ipaddress.IPv4Network(f"{x['address']}/{x['prefix']}", strict=False)
                        except ValueError:
                            continue
                        if onet.overlaps(net):
                            issues.append(warn(tr("{net} alt ağı {name} ({other}) ile çakışıyor; "
                                                  "yönlendirme belirsizleşebilir.").format(
                                net=net, name=other.label, other=onet)))
    if c.kind == ChangeKind.IPV4 and node is not None and node.props.get("sharing") == "private":
        issues.append(warn(tr("Bu bağdaştırıcı internet paylaşımının hedefi; ICS adresini kendisi yönetir.")))

    if c.kind == ChangeKind.DNS4 and p.get("mode") == "manual":
        servers = [s for s in p.get("servers") or [] if str(s).strip()]
        if not servers:
            issues.append(err(tr("En az bir DNS sunucusu girin ya da 'Otomatik' seçin.")))
        for s in servers:
            if _ipv4(s) is None:
                issues.append(err(tr("Geçersiz DNS sunucusu: {value}").format(value=repr(s))))

    if c.kind == ChangeKind.METRIC and not p.get("auto"):
        m = p.get("metric")
        if not isinstance(m, int) or not METRIC_RANGE[0] <= m <= METRIC_RANGE[1]:
            issues.append(err(tr("Metrik {low}–{high} arasında olmalı.").format(low=METRIC_RANGE[0], high=METRIC_RANGE[1])))

    if c.kind == ChangeKind.MTU:
        m = p.get("mtu")
        if not isinstance(m, int) or not MTU_RANGE[0] <= m <= MTU_RANGE[1]:
            issues.append(err(tr("MTU {low}–{high} arasında olmalı.").format(low=MTU_RANGE[0], high=MTU_RANGE[1])))
        elif m > 1500:
            issues.append(warn(tr("1500 üzeri MTU için sürücüde 'Jumbo Packet' da açık olmalı; "
                                  "aksi hâlde paketler parçalanır ya da düşer.")))

    if c.kind == ChangeKind.RENAME:
        new = str(p.get("name") or "").strip()
        if not new:
            issues.append(err(tr("Ad boş olamaz.")))
        elif any(o.is_adapter and o.id != c.target and o.label.lower() == new.lower()
                 for o in topo.nodes.values()):
            issues.append(err(tr("“{name}” adında başka bir bağdaştırıcı var.").format(name=new)))

    if c.kind == ChangeKind.ENABLED and not p.get("enabled") and node is not None and carries_internet:
        issues.append(warn(tr("Bu bağdaştırıcı internet bağlantınızı taşıyor; devre dışı bırakınca "
                              "internet kesilir (30 sn içinde onaylamazsanız geri alınır).")))

    if c.kind in (ChangeKind.IPV4, ChangeKind.DNS4, ChangeKind.MTU) and node is not None and carries_internet:
        issues.append(warn(tr("Bu bağdaştırıcı internet bağlantınızı taşıyor; yanlış ayar bağlantıyı koparır.")))

    if c.kind == ChangeKind.ICS:
        issues += _validate_ics(c, topo)
    return issues


_BRIDGE_NAME_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")


def _validate_bridge(c: Change, topo: Topology) -> list[Issue]:
    err = lambda m: Issue(Severity.ERROR, m)       # noqa: E731
    warn = lambda m: Issue(Severity.WARNING, m)    # noqa: E731
    issues: list[Issue] = []
    name = c.target
    existing = next((n for n in topo.nodes.values() if n.is_adapter and n.label == name), None)
    if c.kind == ChangeKind.BRIDGE_DELETE:
        if existing is None or existing.kind != NodeKind.BRIDGE:
            return [err(tr("{name} adında bir köprü yok.").format(name=name))]
        if existing.id == topo.internet_via:
            issues.append(warn(tr("İnternet bağlantınız bu köprüden çıkıyor; kaldırınca kesilir.")))
        if not c.params.get("members"):
            issues.append(Issue(Severity.INFO, tr("Köprünün üyesi yok.")))
        return issues

    if not name or len(name) > 15 or set(name) - _BRIDGE_NAME_OK:
        issues.append(err(tr("Geçersiz köprü adı: {name} (en çok 15 karakter, harf/rakam/-_.)").format(name=repr(name))))
    if existing is not None:
        issues.append(err(tr("{name} adında bir arayüz zaten var.").format(name=name)))
    members = c.params.get("members") or []
    if not members:
        issues.append(err(tr("Köprünün en az bir üyesi olmalı.")))
    for mid in members:
        m = topo.nodes.get(mid)
        if m is None or not m.is_adapter:
            issues.append(err(tr("Üye bulunamadı: {id}").format(id=mid)))
            continue
        if m.kind == NodeKind.WIFI:
            issues.append(err(tr("{name}: Wi-Fi istemci modunda köprüye eklenemez (AP'ler tek MAC kabul eder).")
                              .format(name=m.label)))
        elif m.kind not in (NodeKind.ETHERNET, NodeKind.UNKNOWN, NodeKind.VM_HOST_ONLY):
            issues.append(err(tr("{name} köprüye eklenemez ({kind}).").format(name=m.label, kind=m.kind.value)))
        if m.props.get("bridge_master"):
            issues.append(err(tr("{name} zaten {bridge} köprüsünün üyesi.").format(
                name=m.label, bridge=m.props["bridge_master"])))
        if m.props.get("sharing"):
            issues.append(err(tr("{name} internet paylaşımında; önce paylaşımı kapatın.").format(name=m.label)))
        if m.id == topo.internet_via:
            issues.append(warn(tr("{name} internet çıkışınız; köprüye alınınca IP köprüye taşınır ve "
                                  "bağlantı kısa süre kesilir (30 sn içinde onaylamazsanız geri alınır).")
                               .format(name=m.label)))
    if len(members) == 1:
        issues.append(warn(tr("Tek üyeli köprü: iki ağı birleştirmek için ikinci bir üye ekleyin.")))
    return issues


def _validate_ics(c: Change, topo: Topology) -> list[Issue]:
    issues: list[Issue] = []
    pub_id, priv_id = c.params.get("public"), c.params.get("private")
    if topo.platform == "linux":
        return _validate_ics_linux(c, topo)
    current = [n for n in topo.nodes.values() if n.props.get("sharing")]
    if not pub_id:
        if not current:
            issues.append(Issue(Severity.INFO, tr("Şu an açık bir paylaşım yok.")))
        return issues
    pub, priv = topo.nodes.get(pub_id), topo.nodes.get(priv_id or "")
    if pub is None or priv is None:
        return [Issue(Severity.ERROR, tr("Paylaşımın kaynağı veya hedefi bulunamadı."))]
    if pub.id == priv.id:
        return [Issue(Severity.ERROR, tr("Kaynak ve hedef aynı bağdaştırıcı olamaz."))]
    for n in (pub, priv):
        if n.kind in (NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.BRIDGE) or n.props.get("bridge_member"):
            issues.append(Issue(Severity.ERROR, tr("{name} internet paylaşımında kullanılamaz.").format(name=n.label)))
    if pub.connectivity != Connectivity.INTERNET and pub.id != topo.internet_via:
        issues.append(Issue(Severity.WARNING, tr("{name} üzerinde şu an internet erişimi görünmüyor.")
                            .format(name=pub.label)))
    if pub.kind == NodeKind.VPN:
        issues.append(Issue(Severity.WARNING, tr("VPN bağdaştırıcısı kaynak yapılırsa VPN yeniden "
                                                 "bağlandığında paylaşım bozulabilir.")))
    if priv.id == topo.internet_via:
        issues.append(Issue(Severity.WARNING, tr("{name} şu an internet çıkışınız; paylaşım hedefi "
                                                 "yapılınca bu bağlantı kopar.").format(name=priv.label)))
    old = {n.id for n in current}
    if old and old != {pub.id, priv.id}:
        names = ", ".join(n.label for n in current)
        issues.append(Issue(Severity.WARNING, tr("Windows aynı anda tek paylaşıma izin verir; mevcut "
                                                 "paylaşım ({names}) kapatılacak.").format(names=names)))
    scope = (topo.snapshot.get("sharing") or {}).get("scope") or "192.168.137.1"
    v4 = [x["address"] for x in priv.props.get("ipv4") or [] if x.get("origin") == "manual"]
    msg = tr("{name} adresi {scope}/24 olacak (paylaşım kapsamı).").format(name=priv.label, scope=scope)
    if v4:
        msg += " " + tr("Mevcut statik adres ({addresses}) silinir; geri alma onu geri yükler.").format(
            addresses=", ".join(v4))
    issues.append(Issue(Severity.WARNING, msg))
    hotspot = [n for n in topo.nodes.values() if n.kind == NodeKind.HOTSPOT and n.status == Status.UP]
    if hotspot:
        issues.append(Issue(Severity.WARNING, tr("Mobil Hotspot açık; o da paylaşımı kullandığı için kapanır.")))
    return issues


def _validate_ics_linux(c: Change, topo: Topology) -> list[Issue]:
    """NetworkManager 'shared': hedef baglanti ipv4.method=shared olur; cikis varsayilan rotadir."""
    pub_id, priv_id = c.params.get("public"), c.params.get("private")
    if not pub_id:
        return []
    pub, priv = topo.nodes.get(pub_id), topo.nodes.get(priv_id or "")
    if pub is None or priv is None:
        return [Issue(Severity.ERROR, tr("Paylaşımın kaynağı veya hedefi bulunamadı."))]
    if pub.id == priv.id:
        return [Issue(Severity.ERROR, tr("Kaynak ve hedef aynı bağdaştırıcı olamaz."))]
    issues = []
    if priv.kind in (NodeKind.SYSTEM, NodeKind.LOOPBACK) or priv.props.get("bridge_master"):
        issues.append(Issue(Severity.ERROR, tr("{name} paylaşım hedefi olamaz.").format(name=priv.label)))
    if priv.id == topo.internet_via:
        issues.append(Issue(Severity.ERROR, tr("{name} internet çıkışınız; paylaşım hedefi yapılamaz.")
                            .format(name=priv.label)))
    if pub.id != topo.internet_via:
        via = topo.nodes.get(topo.internet_via or "")
        issues.append(Issue(Severity.WARNING, tr("Linux'ta paylaşılan trafik varsayılan rotadan çıkar ({name}); "
                                                 "kaynak seçimi yalnız bilgi amaçlı.").format(
            name=via.label if via else tr("yok"))))
    issues.append(Issue(Severity.WARNING, tr("{name} adresi NetworkManager paylaşım adresi olacak "
                                             "(varsayılan 10.42.0.1/24) ve o ağa DHCP dağıtacak.").format(name=priv.label)))
    return issues


# --------------------------------------------------------------------------- geri alma

def rollback_for(c: Change, topo: Topology) -> list[Change]:
    """Degisiklik ONCESI durumu geri getiren adimlar (snapshot'tan)."""
    if c.kind == ChangeKind.ICS:
        current_pub = next((n.id for n in topo.nodes.values() if n.props.get("sharing") == "public"), None)
        current_priv = next((n.id for n in topo.nodes.values() if n.props.get("sharing") == "private"), None)
        if topo.platform == "linux" and current_priv and not current_pub:
            current_pub = topo.internet_via            # NM shared: cikis = varsayilan rota
        out = [Change(ChangeKind.ICS, HOST_TARGET, {"public": current_pub, "private": current_priv})]
        new_priv = c.params.get("private")
        if new_priv and new_priv != current_priv and new_priv in topo.nodes:
            out.append(current_ipv4(topo, new_priv))    # ICS private IP'sini ezer
        return out
    if c.kind == ChangeKind.DHCP_RENEW:
        return []
    if c.kind == ChangeKind.BRIDGE_CREATE:
        restore = {}
        for m in c.params.get("members") or []:
            nm = (topo.nodes[m].props.get("nm") or {}) if m in topo.nodes else {}
            if nm.get("active") and nm.get("uuid"):
                restore[m] = nm["uuid"]             # kopru kalkinca eski profili geri ac
        return [Change(ChangeKind.BRIDGE_DELETE, c.target,
                       {"members": list(c.params.get("members") or []), "created": True, "restore": restore})]
    if c.kind == ChangeKind.BRIDGE_DELETE:
        bridge = next((n for n in topo.nodes.values() if n.is_adapter and n.label == c.target), None)
        if bridge is None:
            return []
        return [Change(ChangeKind.BRIDGE_CREATE, c.target,
                       {"members": bridge_members(topo, c.target),
                        "ipv4": current_ipv4(topo, bridge.id).params})]
    node = topo.nodes.get(c.target)
    if node is None:
        return []
    p = node.props
    if c.kind == ChangeKind.ENABLED:
        return [Change(ChangeKind.ENABLED, c.target, {"enabled": node.status != Status.DISABLED})]
    if c.kind == ChangeKind.IPV4:
        return [current_ipv4(topo, c.target)]
    if c.kind == ChangeKind.DNS4:
        return [current_dns4(topo, c.target)]
    if c.kind == ChangeKind.METRIC:
        if p.get("auto_metric4") is False and p.get("metric4"):
            return [Change(ChangeKind.METRIC, c.target, {"auto": False, "metric": p["metric4"]})]
        return [Change(ChangeKind.METRIC, c.target, {"auto": True})]
    if c.kind == ChangeKind.MTU and p.get("mtu_auto"):
        return [Change(ChangeKind.MTU, c.target, {"mtu": 0})]     # profil 'otomatik'ti
    if c.kind == ChangeKind.MTU and p.get("mtu"):
        return [Change(ChangeKind.MTU, c.target, {"mtu": p["mtu"]})]
    if c.kind == ChangeKind.RENAME:
        return [Change(ChangeKind.RENAME, c.target, {"name": node.label})]
    return []


def current_ipv4(topo: Topology, node_id: str) -> Change:
    p = topo.nodes[node_id].props
    if p.get("dhcp4"):
        return Change(ChangeKind.IPV4, node_id, {"mode": "dhcp"})
    manual = [x for x in p.get("ipv4") or [] if x.get("origin") == "manual"]
    gw = next((r.get("next_hop") for r in topo.snapshot.get("default_routes") or []
               if r.get("adapter") == node_id and r.get("family") == 4
               and r.get("next_hop") not in (None, "", "0.0.0.0")), None)
    if manual:
        return Change(ChangeKind.IPV4, node_id, {"mode": "static", "address": manual[0]["address"],
                                                 "prefix": manual[0].get("prefix"), "gateway": gw})
    return Change(ChangeKind.IPV4, node_id, {"mode": "static", "address": None, "prefix": None, "gateway": None})


def current_dns4(topo: Topology, node_id: str) -> Change:
    p = topo.nodes[node_id].props
    manual = p.get("dns4_manual")
    if manual is None:                     # eski snapshot: DHCP'li ise otomatik varsay
        manual = not p.get("dhcp4") and bool(p.get("dns4"))
    # Linux: profilde yazili DNS (dns4_setting) etkin listeden farkli olabilir.
    servers = p.get("dns4_setting") or p.get("dns4")
    if manual and servers:
        return Change(ChangeKind.DNS4, node_id, {"mode": "manual", "servers": list(servers)})
    return Change(ChangeKind.DNS4, node_id, {"mode": "auto"})


# --------------------------------------------------------------------------- onay gerekir mi

def needs_confirmation(plan: Plan, topo: Topology) -> tuple[bool, str]:
    """Uygulamadan sonra 30 sn 'koru / geri al' beklensin mi? (bool, gerekce)

    Kullanici her degisiklikte beklemekten sikayet etti (2026-09-30): bekleme yalnizca
    baglantiyi koparabilecek degisikliklerde. Digerleri anında biter; kullanici Uygula
    penceresindeki kutuyla bunu her zaman degistirebilir.
    """
    via = topo.internet_via
    for c in plan.changes:
        p = c.params
        if c.kind in (ChangeKind.ICS, ChangeKind.BRIDGE_CREATE, ChangeKind.BRIDGE_DELETE):
            return True, tr("İnternet paylaşımı / köprü ağ yapısını değiştirir.")
        if c.target == via and c.kind not in (ChangeKind.RENAME, ChangeKind.DHCP_RENEW):
            return True, tr("İnternet bağlantınızı taşıyan {name} değişiyor.").format(name=_name(topo, via))
        node = topo.nodes.get(c.target)
        up = node is not None and node.status == Status.UP
        if c.kind == ChangeKind.ENABLED and not p.get("enabled") and up:
            return True, tr("Bağlı {name} kapatılıyor.").format(name=node.label)
        # Kullanilabilir IPv4'u olmayan kartta (yok ya da yalniz 169.254) kopacak bir baglanti yok:
        # ör. DHCP sunucusu kurulacak yalitilmis kart (ADR 0010) onaysiz statik IP alir.
        has_address = node is not None and any(
            a.get("address") and not str(a["address"]).startswith("169.254.") for a in node.props.get("ipv4") or [])
        if (c.kind == ChangeKind.IPV4 and up and has_address) or (c.kind == ChangeKind.MTU and up):
            return True, tr("Bağlı {name} bağdaştırıcısının adres/MTU ayarı değişiyor (uzak bağlantı kopabilir).").format(name=node.label)
    return False, tr("Etkin bağlantıya dokunmuyor; onay beklenmeden tamamlanır.")


# --------------------------------------------------------------------------- plan

def build_plan(changes: ChangeSet, topo: Topology) -> Plan:
    items = [PlanItem(c, describe(c, topo), validate(c, topo)) for c in changes]
    rollback: list[Change] = []
    seen: set[tuple[str, str]] = set()
    for c in changes:
        for r in rollback_for(c, topo):
            if r.key not in seen:          # ilk uretilen = degisiklik oncesi durum
                seen.add(r.key)
                rollback.append(r)
    # Geri alma ters sirada: once paylasim/ad, en son IP (ICS ezdigi IP'yi geri yukle).
    rollback.sort(key=_order, reverse=True)
    return Plan(items, rollback)
