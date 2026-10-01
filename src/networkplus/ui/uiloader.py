"""Qt Designer .ui dosyalarini calisma aninda yukler (ADR 0006).

Her arayuz modulu `ui/modules/<modul>/<modul>.ui` + `<modul>.py` ciftidir.
.ui dosyasi yalnizca yerlesim ve gorunumu tasir; davranis .py icindedir.
.ui Designer'da degistirilip kaydedilince derleme gerekmez: bir sonraki
acilista yeni hali yuklenir.

Kural: .py kodu .ui'deki nesnelere `objectName` ile erisir. Designer'da bir
nesnenin adi degistirilirse `require()` acilista hangi adin eksik oldugunu
soyler (sessizce AttributeError yerine).
"""

from __future__ import annotations

from pathlib import Path

from PyQt5 import uic
from PyQt5.QtWidgets import QWidget


def load_ui(widget: QWidget, module_file: str, ui_name: str | None = None) -> None:
    """`module_file` (genellikle __file__) yanindaki .ui dosyasini `widget` uzerine yukler."""
    here = Path(module_file).resolve()
    path = here.with_name(ui_name or f"{here.stem}.ui")
    uic.loadUi(str(path), widget)


def require(widget: QWidget, *names: str) -> None:
    missing = [n for n in names if not hasattr(widget, n)]
    if missing:
        raise RuntimeError(
            f"{type(widget).__name__}: .ui dosyasinda beklenen nesne(ler) yok: {', '.join(missing)}. "
            "Designer'da objectName degistirildiyse .py tarafini da guncelleyin."
        )
