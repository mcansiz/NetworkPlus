"""Uygulama simgesini .ico, .icns (ve .png) olarak yaz — paketleme (PyInstaller), kisayol, masaustu.

    python tools/make_app_icon.py                          # secili bicem -> src/networkplus/resources/
    python tools/make_app_icon.py --all --out .tmp/icons   # tum bicemler + karsilastirma sayfasi

Cizim `ui/app_icon.py`'dedir (tek kaynak). ICO: 16..256 px, her boyut PNG olarak gomulu
(Windows Vista+). ICNS (macOS .app, ADR 0013): 32..1024 px PNG girdileri; iconutil gerekmez. Qt'nin ICO yazicisi tek boyut yazdigi icin dosya burada elle kurulur;
ek bagimlilik yok (yalniz PyQt5 + struct).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QPointF, Qt    # noqa: E402
from PyQt5.QtGui import QColor, QFont, QImage, QPainter                 # noqa: E402
from PyQt5.QtWidgets import QApplication                                 # noqa: E402

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_bytes(pixmap) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    buf.close()
    return bytes(data)


def write_ico(path: Path, style: str) -> None:
    from networkplus.ui.app_icon import icon_pixmap
    images = [(s, png_bytes(icon_pixmap(s, style=style))) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        dim = 0 if size >= 256 else size                    # 0 = 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    path.write_bytes(header + entries + blobs)


# ICNS girdi turleri: PNG verisi tasiyan turler (macOS 10.7+)
ICNS_TYPES = ((b"ic11", 32), (b"ic12", 64), (b"ic07", 128), (b"ic08", 256), (b"ic13", 512),
              (b"ic09", 512), (b"ic14", 1024), (b"ic10", 1024))


def write_icns(path: Path, style: str) -> None:
    from networkplus.ui.app_icon import icon_pixmap
    cache: dict[int, bytes] = {}
    body = b""
    for kind, size in ICNS_TYPES:
        blob = cache.setdefault(size, png_bytes(icon_pixmap(size, style=style)))
        body += kind + struct.pack(">I", 8 + len(blob)) + blob
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def comparison_sheet(path: Path, styles: list[str]) -> None:
    """Her bicem: gercek tepsi/gorev cubugu boyutlari, koyu + acik zemin, uc durum rengi."""
    from networkplus.ui.app_icon import paint_app_icon
    from networkplus.ui.theme import AMBER, GRAY, GREEN
    row_h, w = 120, 900
    img = QImage(w, row_h * len(styles) * 2 + 10, QImage.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    f = QFont("Segoe UI", 11)
    f.setBold(True)
    for i, style in enumerate(styles):
        for j, bg in enumerate(("#202020", "#f3f3f3")):
            y0 = (i * 2 + j) * row_h + 5
            p.fillRect(0, y0, w, row_h - 4, QColor(bg))
            p.setPen(QColor("white" if j == 0 else "black"))
            p.setFont(f)
            p.drawText(10, y0 + 22, f"{chr(65 + i)}  {style}")
            x, base = 10, y0 + row_h - 16
            for size in (16, 20, 24, 32, 48, 64):
                p.save()
                p.translate(x, base - size)
                paint_app_icon(p, size, style=style)
                p.restore()
                x += size + 16
            x += 20
            for st in (GREEN, AMBER, GRAY):
                for size in (16, 24, 32):
                    p.save()
                    p.translate(x, base - size)
                    paint_app_icon(p, size, st, style=style)
                    p.restore()
                    x += size + 10
                x += 18
    p.end()
    img.save(str(path))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="tum bicemleri yaz (secenekler)")
    ap.add_argument("--style", help="tek bicem (varsayilan: app_icon.DEFAULT_STYLE)")
    ap.add_argument("--out", default=str(ROOT / "src" / "networkplus" / "resources"))
    args = ap.parse_args()
    app = QApplication.instance() or QApplication([])          # noqa: F841 - QPixmap icin gerekli
    from networkplus.ui.app_icon import DEFAULT_STYLE, STYLES, icon_pixmap
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    styles = list(STYLES) if args.all else [args.style or DEFAULT_STYLE]
    for i, style in enumerate(styles):
        name = f"{chr(65 + i)}-{style}" if args.all else "networkplus"
        write_ico(out / f"{name}.ico", style)
        if not args.all:
            write_icns(out / f"{name}.icns", style)
        icon_pixmap(256, style=style).save(str(out / f"{name}.png"))
        print(f"{out / name}.ico")
    if args.all:
        comparison_sheet(out / "secenekler.png", styles)
        print(out / "secenekler.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
