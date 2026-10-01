"""Cekirdek icin ceviri kancasi (Qt'siz).

core/ Qt import etmez (ai_rules/30); bu yuzden ceviri bir kanca ile gelir: arayuz
acilirken `set_translator` Qt cevirmenini baglar. Baglanmazsa kaynak dil (Turkce) doner
— testler ve komut satiri araclari boyle calisir.

Kullanim:
    tr("{name}: DHCP adresini yenile").format(name=...)   # yer tutucu metinde kalir
    LABELS = {X: N_("Ethernet")}   # modul duzeyinde: yalniz isaretle, gosterirken tr()
Cikarici (tools/i18n_update.py) tr("...") ve N_("...") cagrilarindaki sabit metinleri toplar.
"""

from __future__ import annotations

from typing import Callable

CONTEXT = "networkplus"

_translate: Callable[[str, str], str] = lambda context, text: text


def set_translator(fn: Callable[[str, str], str]) -> None:
    global _translate
    _translate = fn


def tr(text: str) -> str:
    return _translate(CONTEXT, text) if text else text


def N_(text: str) -> str:          # noqa: N802 - gettext gelenegi
    """Yalnizca isaret: ceviri gosterim aninda tr() ile yapilir."""
    return text
