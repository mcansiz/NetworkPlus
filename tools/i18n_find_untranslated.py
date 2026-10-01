"""tr()/N_() ile SARILMAMIS, Turkce karakter iceren metinleri listeler (ADR 0008).

    python tools/i18n_find_untranslated.py [dosya/klasor ...]

Belge dizeleri (docstring), yorumlar ve f-string'in tr() icindeki parcalari atlanir.
Cikti: dosya:satir: metin. Hic bulgu yoksa cikis kodu 0.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TURKISH = set("çğıöşüÇĞİÖŞÜ")
SKIP_FILES = {"i18n_find_untranslated.py"}


def wrapped_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in ("tr", "N_", "translate") and node.args:
                for sub in ast.walk(node.args[0]):
                    ids.add(id(sub))
    return ids


def docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def scan(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text)
    skip = wrapped_ids(tree) | docstring_ids(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            # '# notr' ile isaretli satirlar bilerek cevrilmez (CLI yardimi, dilin kendi adi...).
            if "# notr" in lines[node.lineno - 1]:
                continue
            if TURKISH & set(node.value):
                out.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
    return out


def _utf8_console():
    # Windows konsolu cp1254: Turkce/ozel karakterde cokmesin.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or [ROOT / "src" / "networkplus"]
    files = []
    for t in targets:
        files += [t] if t.is_file() else sorted(t.rglob("*.py"))
    found = [line for f in files if f.name not in SKIP_FILES for line in scan(f.resolve())]
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    _utf8_console()
    sys.exit(main(sys.argv[1:]))
