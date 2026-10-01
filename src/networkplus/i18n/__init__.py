"""Dil destegi (ADR 0008).

- Kaynak dil TURKCE. Ceviriler bu klasordeki `<kod>.ts` dosyalarinda (Qt Linguist bicimi).
- `.ts` dogrudan okunur (lrelease/derleme gerekmez); yeni dil = yeni `.ts` dosyasi.
- Dil secimi: ayar 'auto' ise isletim sistemi dili destekleniyorsa o, yoksa Ingilizce.
- `.ui` metinleri uic tarafindan QCoreApplication.translate(<sinif adi>, metin) ile,
  Python metinleri core.i18n.tr (baglam 'networkplus') ile cevrilir.
- Sozde dil 'qps' (NETWORKPLUS_LANG=qps): her cevrilen metni [!…!] icine alir; sarilmamis
  metin gozle ve testle (tests/test_i18n.py) yakalanir.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QLocale, QSettings, QTranslator

from ..core import i18n as core_i18n

I18N_DIR = Path(__file__).resolve().parent
SOURCE_LANG = "tr"
FALLBACK_LANG = "en"
PSEUDO_LANG = "qps"
SETTINGS_KEY = "ui/language"          # 'auto' | dil kodu


@dataclass
class Language:
    code: str
    name: str                          # kendi dilinde ad ("English", "Türkçe")
    path: Path | None                  # kaynak dilde None


def _meta_name(path: Path) -> str:
    """.ts icindeki '@meta' baglamindaki 'LANGUAGE_NAME' cevirisi (yoksa dosya adi)."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return path.stem
    for ctx in root.iter("context"):
        if (ctx.findtext("name") or "") != "@meta":
            continue
        for msg in ctx.iter("message"):
            if msg.findtext("source") == "LANGUAGE_NAME":
                return (msg.findtext("translation") or "").strip() or path.stem
    return path.stem


def available_languages() -> list[Language]:
    langs = [Language(SOURCE_LANG, "Türkçe", None)]  # notr: dilin kendi adi
    for path in sorted(I18N_DIR.glob("*.ts")):
        langs.append(Language(path.stem, _meta_name(path), path))
    return langs


def resolve_language(setting: str | None) -> str:
    """Ayar + isletim sistemi dili -> kullanilacak dil kodu."""
    env = os.environ.get("NETWORKPLUS_LANG")
    if env:
        return env
    codes = {lang.code for lang in available_languages()}
    if setting and setting != "auto" and setting in codes:
        return setting
    system = QLocale.system().name()          # "tr_TR", "en_US", "de_DE"
    for candidate in (system, system.split("_")[0]):
        if candidate in codes:
            return candidate
    return FALLBACK_LANG if FALLBACK_LANG in codes else SOURCE_LANG


def load_ts(path: Path) -> dict[tuple[str, str], str]:
    """(baglam, kaynak) -> ceviri. Bos ve 'unfinished'/'obsolete' ceviriler atlanir."""
    table: dict[tuple[str, str], str] = {}
    root = ET.parse(path).getroot()
    for ctx in root.iter("context"):
        name = ctx.findtext("name") or ""
        for msg in ctx.iter("message"):
            source = msg.findtext("source")
            node = msg.find("translation")
            if source is None or node is None:
                continue
            if node.get("type") in ("unfinished", "obsolete", "vanished"):
                continue
            if node.text:
                table[(name, source)] = node.text
    return table


_PSEUDO = str.maketrans("aeiouAEIOUcsgCSGnN", "àéîõüÀÉÎÕÜçšğÇŠĞñÑ")  # notr


_KEEP = re.compile(r"(\{[^{}]*\}|<[^<>]*>|%\w|&\w+;)")   # yer tutucu, HTML, %v, &nbsp;


def _pseudo(text: str) -> str:
    """Harfleri aksanli karsiliklariyla degistir; yer tutucu/HTML/bicim kodlarina dokunma."""
    return "".join(part if _KEEP.fullmatch(part) else part.translate(_PSEUDO)
                   for part in _KEEP.split(text))


class TsTranslator(QTranslator):
    """.ts dosyasini dogrudan okuyan cevirmen (derleme adimi yok)."""

    def __init__(self, table: dict[tuple[str, str], str] | None, pseudo: bool = False, parent=None):
        super().__init__(parent)
        self.table = table or {}
        self.pseudo = pseudo
        self._by_source = {}
        for (ctx, src), text in self.table.items():
            self._by_source.setdefault(src, text)

    def translate(self, context, source, disambiguation=None, n=-1):
        if not source:
            return source
        if self.pseudo:
            return f"[!{_pseudo(source)}!]"
        text = self.table.get((context, source))
        if text is None:
            text = self._by_source.get(source)      # baglam farkliysa ayni metnin cevirisi
        return text if text is not None else source

    def isEmpty(self):
        return not self.table and not self.pseudo


_installed: TsTranslator | None = None
_current = SOURCE_LANG


def install(app=None, code: str | None = None) -> str:
    """Cevirmeni kur. QApplication'dan SONRA, pencereler olusturulmadan ONCE cagrilir."""
    global _installed, _current
    app = app or QCoreApplication.instance()
    code = code or resolve_language(QSettings().value(SETTINGS_KEY, "auto"))
    if _installed is not None:
        app.removeTranslator(_installed)
        _installed = None
    if code == PSEUDO_LANG:
        _installed = TsTranslator(None, pseudo=True, parent=app)
    elif code != SOURCE_LANG:
        path = I18N_DIR / f"{code}.ts"
        if path.exists():
            _installed = TsTranslator(load_ts(path), parent=app)
        else:
            code = SOURCE_LANG
    if _installed is not None:
        app.installTranslator(_installed)
    core_i18n.set_translator(lambda ctx, text: QCoreApplication.translate(ctx, text))
    _current = code
    return code


def current_language() -> str:
    return _current


_qt_translator: QTranslator | None = None


def install_qt_translations(app, code: str) -> bool:
    """Qt'nin kendi metinleri (Evet/Hayir, Iptal, dosya diyalogu) icin PyQt5 ile gelen qtbase_<dil>.qm."""
    global _qt_translator
    from PyQt5.QtCore import QLibraryInfo
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code in (PSEUDO_LANG,):
        return False
    translator = QTranslator(app)
    if translator.load(f"qtbase_{code}", QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
        _qt_translator = translator
        return True
    return False


def save_language_setting(code: str) -> None:
    """'auto' ya da dil kodu; yeniden baslatinca gecerli olur."""
    QSettings().setValue(SETTINGS_KEY, code)


def language_setting() -> str:
    return str(QSettings().value(SETTINGS_KEY, "auto"))
