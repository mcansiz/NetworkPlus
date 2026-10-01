"""Bir .ts dosyasini kaynak->ceviri sozlugunden (JSON) toplu doldurur.

    python tools/i18n_fill.py en .tmp/work/en_translations.json [--overwrite]

Gelistirici araci: ilk ceviriyi hizli girmek icin. Sonraki duzeltmeler Qt Linguist'te
(C:\\Qt\\5.15.2\\msvc2019_64\\bin\\linguist.exe) ya da bu aracla yapilir.
Varsayilan olarak yalniz BOS (unfinished) ceviriler doldurulur.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n_update as upd                                     # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lang")
    ap.add_argument("json_file")
    ap.add_argument("--overwrite", action="store_true", help="mevcut cevirilerin de uzerine yaz")
    args = ap.parse_args()
    path = upd.I18N / f"{args.lang}.ts"
    mapping = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    language, old = upd.read_ts(path)
    filled = missing = 0
    new = {}
    for key, (text, kind) in old.items():
        ctx, src = key
        want = mapping.get(src)
        if want is not None and (args.overwrite or not text or kind == "unfinished"):
            new[key] = (want, None)
            filled += 1
        else:
            new[key] = (text, kind)
            if not text:
                missing += 1
    stats = upd.write_ts(path, language, upd.collect(), new)
    print(f"{path.name}: {filled} dolduruldu; durum: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
