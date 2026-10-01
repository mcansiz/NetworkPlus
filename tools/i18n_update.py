"""Ceviri dosyalarini (src/networkplus/i18n/*.ts) guncelle — ADR 0008.

    python tools/i18n_update.py              # tum .ts dosyalarini kaynak koda gore guncelle
    python tools/i18n_update.py --new de     # yeni dil: de.ts olustur (sonra Qt Linguist ile cevir)
    python tools/i18n_update.py --check      # eksik ceviri / bozuk yer tutucu varsa cikis kodu 1

Toplanan metinler:
  - .ui dosyalari: tum <string> (notr="true" olanlar haric); baglam = .ui'nin <class> adi
    (uic bunlari QCoreApplication.translate(<sinif>, metin) ile cevirir).
  - .py dosyalari: tr("...") ve N_("...") cagrilarindaki sabit metinler; baglam 'networkplus'.
Mevcut ceviriler korunur; yeni metinler 'unfinished', kodda artik olmayanlar 'vanished' isaretlenir.
Qt Linguist bu dosyalari dogrudan acar: C:\\Qt\\5.15.2\\msvc2019_64\\bin\\linguist.exe
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "networkplus"
I18N = SRC / "i18n"
PY_CONTEXT = "networkplus"
META = ("@meta", "LANGUAGE_NAME")
_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*(?:![rsa])?(?::[^{}]*)?\}")


def collect() -> dict[str, dict[str, str]]:
    """{baglam: {kaynak: konum}}"""
    out: dict[str, dict[str, str]] = {}
    for ui in sorted(SRC.rglob("*.ui")):
        root = ET.parse(ui).getroot()
        context = (root.findtext("class") or ui.stem).strip()
        for node in root.iter("string"):
            if node.get("notr") == "true" or not (node.text or "").strip():
                continue
            out.setdefault(context, {}).setdefault(node.text, str(ui.relative_to(SRC)))
    for py in sorted(SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name not in ("tr", "N_"):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value:
                out.setdefault(PY_CONTEXT, {}).setdefault(arg.value, f"{py.relative_to(SRC)}:{node.lineno}")
    return out


def read_ts(path: Path) -> tuple[str, dict[tuple[str, str], tuple[str, str | None]]]:
    """(dil, {(baglam, kaynak): (ceviri, type)})"""
    if not path.exists():
        return path.stem, {}
    root = ET.parse(path).getroot()
    table = {}
    for ctx in root.iter("context"):
        name = ctx.findtext("name") or ""
        for msg in ctx.iter("message"):
            node = msg.find("translation")
            table[(name, msg.findtext("source") or "")] = (
                (node.text or "") if node is not None else "", node.get("type") if node is not None else None)
    return root.get("language") or path.stem, table


def write_ts(path: Path, language: str, sources: dict[str, dict[str, str]],
             old: dict[tuple[str, str], tuple[str, str | None]]) -> dict[str, int]:
    stats = {"done": 0, "unfinished": 0, "vanished": 0}
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<!DOCTYPE TS>",
             f'<TS version="2.1" language="{language}" sourcelanguage="tr_TR">']
    contexts = dict(sources)
    contexts.setdefault(META[0], {})[META[1]] = "dil adı (kendi dilinde, ör. English)"
    seen = set()
    for ctx in sorted(contexts):
        lines += ["<context>", f"    <name>{escape(ctx)}</name>"]
        for src in sorted(contexts[ctx]):
            seen.add((ctx, src))
            text, kind = old.get((ctx, src), ("", "unfinished"))
            kind = "unfinished" if not text else (None if kind in ("vanished", "obsolete") else kind)
            stats["unfinished" if kind == "unfinished" else "done"] += 1
            attr = f' type="{kind}"' if kind else ""
            lines += ["    <message>",
                      f"        <location filename=\"{escape(contexts[ctx][src].split(':')[0])}\"/>",
                      f"        <source>{escape(src)}</source>",
                      f"        <translation{attr}>{escape(text)}</translation>",
                      "    </message>"]
        # Koddan kalkmis ama cevirisi olan metinler kaybolmasin: vanished
        for (octx, osrc), (text, _k) in sorted(old.items()):
            if octx == ctx and (octx, osrc) not in seen and text:
                stats["vanished"] += 1
                lines += ["    <message>", f"        <source>{escape(osrc)}</source>",
                          f'        <translation type="vanished">{escape(text)}</translation>', "    </message>"]
        lines.append("</context>")
    lines.append("</TS>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats


def check(path: Path) -> list[str]:
    problems = []
    _lang, table = read_ts(path)
    for (ctx, src), (text, kind) in sorted(table.items()):
        if kind in ("vanished", "obsolete"):
            continue
        if kind == "unfinished" or not text:
            problems.append(f"{path.name}: çevrilmemiş [{ctx}] {src!r}")
            continue
        if sorted(_PLACEHOLDER.findall(src)) != sorted(_PLACEHOLDER.findall(text)):
            problems.append(f"{path.name}: yer tutucu uyuşmuyor [{ctx}] {src!r} -> {text!r}")
    return problems


def _utf8_console():
    # Windows konsolu cp1254: Turkce/ozel karakterde cokmesin.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--new", metavar="KOD", help="yeni dil dosyası oluştur (ör. de, en)")
    ap.add_argument("--check", action="store_true", help="eksik çeviri varsa hata ver")
    args = ap.parse_args()
    I18N.mkdir(parents=True, exist_ok=True)
    if args.check:
        problems = [p for ts in sorted(I18N.glob("*.ts")) for p in check(ts)]
        for p in problems:
            print(p)
        print(f"{len(problems)} sorun" if problems else "TAMAM: tüm diller eksiksiz")
        return 1 if problems else 0
    sources = collect()
    targets = sorted(I18N.glob("*.ts"))
    if args.new:
        targets.append(I18N / f"{args.new}.ts")
    for ts in dict.fromkeys(targets):
        language, old = read_ts(ts)
        stats = write_ts(ts, language, sources, old)
        print(f"{ts.name}: {stats['done']} çevrili, {stats['unfinished']} eksik, {stats['vanished']} kaldırılmış")
    return 0


if __name__ == "__main__":
    _utf8_console()
    sys.exit(main())
