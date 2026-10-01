"""Toplayici (collector) arayuzu: her platform normalize snapshot dondurur."""

from __future__ import annotations


class CollectError(RuntimeError):
    """Anlik goruntu alinamadi (arac yok, zaman asimi, gecersiz cikti)."""


class Collector:
    name = "base"

    def collect_raw(self) -> dict:
        raise NotImplementedError

    def normalize(self, raw: dict) -> dict:
        raise NotImplementedError

    def collect(self) -> dict:
        return self.normalize(self.collect_raw())
