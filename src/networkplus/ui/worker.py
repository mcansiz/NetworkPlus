"""Anlik goruntuyu arayuz is parcacigi disinda alir (PowerShell ~5 sn surer)."""

from __future__ import annotations

import time

from PyQt5.QtCore import QThread, pyqtSignal

from ..core.discovery import build_topology
from ..platform import Collector


class SnapshotThread(QThread):
    done = pyqtSignal(object, float)     # Topology, sure (sn)
    failed = pyqtSignal(str)

    def __init__(self, collector: Collector, parent=None):
        super().__init__(parent)
        self.collector = collector

    def run(self):
        start = time.monotonic()
        try:
            topo = build_topology(self.collector.collect())
        except Exception as exc:     # noqa: BLE001 - kullaniciya gosterilir
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(topo, time.monotonic() - start)
