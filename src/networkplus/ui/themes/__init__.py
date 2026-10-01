"""QSS temalari (ADR 0011): `themes/*.qss` dosyalari = menude tema.

Her .qss iki seyi tasir:
- Stil sayfasi (normal QSS) — parcaciklarin gorunumu.
- Bas yorumdaki `@name:` ve `@palette <rol>: <renk>` satirlari — Qt renk paleti. QSS paleti
  degistirmez; diyagram (QPainter) paletle cizildigi icin palet ayrica uygulanir.

Ayar (`ui/theme`): 'auto' (isletim sisteminin acik/koyu ayari; varsayilan), 'system' (yerel
gorunum, stil sayfasi yok — eski davranis) ya da dosya adi ('light', 'dark', kullanicinin
ekledigi...). Tema calisirken degistirilebilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication, QStyleFactory

from ...core.i18n import N_, tr

THEMES_DIR = Path(__file__).resolve().parent
SETTINGS_KEY = "ui/theme"
AUTO, SYSTEM = "auto", "system"
DEFAULT = AUTO
# Hazir temalarin adlari cevrilir; kullanicinin ekledigi temada @name oldugu gibi gosterilir.
BUILTIN_NAMES = {"light": N_("Açık tema"), "dark": N_("Koyu tema")}   # "Açık" tek başına "on" ile karışır

_ROLES = {
    "window": QPalette.Window, "window-text": QPalette.WindowText, "base": QPalette.Base,
    "alternate-base": QPalette.AlternateBase, "text": QPalette.Text, "button": QPalette.Button,
    "button-text": QPalette.ButtonText, "bright-text": QPalette.BrightText,
    "highlight": QPalette.Highlight, "highlighted-text": QPalette.HighlightedText,
    "tooltip-base": QPalette.ToolTipBase, "tooltip-text": QPalette.ToolTipText,
    "link": QPalette.Link, "placeholder-text": QPalette.PlaceholderText,
    "light": QPalette.Light, "midlight": QPalette.Midlight, "mid": QPalette.Mid,
    "dark": QPalette.Dark, "shadow": QPalette.Shadow,
}
_PALETTE_RE = re.compile(r"@palette\s+(disabled\s+)?([a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,8}|[a-z]+)")
_NAME_RE = re.compile(r"@name\s*:\s*(.+)")

_native_style: str | None = None
_current: str | None = None


@dataclass
class Theme:
    code: str
    path: Path
    meta_name: str = ""
    palette: dict[tuple[bool, str], str] = field(default_factory=dict)   # (devre disi mi, rol) -> renk

    @property
    def name(self) -> str:
        if self.code in BUILTIN_NAMES:
            return tr(BUILTIN_NAMES[self.code])
        return self.meta_name or self.code

    @property
    def is_dark(self) -> bool:
        window = self.palette.get((False, "window"))
        return window is not None and QColor(window).lightness() < 128


def parse_theme(path: Path) -> Theme:
    text = path.read_text(encoding="utf-8")
    header = text[: text.find("*/")] if text.lstrip().startswith("/*") else ""
    theme = Theme(path.stem, path)
    m = _NAME_RE.search(header)
    if m:
        theme.meta_name = m.group(1).strip()
    for disabled, role, color in _PALETTE_RE.findall(header):
        if role in _ROLES and QColor(color).isValid():
            theme.palette[(bool(disabled), role)] = color
    return theme


def user_themes_dir() -> Path:
    """Kullanicinin tema klasoru. Tek dosya pakette hazir temalar exe'nin icindedir (duzenlenemez);
    buraya konan .qss menude gorunur, ayni addaki hazir temanin yerine gecer."""
    from PyQt5.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)) / "themes"


def available_themes() -> list[Theme]:
    """Hazir temalar once (acik, koyu), sonra kullanicinin ekledikleri (ada gore)."""
    found: dict[str, Path] = {p.stem: p for p in THEMES_DIR.glob("*.qss")}
    user_dir = user_themes_dir()
    if user_dir.is_dir():
        found.update({p.stem: p for p in user_dir.glob("*.qss")})
    themes = [parse_theme(p) for p in found.values()]
    order = list(BUILTIN_NAMES)
    return sorted(themes, key=lambda t: (order.index(t.code) if t.code in order else len(order), t.name.lower()))


def theme_setting() -> str:
    return QSettings().value(SETTINGS_KEY, DEFAULT, type=str) or DEFAULT


def save_theme_setting(code: str) -> None:
    QSettings().setValue(SETTINGS_KEY, code)


_ASK_OS = object()


def resolve_theme(setting: str, prefers_dark=_ASK_OS) -> str:
    """Ayar -> uygulanacak tema kodu ya da SYSTEM. 'auto': isletim sistemi koyu ise 'dark'.
    `prefers_dark` verilmezse isletim sistemine sorulur; None = bilinmiyor (acik)."""
    codes = {t.code for t in available_themes()}
    if setting == SYSTEM:
        return SYSTEM
    if setting != AUTO and setting in codes:
        return setting
    if prefers_dark is _ASK_OS:
        from ...platform import system_prefers_dark
        prefers_dark = system_prefers_dark()
    wanted = "dark" if prefers_dark else "light"
    return wanted if wanted in codes else SYSTEM


def build_palette(theme: Theme) -> QPalette:
    pal = QPalette()
    for (disabled, role), color in theme.palette.items():
        groups = (QPalette.Disabled,) if disabled else (QPalette.Active, QPalette.Inactive, QPalette.Disabled)
        for group in groups:
            if not disabled and (True, role) in theme.palette and group == QPalette.Disabled:
                continue                                  # ozel devre disi rengi var
            pal.setColor(group, _ROLES[role], QColor(color))
    return pal


def apply_theme(app: QApplication, setting: str | None = None) -> str:
    """Temayi uygula; uygulanan kodu dondur ('system' ya da tema kodu)."""
    global _native_style, _current
    if _native_style is None:
        _native_style = app.style().objectName()
    code = resolve_theme(setting if setting is not None else theme_setting())
    if code == SYSTEM:
        app.setStyleSheet("")
        style = QStyleFactory.create(_native_style) if _native_style else None
        if style is not None:
            app.setStyle(style)
            app.setPalette(style.standardPalette())
    else:
        theme = next(t for t in available_themes() if t.code == code)
        app.setStyle(QStyleFactory.create("Fusion"))      # palet ve QSS'i en tutarli uygulayan stil
        app.setPalette(build_palette(theme))
        app.setStyleSheet(theme.path.read_text(encoding="utf-8"))
    _current = code
    return code


def current_theme() -> str | None:
    return _current
