#!/usr/bin/env python3
"""networkPlus DHCP sunucu sureci (ADR 0010).

    dhcp_daemon.py --src <src dizini> --config cfg.json --leases leases.json

- Arayuzle stdin/stdout JSON satirlari: cikti olaylar ({"event": ...}), girdi komutlar
  ({"cmd": "stop" | "reservations" | "delete_lease"}). stdin kapanirsa (arayuz kapandi/coktu)
  sunucu DURUR — yetim DHCP sunucusu kalmaz.
- Windows: adaptor IP'si:67'ye SO_EXCLUSIVEADDRUSE (ICS/baska sunucu 67'yi tutuyorsa acikca
  hata; qtDHCP ReuseAddress ile bunu gizliyordu). Linux: 0.0.0.0:67 + SO_BINDTODEVICE (kok).
- pkexec ortami temizledigi icin paket yolu --src ile verilir.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import socket
import sys
import threading
import time

SO_BINDTODEVICE = 25


def emit(obj: dict) -> None:
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def open_socket(cfg) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if os.name == "nt":
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((cfg.server_ip, 67))
    else:
        if cfg.ifname:
            s.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, cfg.ifname.encode() + b"\0")
        s.bind(("0.0.0.0", 67))
    s.settimeout(0.5)
    return s


def read_commands(q: "queue.Queue[dict]") -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            q.put(json.loads(line))
        except ValueError:
            emit({"event": "error", "code": "bad_command", "detail": line[:200]})
    q.put({"cmd": "stop", "reason": "stdin_closed"})


def _utf8_pipes() -> None:
    """Arayuz satirlari UTF-8 okur. Windows'ta boruya yazan Python yerel kod sayfasini (cp1254)
    kullaniyordu: 'Geçersiz' gibi metinler bozuk geliyordu (paket sinamasinda yakalandi)."""
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _utf8_pipes()
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--leases", required=True)
    args = ap.parse_args(argv)
    sys.path.insert(0, args.src)
    from networkplus.core.dhcp import packet as P
    from networkplus.core.dhcp.leases import DhcpConfig, LeaseManager, norm_mac, validate_config
    from networkplus.core.dhcp.server import DhcpServerCore

    with open(args.config, encoding="utf-8") as fh:
        cfg = DhcpConfig.from_dict(json.load(fh))
    errors = validate_config(cfg)
    if errors:
        emit({"event": "error", "code": "config", "detail": "; ".join(errors)})
        return 2
    leases = LeaseManager(cfg)
    if os.path.exists(args.leases):
        try:
            with open(args.leases, encoding="utf-8") as fh:
                leases.load(json.load(fh))
        except (OSError, ValueError) as exc:
            emit({"event": "log", "level": "warning", "detail": f"leases file ignored: {exc}"})
    core = DhcpServerCore(cfg, leases)

    try:
        sock = open_socket(cfg)
    except PermissionError as exc:
        emit({"event": "error", "code": "permission", "detail": str(exc)})
        return 3
    except OSError as exc:
        emit({"event": "error", "code": "bind", "errno": exc.errno, "detail": str(exc)})
        return 3

    def save():
        tmp = args.leases + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(leases.to_list(), fh, ensure_ascii=False, indent=1)
            try:
                os.chmod(tmp, 0o644)
            except OSError:
                pass
            os.replace(tmp, args.leases)
        except OSError as exc:
            emit({"event": "log", "level": "warning", "detail": f"save failed: {exc}"})

    def publish():
        save()
        emit({"event": "leases", "items": leases.to_list()})

    commands: "queue.Queue[dict]" = queue.Queue()
    threading.Thread(target=read_commands, args=(commands,), daemon=True).start()
    emit({"event": "started", "server_ip": cfg.server_ip, "pid": os.getpid(), "ifname": cfg.ifname})
    publish()

    last_tick = 0.0
    running = True
    while running:
        # -- komutlar
        while not commands.empty():
            cmd = commands.get()
            name = cmd.get("cmd")
            if name == "stop":
                running = False
                emit({"event": "stopping", "reason": cmd.get("reason", "requested")})
            elif name == "reservations":
                new = {norm_mac(m): dict(v) for m, v in (cmd.get("items") or {}).items()}
                old = cfg.reservations
                cfg.reservations = new
                bad = validate_config(cfg)
                if bad:
                    cfg.reservations = old
                    emit({"event": "error", "code": "reservations", "detail": "; ".join(bad)})
                else:
                    emit({"event": "log", "level": "info", "detail": f"reservations: {len(new)}"})
                    publish()
            elif name == "delete_lease":
                leases.leases.pop(norm_mac(cmd.get("mac", "")), None)
                publish()
        if not running:
            break
        # -- paket
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            data = None
        except OSError as exc:
            emit({"event": "error", "code": "socket", "detail": str(exc)})
            break
        now = time.time()
        if data:
            try:
                pkt = P.parse(data)
            except P.PacketError:
                pkt = None
            if pkt is not None:
                replies, events = core.handle(pkt, now)
                for r in replies:
                    try:
                        sock.sendto(r.packet.to_bytes(), (r.dest, r.port))
                    except OSError as exc:
                        emit({"event": "error", "code": "send", "detail": f"{r.dest}: {exc}"})
                emit({"event": "packet", "type": P.MSG_NAMES.get(pkt.msg_type, str(pkt.msg_type)),
                      "mac": pkt.mac, "hostname": pkt.opt_text(P.OPT_HOSTNAME) or "",
                      "reply": [P.MSG_NAMES.get(r.packet.msg_type, "?") for r in replies],
                      "ip": replies[0].packet.yiaddr if replies else ""})
                for ev in events:
                    emit({"event": "lease_event", **ev.to_dict()})
                if events or replies:
                    publish()
        if now - last_tick >= 1.0:
            last_tick = now
            expired = core.tick(now)
            for ev in expired:
                emit({"event": "lease_event", **ev.to_dict()})
            if expired:
                publish()

    save()
    sock.close()
    emit({"event": "stopped"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
