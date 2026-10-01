"""DHCP sunucusu paneli (ADR 0010): kart secimi, ayarlar, baslat/durdur, kiralar, rezervasyonlar, gunluk.

Sunucu sureci DhcpService'tedir (ayri surec, JSON satirlari); bu modul yalnizca arayuz.
Kartin statik IP'si yoksa (ya da "Sunucu IP'si" farkliysa) once `staticIpRequested` ile
ana pencereden statik adres uygulanir; sonuc `on_static_result` ile gelir, bir sonraki
okumada adres kartta gorulunce sunucu baslar.
"""

from __future__ import annotations

import ipaddress
import json
import time

from PyQt5.QtCore import QSettings, QTimer, pyqtSignal
from PyQt5.QtWidgets import QHeaderView, QTableWidgetItem, QWidget

from ...dhcp_service import leases_path
from ...theme import AMBER, GREEN, RED
from ...uiloader import load_ui, require
from ....core.dhcp.guard import AdapterCheck, check_adapter, eligible_adapters, static_ipv4
from ....core.dhcp.leases import DhcpConfig, norm_mac, suggest_config, validate_config
from ....core.i18n import N_, tr
from ....core.model import Topology

SETTINGS_PREFIX = "dhcp/config/"
LAST_ADAPTER_KEY = "dhcp/lastAdapter"
BIND_RETRIES = 3            # statik IP yeni verildiyse adres birkac sn "hazir degil" olabilir
STATIC_WAIT_S = 20          # uygulamadan sonra adresin okumada gorunmesi icin azami bekleme
STATIC_POLL_MS = 1500
RETRY_MS = 2000
_ADDR_NOT_AVAILABLE = {99, 10049}      # Linux EADDRNOTAVAIL, Windows WSAEADDRNOTAVAIL
STATE_TEXT = {"bound": N_("Kirada"), "offered": N_("Teklif edildi"), "released": N_("Bırakıldı"),
              "expired": N_("Süresi doldu")}


def parse_prefix(text: str) -> int | None:
    """'24', '/24' ya da '255.255.255.0' -> 24."""
    text = text.strip().lstrip("/")
    if not text:
        return None
    if text.isdigit():
        n = int(text)
        return n if 1 <= n <= 32 else None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{text}").prefixlen
    except ValueError:
        return None


def _key(node_id: str) -> str:
    return SETTINGS_PREFIX + "".join(c if c.isalnum() else "_" for c in node_id)


class DhcpServerPanel(QWidget):
    staticIpRequested = pyqtSignal(str, str, int)      # kart, adres, onek
    leaseNotification = pyqtSignal(str, str)           # tepsi bildirimi: baslik, metin
    clientsChanged = pyqtSignal()                      # diyagram katmani yenilensin
    refreshRequested = pyqtSignal()                    # statik IP bekleniyor: agi yeniden oku

    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui(self, __file__)
        require(self, "cmbAdapter", "lblStatus", "btnStart", "btnStop", "lblWarning", "grpSettings",
                "edServerIp", "edMask", "edPoolStart", "edPoolEnd", "edGateway", "edDns1", "edDns2",
                "spnLease", "edDomain", "tabs", "tblLeases", "btnReserve", "btnDeleteLease",
                "tblReservations", "btnAddReservation", "btnRemoveReservation", "btnSaveReservations",
                "txtLog", "btnClearLog")
        for table, stretch in ((self.tblLeases, 2), (self.tblReservations, 2)):
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)     # MAC/IP kirpilmasin
            header.setSectionResizeMode(stretch, QHeaderView.Stretch)      # cihaz adi kalan yeri alir
            table.verticalHeader().hide()
        self.service = None
        self.preflight = None             # () -> (ok, uyari): ör. Windows guvenlik duvari kurali
        self.topology: Topology | None = None
        self.live = True
        self.check = AdapterCheck(False)
        self.leases: list[dict] = []
        self.running_node: str | None = None
        self.running_config: DhcpConfig | None = None
        self._pending: DhcpConfig | None = None       # statik IP bekleyen baslatma
        self._pending_state = ""                      # "applying" | "waiting"
        self._retries = 0
        self._last_bind_errno = None
        self._clients_sig: tuple = ()
        self._filling = False

        self.cmbAdapter.currentIndexChanged.connect(self._on_adapter_changed)
        self.btnStart.clicked.connect(self.start)
        self.btnStop.clicked.connect(self.stop)
        self.edServerIp.editingFinished.connect(self._on_network_edited)
        self.edMask.editingFinished.connect(self._on_network_edited)
        self.edServerIp.textChanged.connect(lambda _t: self._sync_buttons())
        self.btnReserve.clicked.connect(self._reserve_selected)
        self.btnDeleteLease.clicked.connect(self._delete_selected_lease)
        self.btnAddReservation.clicked.connect(self._add_reservation_row)
        self.btnRemoveReservation.clicked.connect(self._remove_reservation_rows)
        self.btnSaveReservations.clicked.connect(self._save_reservations)
        self.btnClearLog.clicked.connect(self.txtLog.clear)
        self.tblLeases.itemSelectionChanged.connect(self._sync_buttons)
        self._set_status(tr("Durdu"), None)
        self._sync_buttons()

    # ----------------------------------------------------------------- genel API
    def attach(self, service, preflight=None):
        if self.service is not None:
            for sig, slot in self._service_slots():
                try:
                    sig.disconnect(slot)
                except TypeError:
                    pass
        self.service = service
        self.preflight = preflight
        for sig, slot in self._service_slots():
            sig.connect(slot)

    def _service_slots(self):
        s = self.service
        return [(s.started, self._on_started), (s.stopped, self._on_stopped), (s.message, self._on_event)]

    @property
    def running(self) -> bool:
        return self.service is not None and self.service.running

    def set_live(self, live: bool):
        self.live = live
        self._evaluate()

    def set_topology(self, topo: Topology):
        self.topology = topo
        current = self.selected_adapter() or QSettings().value(LAST_ADAPTER_KEY, "", type=str)
        self._filling = True
        self.cmbAdapter.clear()
        for node in eligible_adapters(topo):
            static = static_ipv4(node)
            ips = [a.get("address") for a in node.props.get("ipv4") or [] if a.get("address")]
            shown = f"{static[0]}/{static[1]}" if static else (ips[0] if ips else tr("IP yok"))
            self.cmbAdapter.addItem(f"{node.label} — {shown}", node.id)
        index = self.cmbAdapter.findData(self.running_node or current)
        self._filling = False
        if index >= 0:
            self.cmbAdapter.setCurrentIndex(index)
        if self.cmbAdapter.currentIndex() >= 0 and not self.form_loaded_for(self.selected_adapter()):
            self._load_form(self.selected_adapter())
        self._evaluate()
        self._continue_pending()

    def select_adapter(self, node_id: str) -> bool:
        index = self.cmbAdapter.findData(node_id)
        if index < 0 or (self.running and node_id != self.running_node):
            return False
        self.cmbAdapter.setCurrentIndex(index)
        return True

    def selected_adapter(self) -> str:
        return self.cmbAdapter.currentData() or ""

    def form_loaded_for(self, node_id: str) -> bool:
        return getattr(self, "_form_node", None) == node_id

    def overlay(self) -> tuple[str, str, list[dict]] | None:
        """Diyagram icin: (kart, sunucu IP'si, etkin istemciler); calismiyorsa None."""
        if not self.running or self.running_node is None or self.running_config is None:
            return None
        return self.running_node, self.running_config.server_ip, self.active_clients()

    def active_clients(self) -> list[dict]:
        now = time.time()
        return [l for l in self.leases if l.get("state") == "bound" and float(l.get("expires") or 0) > now]

    def shutdown(self):
        self._pending = None
        if self.running:
            self.service.stop()

    # ----------------------------------------------------------------- form
    def _on_adapter_changed(self, _index: int):
        if self._filling:
            return
        node_id = self.selected_adapter()
        if node_id:
            QSettings().setValue(LAST_ADAPTER_KEY, node_id)
            self._load_form(node_id)
        self._evaluate()
        if not self.running:
            self._show_saved_leases(node_id)

    def _load_form(self, node_id: str):
        self._form_node = node_id
        saved = QSettings().value(_key(node_id), "", type=str)
        cfg = None
        if saved:
            try:
                cfg = DhcpConfig.from_dict(json.loads(saved))
            except (ValueError, TypeError):
                cfg = None
        node = self.topology.nodes.get(node_id) if self.topology else None
        static = static_ipv4(node) if node else None
        if cfg is None:
            ip, prefix = static or self._free_subnet()
            cfg = suggest_config(ip, prefix)
        self._fill_form(cfg)

    def _free_subnet(self) -> tuple[str, int]:
        """Statik IP'si olmayan kart icin: hicbir kartin agiyla cakismayan 192.168.77-99.1/24."""
        used = []
        for node in (self.topology.nodes.values() if self.topology else []):
            for a in node.props.get("ipv4") or []:
                try:
                    used.append(ipaddress.IPv4Interface(f"{a['address']}/{a.get('prefix') or 24}").network)
                except (KeyError, ValueError):
                    pass
        for third in range(77, 100):
            net = ipaddress.IPv4Network(f"192.168.{third}.0/24")
            if not any(net.overlaps(u) for u in used):
                return f"192.168.{third}.1", 24
        return "10.77.0.1", 24

    def _fill_form(self, cfg: DhcpConfig):
        self.edServerIp.setText(cfg.server_ip)
        self.edMask.setText(str(ipaddress.IPv4Network(f"0.0.0.0/{cfg.prefix}").netmask))
        self.edPoolStart.setText(cfg.pool_start)
        self.edPoolEnd.setText(cfg.pool_end)
        self.edGateway.setText(cfg.gateway or "")
        dns = list(cfg.dns) + ["", ""]
        self.edDns1.setText(dns[0])
        self.edDns2.setText(dns[1])
        self.spnLease.setValue(max(1, int(cfg.lease_time) // 60))
        self.edDomain.setText(cfg.domain or "")
        self.tblReservations.setRowCount(0)
        for mac, r in cfg.reservations.items():
            self._append_reservation(mac, r.get("ip", ""), r.get("name", ""))

    def _on_network_edited(self):
        """Akilli varsayilan: sunucu IP'si/maske degisip havuz alt agin disinda kaldiysa havuzu yeniden oner."""
        prefix = parse_prefix(self.edMask.text())
        try:
            iface = ipaddress.IPv4Interface(f"{self.edServerIp.text().strip()}/{prefix or 24}")
        except ValueError:
            return
        if prefix is None:
            self.edMask.setText(str(iface.netmask))
        net = iface.network

        def inside(text):
            try:
                return ipaddress.IPv4Address(text.strip()) in net
            except ValueError:
                return False
        if not (inside(self.edPoolStart.text()) and inside(self.edPoolEnd.text())):
            s = suggest_config(str(iface.ip), net.prefixlen)
            self.edPoolStart.setText(s.pool_start)
            self.edPoolEnd.setText(s.pool_end)
        if self.edGateway.text().strip() and not inside(self.edGateway.text()):
            self.edGateway.clear()

    def form_config(self) -> tuple[DhcpConfig | None, list[str]]:
        node_id = self.selected_adapter()
        node = self.topology.nodes.get(node_id) if self.topology else None
        if node is None:
            return None, [tr("Bağdaştırıcı seçin.")]
        prefix = parse_prefix(self.edMask.text())
        if prefix is None:
            return None, [tr("Alt ağ maskesi geçersiz.")]
        reservations, errors = self._reservations_from_table()
        cfg = DhcpConfig(
            server_ip=self.edServerIp.text().strip(), prefix=prefix,
            pool_start=self.edPoolStart.text().strip(), pool_end=self.edPoolEnd.text().strip(),
            gateway=self.edGateway.text().strip() or None,
            dns=[d for d in (self.edDns1.text().strip(), self.edDns2.text().strip()) if d],
            lease_time=self.spnLease.value() * 60, domain=self.edDomain.text().strip() or None,
            interface=node_id, ifname=str(node.props.get("name") or node_id), reservations=reservations)
        errors += validate_config(cfg)
        return cfg, errors

    def _save_settings(self, cfg: DhcpConfig):
        QSettings().setValue(_key(cfg.interface), json.dumps(cfg.to_dict(), ensure_ascii=False))

    # ----------------------------------------------------------------- denetim
    def _evaluate(self):
        node_id = self.selected_adapter()
        if not self.live:
            self.check = AdapterCheck(False, severity="error", message=tr(
                "Kaynak bir anlık görüntü dosyası; DHCP sunucusu yalnızca canlı sistemde çalışır."))
        elif self.topology is None or not node_id:
            self.check = AdapterCheck(False, message=tr("DHCP sunucusu çalıştırılabilecek bağdaştırıcı yok."),
                                      severity="warning")
        else:
            self.check = check_adapter(self.topology, node_id)
        if self.running:
            self._show_warning("", "")
        else:
            self._show_warning(self.check.message, self.check.severity)
        self._sync_buttons()

    def _needs_static(self) -> bool:
        if self.check.needs_static or self.check.needs_enable:
            return True
        prefix = parse_prefix(self.edMask.text())
        return self.check.ok and (self.edServerIp.text().strip() != self.check.server_ip
                                  or (prefix is not None and prefix != self.check.prefix))

    def _sync_buttons(self):
        running, busy = self.running, bool(self._pending)
        can_start = (self.check.ok or self.check.needs_static) and not running and not busy
        self.btnStart.setEnabled(can_start)
        self.btnStart.setText(tr("Karta statik IP ver ve başlat") if (can_start and self._needs_static())
                              else tr("Başlat"))
        self.btnStop.setEnabled(running or busy)
        self.cmbAdapter.setEnabled(not running and not busy)
        self.grpSettings.setEnabled(not running and not busy)
        has_lease = bool(self.tblLeases.selectedItems())
        self.btnReserve.setEnabled(has_lease)
        self.btnDeleteLease.setEnabled(has_lease and running)

    def _show_warning(self, message: str, severity: str):
        color = {"error": RED, "warning": AMBER}.get(severity)
        self.lblWarning.setText(message)
        self.lblWarning.setStyleSheet(f"color: {color.name()};" if color else "")
        self.lblWarning.setVisible(bool(message))

    def _set_status(self, text: str, color):
        self.lblStatus.setText(text)
        self.lblStatus.setStyleSheet(f"color: {color.name()}; font-weight: bold;" if color else "")

    # ----------------------------------------------------------------- baslat / durdur
    def start(self):
        if self.running or self._pending:
            return
        self._evaluate()
        if not (self.check.ok or self.check.needs_static):
            return
        cfg, errors = self.form_config()
        if errors:
            self._show_warning("\n".join(errors), "error")
            return
        self._save_settings(cfg)
        if self._needs_static():
            self._pending, self._pending_state = cfg, "applying"
            self._set_status(tr("Karta statik IP veriliyor: {ip}/{prefix}…").format(
                ip=cfg.server_ip, prefix=cfg.prefix), AMBER)
            self._log(tr("Karta statik IP veriliyor: {ip}/{prefix}…").format(ip=cfg.server_ip, prefix=cfg.prefix))
            self._sync_buttons()
            self.staticIpRequested.emit(cfg.interface, cfg.server_ip, cfg.prefix)
            return
        self._retries = 0
        self._launch(cfg)

    def on_static_result(self, ok: bool, message: str = ""):
        """Ana pencere: statik IP uygulamasi bitti. Basariliysa bir sonraki okumada sunucu baslar."""
        if self._pending is None or self._pending_state != "applying":
            return
        if not ok:
            self._pending = None
            self._set_status(tr("Durdu"), None)
            self._show_warning(tr("Statik IP uygulanamadı; sunucu başlatılmadı. {details}").format(
                details=message).strip(), "error")
            self._sync_buttons()
            return
        self._pending_state = "waiting"
        self._pending_deadline = time.monotonic() + STATIC_WAIT_S

    def _continue_pending(self):
        if self._pending is None or self._pending_state != "waiting" or self.topology is None:
            return
        cfg = self._pending
        node = self.topology.nodes.get(cfg.interface)
        visible = node is not None and static_ipv4(node) == (cfg.server_ip, cfg.prefix)
        if not visible and time.monotonic() < getattr(self, "_pending_deadline", 0):
            # Okuma uygulamadan once baslamis ya da adres (NM etkinlestirme) henuz gelmemis olabilir.
            QTimer.singleShot(STATIC_POLL_MS, self.refreshRequested)
            return
        self._pending = None
        if not visible:
            self._set_status(tr("Durdu"), None)
            self._show_warning(tr("Statik adres kartta görünmüyor; sunucu başlatılmadı."), "error")
            self._sync_buttons()
            return
        self._retries = BIND_RETRIES
        self._evaluate()
        self._launch(cfg)

    def _launch(self, cfg: DhcpConfig):
        if self.preflight is not None:
            ok, warning = self.preflight()
            if not ok and warning:
                self._log(warning)
                self._show_warning(warning, "warning")
        self.running_node, self.running_config = cfg.interface, cfg
        self._last_bind_errno = None
        self._set_status(tr("Başlatılıyor…"), AMBER)
        self.service.start(cfg)
        self._sync_buttons()

    def _retry_launch(self):
        cfg, self._retry_config = getattr(self, "_retry_config", None), None
        if cfg is not None and not self.running and self.running_node == cfg.interface:
            self._launch(cfg)

    def stop(self):
        self._retry_config = None
        if self._pending is not None:
            self._pending = None
            self._set_status(tr("Durdu"), None)
            self._sync_buttons()
        self._retries = 0
        if self.running:
            self.service.stop()

    # ----------------------------------------------------------------- surec olaylari
    def _on_started(self, ev: dict):
        cfg = self.running_config
        node = self.topology.nodes.get(cfg.interface) if (self.topology and cfg) else None
        self._retries = 0
        self._set_status(tr("Çalışıyor: {ip} · {adapter}").format(
            ip=ev.get("server_ip") or (cfg.server_ip if cfg else ""), adapter=node.label if node else ""), GREEN)
        self._show_warning("", "")
        self._log(tr("Sunucu başladı ({ip}).").format(ip=ev.get("server_ip", "")))
        self._sync_buttons()
        self._emit_clients(force=True)

    def _on_stopped(self, error: str):
        cfg = self.running_config
        if error and self._retries > 0 and self._last_bind_errno in _ADDR_NOT_AVAILABLE and cfg is not None:
            self._retries -= 1
            self._log(tr("Adres henüz hazır değil; yeniden deneniyor…"))
            self._retry_config = cfg
            QTimer.singleShot(RETRY_MS, self._retry_launch)       # bagli metot: panel silinirse dusmez
            return
        self.running_node = None
        self._retries = 0
        if error:
            self._set_status(tr("Durdu (hata)"), RED)
            self._show_warning(error, "error")
            self._log(tr("Hata: {error}").format(error=error))
        else:
            self._set_status(tr("Durdu"), None)
            self._log(tr("Sunucu durdu."))
            self._evaluate()
        self._sync_buttons()
        self._emit_clients(force=True)

    def _on_event(self, ev: dict):
        kind = ev.get("event")
        if kind == "leases":
            self._set_leases(ev.get("items") or [])
        elif kind == "packet":
            reply = ", ".join(ev.get("reply") or []) or "—"
            host = f" ({ev['hostname']})" if ev.get("hostname") else ""
            ip = f" {ev['ip']}" if ev.get("ip") and ev.get("ip") != "0.0.0.0" else ""
            self._log(f"{ev.get('type')} {ev.get('mac')}{host} → {reply}{ip}")
        elif kind == "lease_event":
            self._on_lease_event(ev)
        elif kind == "error":
            if ev.get("code") == "bind":
                self._last_bind_errno = ev.get("errno")
            self._log(tr("Hata: {error}").format(error=ev.get("detail") or ev.get("code")))
        elif kind == "log":
            self._log(str(ev.get("detail", "")))

    def _on_lease_event(self, ev: dict):
        k = ev.get("kind")
        who = ev.get("hostname") or ev.get("mac", "")
        texts = {
            "lease_new": tr("Yeni cihaz: {who} → {ip}"),
            "lease_renew": tr("Kira yenilendi: {who} → {ip}"),
            "release": tr("Cihaz adresini bıraktı: {who} ({ip})"),
            "decline": tr("Cihaz adresi reddetti (ağda başka kullanan var): {who} ({ip})"),
            "nak": tr("İstek reddedildi (NAK): {who} ({ip})"),
            "exhausted": tr("Havuz doldu: {who} adres alamadı"),
            "expired": tr("Kira süresi doldu: {who} ({ip})"),
        }
        if k in texts:
            self._log(texts[k].format(who=who, ip=ev.get("ip", "")))
        if k == "lease_new":
            self.leaseNotification.emit(tr("DHCP: yeni cihaz"), tr("{who} → {ip}").format(who=who, ip=ev.get("ip", "")))
        elif k == "exhausted":
            self.leaseNotification.emit(tr("DHCP: havuz doldu"), texts[k].format(who=who, ip=""))

    # ----------------------------------------------------------------- kiralar
    def _set_leases(self, items: list[dict]):
        self.leases = list(items)
        self.tblLeases.setRowCount(0)
        for l in self.leases:
            row = self.tblLeases.rowCount()
            self.tblLeases.insertRow(row)
            expires = float(l.get("expires") or 0)
            state = l.get("state", "")
            values = [l.get("mac", ""), l.get("ip", ""), l.get("hostname", ""),
                      self._time_text(expires),
                      tr(STATE_TEXT[state]) if state in STATE_TEXT else state]
            for col, value in enumerate(values):
                self.tblLeases.setItem(row, col, QTableWidgetItem(str(value)))
        self.tabs.setTabText(0, tr("Kiralar ({count})").format(count=len(self.active_clients())))
        self._sync_buttons()
        self._emit_clients()

    @staticmethod
    def _time_text(ts: float) -> str:
        if not ts:
            return "—"
        same_day = time.localtime(ts)[:3] == time.localtime()[:3]
        return time.strftime("%H:%M" if same_day else "%d.%m %H:%M", time.localtime(ts))

    def _show_saved_leases(self, node_id: str):
        """Sunucu calismiyorken son kiralari diskten goster (salt okunur)."""
        items = []
        try:
            items = json.loads(leases_path(node_id).read_text(encoding="utf-8")) if node_id else []
        except (OSError, ValueError):
            items = []
        self._set_leases(items if isinstance(items, list) else [])

    def _emit_clients(self, force: bool = False):
        overlay = self.overlay()
        sig = (overlay[0], tuple((c.get("mac"), c.get("ip"), c.get("hostname")) for c in overlay[2])) if overlay else ()
        if force or sig != self._clients_sig:
            self._clients_sig = sig
            self.clientsChanged.emit()

    def _selected_lease(self) -> dict | None:
        rows = {i.row() for i in self.tblLeases.selectedItems()}
        return self.leases[min(rows)] if rows and min(rows) < len(self.leases) else None

    def _reserve_selected(self):
        lease = self._selected_lease()
        if lease is None:
            return
        mac = norm_mac(lease.get("mac", ""))
        for row in range(self.tblReservations.rowCount()):
            if norm_mac(self._cell(self.tblReservations, row, 0)) == mac:
                self.tblReservations.removeRow(row)
                break
        self._append_reservation(mac, lease.get("ip", ""), lease.get("hostname", ""))
        self._save_reservations()
        self.tabs.setCurrentWidget(self.tabReservations)

    def _delete_selected_lease(self):
        lease = self._selected_lease()
        if lease is not None and self.running:
            self.service.delete_lease(lease.get("mac", ""))
            self._log(tr("Kira silindi: {mac}").format(mac=lease.get("mac", "")))

    # ----------------------------------------------------------------- rezervasyonlar
    @staticmethod
    def _cell(table, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _append_reservation(self, mac: str, ip: str, name: str):
        row = self.tblReservations.rowCount()
        self.tblReservations.insertRow(row)
        for col, value in enumerate((mac, ip, name)):
            self.tblReservations.setItem(row, col, QTableWidgetItem(value))
        return row

    def _add_reservation_row(self):
        row = self._append_reservation("", "", "")
        self.tblReservations.setCurrentCell(row, 0)
        self.tblReservations.editItem(self.tblReservations.item(row, 0))

    def _remove_reservation_rows(self):
        for row in sorted({i.row() for i in self.tblReservations.selectedItems()}, reverse=True):
            self.tblReservations.removeRow(row)

    def _reservations_from_table(self) -> tuple[dict, list[str]]:
        items, errors = {}, []
        for row in range(self.tblReservations.rowCount()):
            mac, ip, name = (self._cell(self.tblReservations, row, c) for c in range(3))
            if not mac and not ip:
                continue
            if not mac or not ip:
                errors.append(tr("Rezervasyon satırı {row}: MAC ve IP birlikte girilmeli.").format(row=row + 1))
                continue
            items[norm_mac(mac)] = {"ip": ip, "name": name}
        return items, errors

    def _save_reservations(self):
        items, errors = self._reservations_from_table()
        if self.running and self.running_config is not None:
            cfg = DhcpConfig.from_dict({**self.running_config.to_dict(), "reservations": items})
        else:
            cfg, form_errors = self.form_config()
            errors += [e for e in form_errors if e not in errors]
        if cfg is not None:
            errors += [e for e in validate_config(cfg) if e not in errors]
        if errors:
            self._show_warning("\n".join(errors), "error")
            return
        self._show_warning("", "")
        self._save_settings(cfg)
        if self.running:
            self.running_config = cfg
            self.service.set_reservations(items)
        self._log(tr("Rezervasyonlar kaydedildi ({count}).").format(count=len(items)))

    # ----------------------------------------------------------------- gunluk
    def _log(self, text: str):
        self.txtLog.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")
