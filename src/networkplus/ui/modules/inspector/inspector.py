"""Ozellikler (inspector) modulu: yerlesim inspector.ui'da, davranis burada.

Form bagdastiricinin su anki ayarlariyla (ve varsa bekleyen degisikliklerle)
dolar. "Kuyruga ekle" yalnizca DEGISEN alanlari Change olarak yayar; hicbir
sey burada uygulanmaz (ADR 0003).
"""

from __future__ import annotations

import ipaddress

from PyQt5.QtCore import QCollator, QLocale, QRegularExpression, QSignalBlocker, Qt, pyqtSignal
from PyQt5.QtGui import QRegularExpressionValidator, QTextCursor
from PyQt5.QtWidgets import QHeaderView, QLineEdit, QTreeWidgetItem, QWidget

from ...icons import make_icon
from ...theme import RED, connectivity_text, edge_title, status_color, status_text
from ...uiloader import load_ui, require
from ....core.changes import (
    MTU_RANGE, Change, ChangeKind, ChangeSet, HOST_TARGET, advanced_display, advanced_props, advanced_registry,
    current_dns4, current_ipv4, parse_prefix, prefix_to_mask, validate, validate_advanced_value,
)
from ....core.discovery import kind_label
from ....core.i18n import N_, tr
from ....core.model import Node, NodeKind, Severity, Status, Topology

PAGE_EMPTY, PAGE_ADAPTER, PAGE_INFO = 0, 1, 2
MODE_DHCP, MODE_STATIC = 0, 1
DNS_AUTO, DNS_MANUAL = 0, 1

BINDING_NAMES = {
    "ms_tcpip": N_("İnternet Protokolü Sürüm 4 (TCP/IPv4)"),
    "ms_tcpip6": N_("İnternet Protokolü Sürüm 6 (TCP/IPv6)"),
    "ms_bridge": N_("Ağ köprüsü"),
    "vms_pp": N_("Hyper-V genişletilebilir sanal anahtar"),
    "ms_server": N_("Dosya ve yazıcı paylaşımı"),
    "ms_msclient": N_("Microsoft Ağları İstemcisi"),
}
_NOT_SHAREABLE = {NodeKind.SYSTEM, NodeKind.LOOPBACK, NodeKind.BRIDGE, NodeKind.CONTAINER}


def _dash(value) -> str:
    if value is None or value == "" or value == []:
        return "—"
    if isinstance(value, bool):
        return tr("Evet") if value else tr("Hayır")
    return str(value)


ORIGIN_TEXT = {"dhcp": N_("DHCP"), "manual": N_("elle"), "link_local": N_("otomatik özel"), "other": ""}


def _addresses(items) -> str:
    rows = []
    for x in items or []:
        origin = tr(ORIGIN_TEXT.get(x.get("origin"), ""))
        rows.append(f"{x['address']}/{x.get('prefix')}" + (f"  ({origin})" if origin else ""))
    return "\n".join(rows) or "—"


def _speed(bps) -> str:
    if not bps:
        return "—"
    for unit, div in ((N_("Gbit/sn"), 1e9), (N_("Mbit/sn"), 1e6), (N_("kbit/sn"), 1e3)):
        if bps >= div:
            return f"{bps / div:g} {tr(unit)}"
    return f"{bps} {tr('bit/sn')}"


DEFAULT_MASK = "255.255.255.0"
_IP_CHARS = QRegularExpression(r"[0-9./]*")
_DOT_CHARS = QRegularExpression(r"[0-9.]*")


def gateway_hint(address: str, mask_text: str) -> str | None:
    """Alt agin ilk adresi (ör. 192.168.1.1) — yalnizca ONERI, otomatik yazilmaz."""
    prefix = parse_prefix(mask_text) or 24
    try:
        net = ipaddress.IPv4Interface(f"{address.strip()}/{prefix}").network
    except ValueError:
        return None
    if net.prefixlen >= 31:
        return None
    first = net.network_address + 1
    return None if str(first) == address.strip() else str(first)


class InspectorPanel(QWidget):
    # (bagdastirici id, eklenecek degisiklikler, kuyruktan cikarilacak anahtarlar)
    formSubmitted = pyqtSignal(str, list, list)
    formApplyRequested = pyqtSignal(str, list)     # (bagdastirici id, degisiklikler) — dogrudan uygula

    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "stack", "tabs", "lblIcon", "lblTitle", "lblSubtitle", "treeInfo",
                "pageAdapter", "tabWifi", "tabBindings", "tabIssues",
                "edName", "chkEnabled", "edDescription", "edKind", "edStatus", "edConnectivity",
                "edMac", "edSpeed", "edNetwork", "edId",
                "cmbIpv4Mode", "edIpAddress", "edMask", "edGateway", "txtIpv4",
                "cmbDnsMode", "edDns1", "edDns2", "chkAutoMetric", "spnMetric", "spnMtu", "edForwarding",
                "txtIpv6", "edDns6", "cmbShareFrom", "edIcsRole", "edIcsScope", "edIcsService", "edBridge",
                "edSsid", "edBssid", "barSignal", "treeBindings", "listIssues",
                "tabAdvanced", "treeAdvanced", "edAdvancedFilter",
                "cmbAdvValue", "spnAdvValue", "edAdvValue", "btnAdvDefault", "lblAdvValue",
                "lblPending", "btnQueue", "btnResetForm", "btnApplyNow", "lblReadOnly")
        f = self.lblTitle.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1)
        self.lblTitle.setFont(f)

        # Yalnizca rakam/nokta (IP alaninda '/' da: 192.168.1.10/24 yazilabilir).
        self.edIpAddress.setValidator(QRegularExpressionValidator(_IP_CHARS, self))
        for ed in (self.edMask, self.edGateway, self.edDns1, self.edDns2):
            ed.setValidator(QRegularExpressionValidator(_DOT_CHARS, self))
        self.edMask.setValidator(QRegularExpressionValidator(_IP_CHARS, self))    # '/24' de olur

        self.cmbIpv4Mode.currentIndexChanged.connect(self._sync_enabled)
        self.cmbIpv4Mode.activated.connect(self._on_mode_chosen)
        self.edIpAddress.editingFinished.connect(self._on_ip_finished)
        self.edIpAddress.textChanged.connect(self._update_gateway_hint)
        self.edMask.editingFinished.connect(self._on_mask_finished)
        self.edMask.textChanged.connect(self._update_gateway_hint)
        self.cmbDnsMode.currentIndexChanged.connect(self._sync_enabled)
        self.chkAutoMetric.toggled.connect(self._sync_enabled)
        self.btnQueue.clicked.connect(self._submit)
        self.btnApplyNow.clicked.connect(self._submit_and_apply)
        self.btnResetForm.clicked.connect(lambda: self._fill_form(self._node, with_pending=False))
        self.edAdvancedFilter.textChanged.connect(self._filter_advanced)
        # Deger sutunu hep tam gorunsun; uzun ozellik adi kisaltilir (ipucunda tamami).
        head = self.treeAdvanced.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        # Deger duzenleyici (Windows'taki gibi: listeden sec, alttan degistir). Duzenlemeler
        # _adv_edits'te birikir ve formun geri kalaniyla ayni Uygula / Kuyruga ekle ile gider.
        self._adv_edits: dict[str, str | None] = {}
        self.treeAdvanced.currentItemChanged.connect(self._load_adv_editor)
        self.cmbAdvValue.activated.connect(self._adv_combo_chosen)
        self.spnAdvValue.editingFinished.connect(self._adv_spin_done)
        self.edAdvValue.editingFinished.connect(self._adv_text_done)
        self.btnAdvDefault.clicked.connect(self._adv_default)

        self.topology: Topology | None = None
        self.changes: ChangeSet | None = None
        self._node: Node | None = None
        self.clear()

    def set_topology(self, topo: Topology):
        self.topology = topo

    def set_changes(self, changes: ChangeSet):
        self.changes = changes

    def clear(self):
        self._node = None
        self.lblIcon.clear()
        self.lblTitle.setText(tr("Özellikler"))
        self.lblSubtitle.setText("")
        self.stack.setCurrentIndex(PAGE_EMPTY)

    def refresh_pending(self):
        """Kuyruk degisince acik formu yeniden doldur."""
        if self._node is not None and self.stack.currentIndex() == PAGE_ADAPTER:
            self._fill_form(self._node, with_pending=True)

    # ----------------------------------------------------------------- dugum
    def show_node(self, node_id: str):
        node = self.topology.nodes.get(node_id) if self.topology else None
        if node is None:
            self.clear()
            return
        self._header(node)
        if node.is_adapter:
            self._node = node
            self._show_adapter(node)
        else:
            self._node = None
            self._show_synthetic(node)

    def _header(self, node: Node):
        self.lblIcon.setPixmap(make_icon(node.kind, status_color(node), 40).pixmap(40, 40))
        self.lblTitle.setText(node.label)
        self.lblSubtitle.setText(f"{kind_label(node.kind)} · {status_text(node.status)}")

    def _show_adapter(self, node: Node):
        p = node.props
        topo = self.topology
        self.edDescription.setText(_dash(p.get("description")))
        self.edKind.setText(kind_label(node.kind))
        self.edStatus.setText(status_text(node.status))
        self.edConnectivity.setText(connectivity_text(node.connectivity))
        self.edMac.setText(_dash(p.get("mac")))
        self.edSpeed.setText(_speed(p.get("speed_bps")))
        net, cat = p.get("network_name"), p.get("network_category")
        self.edNetwork.setText(_dash(f"{net} ({cat})" if net and cat else net))
        self.edId.setText(_dash(p.get("id")))

        self.txtIpv4.setPlainText(_addresses(p.get("ipv4")))
        self.edForwarding.setText(_dash(p.get("forwarding4")))
        self.txtIpv6.setPlainText(_addresses(p.get("ipv6")))
        for box in (self.txtIpv4, self.txtIpv6):
            box.moveCursor(QTextCursor.Start)
        self.edDns6.setText(_dash(", ".join(p.get("dns6") or [])))

        sharing = topo.snapshot.get("sharing") or {}
        role = p.get("sharing")
        self.edIcsRole.setText({"public": tr("Kaynak (interneti paylaşıyor)"),
                                "private": tr("Hedef (paylaşılan interneti alıyor)")}.get(role, tr("Kapalı")))
        self.edIcsScope.setText(_dash(sharing.get("scope")) + ("/24" if sharing.get("scope") else ""))
        self.edIcsService.setText(_dash(sharing.get("service")))
        member = p.get("bridge_master") or ("evet" if p.get("bridge_member") else None)
        self.edBridge.setText(tr("Üye ({bridge})").format(bridge=member) if member else tr("Üye değil"))

        wifi = p.get("wifi") or {}
        self.tabs.setTabEnabled(self.tabs.indexOf(self.tabWifi), bool(wifi) or node.kind == NodeKind.WIFI)
        self.edSsid.setText(_dash(wifi.get("ssid")))
        self.edBssid.setText(_dash(wifi.get("bssid")))
        self.barSignal.setValue(int(wifi.get("signal") or 0))

        self.treeBindings.clear()
        for comp, enabled in sorted((p.get("bindings") or {}).items()):
            QTreeWidgetItem(self.treeBindings, [tr(BINDING_NAMES[comp]) if comp in BINDING_NAMES else comp, tr("Evet") if enabled else tr("Hayır")])
        self.tabs.setTabEnabled(self.tabs.indexOf(self.tabBindings), bool(p.get("bindings")))
        self._fill_advanced(p.get("advanced") or [])

        self.listIssues.clear()
        for b in node.badges:
            self.listIssues.addItem(f"[{b.severity.value}] {b.message}")
        issues_index = self.tabs.indexOf(self.tabIssues)
        self.tabs.setTabText(issues_index, tr("Sorunlar ({count})").format(count=len(node.badges)) if node.badges
                             else tr("Sorunlar"))

        self._fill_form(node, with_pending=True)
        for ed in self.pageAdapter.findChildren(QLineEdit):
            ed.setCursorPosition(0)
        if not self.tabs.isTabEnabled(self.tabs.currentIndex()):
            self.tabs.setCurrentIndex(0)
        self.stack.setCurrentIndex(PAGE_ADAPTER)

    def _fill_advanced(self, props: list[dict]):
        """Surucu gelismis ozellikleri (salt okunur). Varsayilandan farkli deger kalin yazilir."""
        self.treeAdvanced.clear()
        # Yerel sira (Turkce: "Ag Adresi" "Akis"tan once, Windows gibi). Harf buyuklugu once
        # katlanir: C/POSIX yerelinde (CI) QCollator buyuk harfi one alir ("ARP" < "Advanced").
        collator = QCollator(QLocale())
        for prop in sorted(props, key=lambda x: collator.sortKey(str(x.get("display") or "").casefold())):
            value = prop.get("value") or ""
            item = QTreeWidgetItem(self.treeAdvanced, [str(prop.get("display") or prop.get("keyword")),
                                                       value or _dash(None)])
            item.setData(0, Qt.UserRole, prop.get("keyword"))
            default = prop.get("default")
            lines = [str(prop.get("display") or ""), tr("Anahtar: {keyword}").format(keyword=prop.get("keyword"))]
            if prop.get("registry"):
                lines.append(tr("Kayıt değeri: {value}").format(value=", ".join(prop["registry"])))
            if default is not None:
                lines.append(tr("Varsayılan: {value}").format(value=default))
            rng = prop.get("range")
            if prop.get("options"):
                lines.append(tr("Seçenekler: {values}").format(values=" · ".join(prop["options"])))
            elif rng:
                lines.append(tr("Aralık: {min}–{max} (adım {step})").format(
                    min=rng.get("min"), max=rng.get("max"), step=rng.get("step") or 1))
            tip = "\n".join(lines)
            item.setToolTip(0, tip)
            item.setToolTip(1, tip)
        self.tabs.setTabEnabled(self.tabs.indexOf(self.tabAdvanced), bool(props))
        self._filter_advanced(self.edAdvancedFilter.text())
        self._load_adv_editor(None)

    # ---- gelismis: deger duzenleme
    def _adv_prop(self, item) -> dict | None:
        if item is None or self._node is None:
            return None
        return advanced_props(self._node).get(item.data(0, Qt.UserRole))

    def _adv_value(self, prop: dict) -> str | None:
        """Formdaki (duzenlenmis ya da su anki) kayit degeri."""
        keyword = prop["keyword"]
        return self._adv_edits[keyword] if keyword in self._adv_edits else advanced_registry(prop)

    def _render_adv_values(self):
        """Deger sutunu: duzenlenmis deger + isaret; varsayilandan farkli deger kalin."""
        for i in range(self.treeAdvanced.topLevelItemCount()):
            item = self.treeAdvanced.topLevelItem(i)
            prop = self._adv_prop(item)
            if prop is None:
                continue
            edited = prop["keyword"] in self._adv_edits
            value = self._adv_value(prop)
            text = advanced_display(prop, value) if edited else (prop.get("value") or "")
            if edited and value is None:
                text = tr("(varsayılan)")
            item.setText(1, ("● " if edited else "") + (text or _dash(None)))
            f = item.font(1)
            default = prop.get("default")
            f.setBold(edited or (default is not None and bool(text) and text != default))
            f.setItalic(edited)
            item.setFont(1, f)

    def _load_adv_editor(self, item, _previous=None):
        prop = self._adv_prop(item)
        options, regs = (prop or {}).get("options") or [], (prop or {}).get("options_registry") or []
        rng = (prop or {}).get("range")
        use_combo = bool(prop) and bool(options) and len(options) == len(regs)
        use_spin = bool(prop) and not use_combo and bool(rng)
        use_text = bool(prop) and not use_combo and not use_spin
        self.cmbAdvValue.setVisible(use_combo or not prop)
        self.spnAdvValue.setVisible(use_spin)
        self.edAdvValue.setVisible(use_text)
        for w in (self.cmbAdvValue, self.spnAdvValue, self.edAdvValue, self.btnAdvDefault, self.lblAdvValue):
            w.setEnabled(bool(prop))
        blockers = [QSignalBlocker(w) for w in (self.cmbAdvValue, self.spnAdvValue, self.edAdvValue)]
        self.cmbAdvValue.clear()
        if not prop:
            return
        value = self._adv_value(prop)
        if use_combo:
            for text, reg in zip(options, regs):
                self.cmbAdvValue.addItem(text, reg)
            self.cmbAdvValue.setCurrentIndex(max(0, self.cmbAdvValue.findData(value)))
        elif use_spin:
            self.spnAdvValue.setRange(int(rng["min"]), int(rng["max"]))
            self.spnAdvValue.setSingleStep(int(rng.get("step") or 1))
            try:
                self.spnAdvValue.setValue(int(value))
            except (TypeError, ValueError):
                self.spnAdvValue.setValue(int(rng["min"]))
        else:
            self.edAdvValue.setText(value or "")
            self.edAdvValue.setPlaceholderText(tr("boş = sürücü varsayılanı"))
        del blockers

    def _set_adv(self, value: str | None):
        prop = self._adv_prop(self.treeAdvanced.currentItem())
        if prop is None:
            return
        if value == advanced_registry(prop):
            self._adv_edits.pop(prop["keyword"], None)        # su anki degere donuldu
        else:
            self._adv_edits[prop["keyword"]] = value
        problem = validate_advanced_value(prop, value)
        if problem:
            self._set_pending_label(0, tr("Düzeltin: {error}").format(error=problem))
        self._render_adv_values()

    def _adv_combo_chosen(self, index: int):
        self._set_adv(self.cmbAdvValue.itemData(index))

    def _adv_spin_done(self):
        if self.spnAdvValue.isVisible():
            self._set_adv(str(self.spnAdvValue.value()))

    def _adv_text_done(self):
        if self.edAdvValue.isVisible():
            self._set_adv(self.edAdvValue.text().strip() or None)

    def _adv_default(self):
        prop = self._adv_prop(self.treeAdvanced.currentItem())
        if prop is None:
            return
        default = prop.get("default")
        options, regs = prop.get("options") or [], prop.get("options_registry") or []
        if default in options and len(options) == len(regs):
            value = regs[options.index(default)]
        elif prop.get("range") and str(default or "").strip().lstrip("-").isdigit():
            value = str(int(default))
        else:
            value = None                                        # surucu varsayilani (kayit silinir)
        self._set_adv(value)
        self._load_adv_editor(self.treeAdvanced.currentItem())

    def _filter_advanced(self, text: str):
        needle = text.strip().casefold()
        for i in range(self.treeAdvanced.topLevelItemCount()):
            item = self.treeAdvanced.topLevelItem(i)
            hay = f"{item.text(0)} {item.text(1)} {item.toolTip(0)}".casefold()
            item.setHidden(bool(needle) and needle not in hay)

    # ----------------------------------------------------------------- form
    def _current_state(self, node: Node) -> dict[ChangeKind, dict]:
        """Bagdastiricinin SU ANKI (snapshot) durumu, Change parametreleri biciminde."""
        p = node.props
        topo = self.topology
        state = {
            ChangeKind.RENAME: {"name": node.label},
            ChangeKind.ENABLED: {"enabled": node.status != Status.DISABLED},
            ChangeKind.IPV4: current_ipv4(topo, node.id).params,
            ChangeKind.DNS4: current_dns4(topo, node.id).params,
            ChangeKind.METRIC: ({"auto": False, "metric": p["metric4"]}
                                if p.get("auto_metric4") is False and p.get("metric4") else {"auto": True}),
            # Loopback 4294967295 gibi degerler kutunun sinirina kirpilir; kirpilmis
            # deger karsilastirilir ki form kendiliginden "degisti" sanmasin.
            ChangeKind.MTU: {"mtu": min(max(int(p.get("mtu") or 1500), MTU_RANGE[0]), MTU_RANGE[1])},
            ChangeKind.ADVANCED: {"values": {}},           # su anki = hic degisiklik yok
        }
        pub = None
        if p.get("sharing") == "private":
            pub = next((n.id for n in topo.nodes.values() if n.props.get("sharing") == "public"), None)
        state[ChangeKind.ICS] = {"public": pub, "private": node.id if pub else None}
        return state

    def _fill_form(self, node: Node | None, with_pending: bool):
        if node is None:
            return
        state = self._current_state(node)
        pending = 0
        if with_pending and self.changes is not None:
            for kind in state:
                target = HOST_TARGET if kind == ChangeKind.ICS else node.id
                c = self.changes.get(kind, target)
                if c is None:
                    continue
                if kind == ChangeKind.ICS and node.id not in (c.params.get("private"), state[kind]["private"]):
                    continue
                state[kind] = dict(c.params)
                pending += 1
        if self.changes is not None:
            pending = sum(1 for c in self.changes
                          if c.target == node.id or node.id in (c.params.get("public"), c.params.get("private")))

        self.edName.setText(state[ChangeKind.RENAME]["name"])
        self.chkEnabled.setChecked(bool(state[ChangeKind.ENABLED]["enabled"]))

        ip = state[ChangeKind.IPV4]
        self.cmbIpv4Mode.setCurrentIndex(MODE_DHCP if ip.get("mode") == "dhcp" else MODE_STATIC)
        if ip.get("mode") == "dhcp":
            v4 = next((x for x in node.props.get("ipv4") or [] if x.get("origin") != "link_local"), None)
            gw = next((r.get("next_hop") for r in self.topology.snapshot.get("default_routes") or []
                       if r.get("adapter") == node.id and r.get("family") == 4), "")
            self.edIpAddress.setText(v4["address"] if v4 else "")
            self.edMask.setText(prefix_to_mask(v4["prefix"]) if v4 and v4.get("prefix") else "")
            self.edGateway.setText(gw or "")
        else:
            self.edIpAddress.setText(ip.get("address") or "")
            self.edMask.setText(prefix_to_mask(ip["prefix"]) if isinstance(ip.get("prefix"), int) else "")
            self.edGateway.setText(ip.get("gateway") or "")

        dns = state[ChangeKind.DNS4]
        self.cmbDnsMode.setCurrentIndex(DNS_AUTO if dns.get("mode") == "auto" else DNS_MANUAL)
        servers = dns.get("servers") or (node.props.get("dns4") if dns.get("mode") == "auto" else []) or []
        self.edDns1.setText(servers[0] if len(servers) > 0 else "")
        self.edDns2.setText(servers[1] if len(servers) > 1 else "")

        metric = state[ChangeKind.METRIC]
        self.chkAutoMetric.setChecked(bool(metric.get("auto")))
        self.spnMetric.setValue(int(metric.get("metric") or node.props.get("metric4") or 25))
        self.spnMtu.setValue(int(state[ChangeKind.MTU].get("mtu") or 1500))

        self.cmbShareFrom.clear()
        self.cmbShareFrom.addItem(tr("(paylaşım yok)"), None)
        for other in sorted(self.topology.nodes.values(), key=lambda n: n.label.lower()):
            if not other.is_adapter or other.id == node.id or other.kind in _NOT_SHAREABLE or other.hidden:
                continue
            suffix = " — " + tr("internet çıkışı") if other.id == self.topology.internet_via else ""
            self.cmbShareFrom.addItem(f"{other.label}{suffix}", other.id)
        ics = state[ChangeKind.ICS]
        idx = self.cmbShareFrom.findData(ics.get("public")) if ics.get("private") == node.id else 0
        self.cmbShareFrom.setCurrentIndex(max(0, idx))

        self._adv_edits = dict(state[ChangeKind.ADVANCED].get("values") or {})
        self._render_adv_values()
        self._load_adv_editor(self.treeAdvanced.currentItem())

        self._set_pending_label(pending)
        self._sync_enabled()

    def _set_pending_label(self, count: int, error: str = ""):
        if error:
            self.lblPending.setStyleSheet(f"color: {RED.name()}")
            self.lblPending.setText(error)
        else:
            self.lblPending.setStyleSheet("")
            self.lblPending.setText(tr("{count} bekleyen değişiklik").format(count=count) if count else "")

    def _sync_enabled(self, *_):
        static = self.cmbIpv4Mode.currentIndex() == MODE_STATIC
        for w in (self.edIpAddress, self.edMask, self.edGateway):
            w.setReadOnly(not static)
            w.setEnabled(static)
        manual = self.cmbDnsMode.currentIndex() == DNS_MANUAL
        for w in (self.edDns1, self.edDns2):
            w.setEnabled(manual)
        self.spnMetric.setEnabled(not self.chkAutoMetric.isChecked())

    def form_changes(self) -> tuple[list[Change], list[tuple[str, str]]]:
        """Formu su anki durumla karsilastirir: (eklenecekler, kuyruktan cikarilacaklar)."""
        node = self._node
        state = self._current_state(node)
        wanted: dict[ChangeKind, dict] = {
            ChangeKind.RENAME: {"name": self.edName.text().strip()},
            ChangeKind.ENABLED: {"enabled": self.chkEnabled.isChecked()},
        }
        if self.cmbIpv4Mode.currentIndex() == MODE_DHCP:
            wanted[ChangeKind.IPV4] = {"mode": "dhcp"}
        else:
            wanted[ChangeKind.IPV4] = {"mode": "static",
                                       "address": self.edIpAddress.text().strip() or None,
                                       "prefix": parse_prefix(self.edMask.text()),
                                       "gateway": self.edGateway.text().strip() or None}
        if self.cmbDnsMode.currentIndex() == DNS_AUTO:
            wanted[ChangeKind.DNS4] = {"mode": "auto"}
        else:
            wanted[ChangeKind.DNS4] = {"mode": "manual", "servers": [
                s for s in (self.edDns1.text().strip(), self.edDns2.text().strip()) if s]}
        wanted[ChangeKind.METRIC] = ({"auto": True} if self.chkAutoMetric.isChecked()
                                     else {"auto": False, "metric": self.spnMetric.value()})
        wanted[ChangeKind.MTU] = {"mtu": self.spnMtu.value()}
        pub = self.cmbShareFrom.currentData()
        wanted[ChangeKind.ICS] = {"public": pub, "private": node.id if pub else None}
        props = advanced_props(node)
        wanted[ChangeKind.ADVANCED] = {"values": {k: v for k, v in self._adv_edits.items()
                                                  if k in props and v != advanced_registry(props[k])}}

        add, remove = [], []
        for kind, params in wanted.items():
            target = HOST_TARGET if kind == ChangeKind.ICS else node.id
            current = state[kind]
            if kind == ChangeKind.ICS:
                if params == current:
                    pending = self.changes.get(kind, target) if self.changes else None
                    if pending and node.id in (pending.params.get("private"), current.get("private")):
                        remove.append((kind.value, target))
                    continue
                if not pub:                                # bu hedefe paylasimi kapat
                    params = {"public": None, "private": None}
            elif params == current:
                remove.append((kind.value, target))
                continue
            add.append(Change(kind, target, params))
        return add, remove

    # ----------------------------------------------------------------- akilli varsayilanlar
    def _on_mode_chosen(self, index: int):
        """Kullanici 'Elle (statik)' secince: maske bossa 255.255.255.0, imlec IP'ye."""
        if index != MODE_STATIC:
            return
        if not self.edMask.text().strip():
            self.edMask.setText(DEFAULT_MASK)
        if not self.edIpAddress.text().strip():
            self.edIpAddress.setFocus()

    def _on_ip_finished(self):
        text = self.edIpAddress.text().strip()
        if "/" in text:                                    # 192.168.1.10/24 -> IP + maske
            addr, _, pfx = text.partition("/")
            prefix = parse_prefix(pfx)
            self.edIpAddress.setText(addr)
            if prefix:
                self.edMask.setText(prefix_to_mask(prefix))
        elif text and not self.edMask.text().strip():
            self.edMask.setText(DEFAULT_MASK)

    def _on_mask_finished(self):
        prefix = parse_prefix(self.edMask.text())
        if prefix:                                         # '24' / '/24' -> 255.255.255.0
            self.edMask.setText(prefix_to_mask(prefix))

    def _update_gateway_hint(self, *_):
        hint = gateway_hint(self.edIpAddress.text().split("/")[0], self.edMask.text())
        # Ag gecidi BILEREK otomatik yazilmaz: yanlis/olmayan ag gecidi, dusuk metrikli
        # kartta varsayilan rotayi ele gecirip interneti kesebilir. Yalnizca oneri.
        self.edGateway.setPlaceholderText(tr("öneri: {hint} — boş bırakılabilir").format(hint=hint) if hint
                                          else tr("boş bırakılabilir"))

    def _validated_changes(self):
        """(eklenecekler, cikarilacaklar) ya da hata varsa None (hata etikette gosterilir)."""
        if self._node is None:
            return None
        self._on_ip_finished()
        self._on_mask_finished()
        add, remove = self.form_changes()
        errors = [i.message for c in add for i in validate(c, self.topology) if i.severity == Severity.ERROR]
        if errors:
            self._set_pending_label(0, tr("Düzeltin: {error}").format(error=errors[0]))
            return None
        return add, remove

    def _submit(self) -> bool:
        """Toplu kip: formu kuyruga al."""
        result = self._validated_changes()
        if result is None:
            return False
        self.formSubmitted.emit(self._node.id, *result)
        return True

    def _submit_and_apply(self):
        """Varsayilan: formdaki degisiklikleri DOGRUDAN uygula (kuyruk ve pencere yok)."""
        result = self._validated_changes()
        if result is not None:
            self.formApplyRequested.emit(self._node.id, result[0])

    def set_queue_mode(self, on: bool):
        """Toplu kipte 'Kuyruğa ekle' gorunur; varsayilan kipte yalnizca 'Uygula'."""
        self.btnQueue.setVisible(on)
        self.btnApplyNow.setText(tr("Hemen uygula…") if on else tr("Uygula"))
        self.lblReadOnly.setText(
            tr("Değişiklikler önce kuyruğa girer; alttaki “Bekleyen değişiklikler” panelinden Uygula ile "
               "tek yönetici onayıyla uygulanır.") if on else
            tr("“Uygula” değişikliği hemen uygular. İnternet bağlantınızı taşıyan karta dokunan "
               "değişikliklerde diyagramın üstünde 30 sn “Koru / Geri al” şeridi çıkar."))

    def _show_synthetic(self, node: Node):
        rows = [(tr("Tür"), kind_label(node.kind)), (tr("Durum"), status_text(node.status))]
        if node.kind == NodeKind.GATEWAY:
            owner = self.topology.nodes.get(node.props.get("adapter"))
            rows += [(tr("IP adresi"), node.props.get("ip")), (tr("MAC adresi"), node.props.get("mac")),
                     (tr("Bağdaştırıcı"), owner.label if owner else None),
                     (tr("İnternet erişimi"), connectivity_text(node.connectivity))]
        elif node.kind == NodeKind.DHCP_CLIENTS:
            owner = self.topology.nodes.get(node.props.get("adapter"))
            rows = [(tr("Tür"), kind_label(node.kind)), (tr("Bağdaştırıcı"), owner.label if owner else None),
                    (tr("Sunucu IP'si"), node.props.get("server_ip"))]
            rows += [(c.get("ip"), " · ".join(x for x in (c.get("hostname"), c.get("mac")) if x))
                     for c in node.props.get("clients") or []]
        else:
            via = self.topology.nodes.get(self.topology.internet_via or "")
            rows.append((tr("Çıkış bağdaştırıcısı"), via.label if via else None))
            rows += [(tr("Not"), b.message) for b in self.topology.host_badges]
        self._fill_info(rows)

    # ----------------------------------------------------------------- kenar
    def show_edge(self, edge_id: str):
        topo = self.topology
        edge = next((e for e in topo.edges if e.id == edge_id), None) if topo else None
        if edge is None:
            self.clear()
            return
        self._node = None
        title = edge_title(edge.kind)
        src, dst = topo.nodes[edge.src], topo.nodes[edge.dst]
        self.lblIcon.clear()
        self.lblTitle.setText(title)
        self.lblSubtitle.setText(f"{src.label} → {dst.label}")
        rows = [(tr("İlişki"), title), (tr("Kaynak"), src.label), (tr("Hedef"), dst.label),
                (tr("Etiket"), edge.label), (tr("İnternete çıkan yol"), edge.active)]
        rows += [(tr("Kanıt"), ev) for ev in edge.evidence]
        self._fill_info(rows)

    def _fill_info(self, rows):
        self.treeInfo.clear()
        for key, value in rows:
            QTreeWidgetItem(self.treeInfo, [key, _dash(value)])
        self.treeInfo.resizeColumnToContents(0)
        self.stack.setCurrentIndex(PAGE_INFO)
