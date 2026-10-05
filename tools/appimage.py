"""Linux AppImage uretir (GELISTIRME ARACI, ADR 0013). DiskUltimate'teki yontemin aynisi.

    python3 tools/appimage.py            # dist/networkPlus-<surum>-x86_64.AppImage
    python3 tools/appimage.py --keep     # AppDir'i incelemek icin silme

## Neden PyInstaller tek dosyasi degil

PyInstaller ikilisi **derlendigi makinenin glibc surumune** baglidir (ADR 0012): GitHub'in
ubuntu-24.04 makinesinde derlenen paket Mint 21 / Ubuntu 22.04'te calismaz. Bunun yerine
`niess/python-appimage`in manylinux2014 (glibc 2.17) uzerinde derlenmis tasinabilir Python'u ve
PyPI'nin manylinux PyQt5 tekerlekleri kullanilir. Cikan pakette gereken en yuksek glibc surumu
**olculur** ve basilir.

## Adimlar

1. Sabitlenmis Python AppImage'i ve `appimagetool` indirilir (SHA-256 denetlenir) ->
   `.tmp/appimage/tools/`.
2. Python acilir, PyQt5 sabit surumlerle kurulur.
3. Kullanilmayan Qt kutuphaneleri, eklentileri ve Python modulleri silinir; kalan her ELF
   dosyasinin Qt `NEEDED` bagimliliklari pakette bulunmali (yoksa durulur).
4. Uygulama (`main.py`, `src/networkplus` — .ui/.ts/.qss dahil), `AppRun`, `.desktop`, simge.
5. `appimagetool` ile paketlenir.

Yardimci roller (pkexec ile kok uygulayici, DHCP sunucusu) `.AppImage` dosyasinin kendisini
bayrakla cagirir: kok kullanici kullanicinin FUSE baglama noktasina erisemez (platform/selfexec.py).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, ".tmp", "appimage")
TOOLS = os.path.join(WORK, "tools")

# `python3.12` yuvarlanan bir etikettir: yeni yama surumu cikinca eskisi silinir (404).
# Guncelleme: asagidaki komutun verdigi ad ve sha256 buraya yazilir.
#   gh api repos/niess/python-appimage/releases/tags/python3.12 --jq \
#     '.assets[] | select(.name|test("manylinux2014_x86_64")) | .name, .digest'
PYTHON = ("python3.12.15-cp312-cp312-manylinux2014_x86_64.AppImage",
          "https://github.com/niess/python-appimage/releases/download/python3.12/",
          "a6a9bf619a3e21c5623be144d8ac4e458e1a5b5c133b1cc99b142d6e71b82c76")
APPIMAGETOOL = ("appimagetool-x86_64.AppImage",
                "https://github.com/AppImage/appimagetool/releases/download/1.9.1/",
                "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0")
# .github/requirements-ci.txt ile ayni surumler
PIP_PACKAGES = ("PyQt5==5.15.11", "PyQt5-Qt5==5.15.19", "PyQt5-sip==12.19.0")
PY = "python3.12"

# Uygulamanin kullandigi Qt modulleri: QtCore, QtGui, QtWidgets, QtNetwork (tek kopya kilidi).
# Platform eklentileri (xcb, wayland) bunlarin disinda su kutuphaneleri ister.
QT_LIBS_KEEP = {"Core", "Gui", "Widgets", "Network", "DBus", "XcbQpa", "WaylandClient", "Svg"}
QT_PLUGIN_DIRS_KEEP = {
    "platforms", "platforminputcontexts", "platformthemes", "imageformats",
    "iconengines", "xcbglintegrations", "wayland-decoration-client",
    "wayland-graphics-integration-client", "wayland-shell-integration",
}
PLATFORMS_KEEP = ("libqxcb.so", "libqwayland-generic.so", "libqoffscreen.so", "libqminimal.so")
PYQT_KEEP = ("QtCore", "QtGui", "QtWidgets", "QtNetwork", "sip")
STDLIB_DROP = ("test", "idlelib", "tkinter", "turtledemo", "ensurepip",
               "lib2to3", "pydoc_data", "unittest/test")

DESKTOP = """[Desktop Entry]
Type=Application
Name=networkPlus
GenericName=Network Adapter Diagram
GenericName[tr]=Ag Bagdastiricisi Diyagrami
Comment=See network adapters as a diagram and configure them
Comment[tr]=Ag bagdastiricilarini diyagramda gorun ve yapilandirin
Exec=networkPlus %F
Icon=networkplus
Terminal=false
Categories=Network;System;Settings;
Keywords=network;adapter;nmcli;bridge;dhcp;sharing;
"""

APPRUN = r"""#!/bin/sh
# networkPlus AppImage baslaticisi (ADR 0013).
HERE="$(dirname "$(readlink -f "$0")")"
: "${APPDIR:=$HERE}"
export APPDIR

if [ ! -e /lib64/ld-linux-x86-64.so.2 ] && [ ! -e /lib/ld-linux-x86-64.so.2 ] \
   && [ ! -e /lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 ]; then
  echo "networkPlus: this package needs glibc. On musl systems run it from source." >&2
  exit 1
fi

# Kullanicinin kendi Python ortami pakete karismasin.
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP
exec "$APPDIR/opt/python3.12/bin/python3.12" -s -E \
     "$APPDIR/usr/share/networkplus/main.py" "$@"
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(item) -> str:
    name, base, digest = item
    os.makedirs(TOOLS, exist_ok=True)
    path = os.path.join(TOOLS, name)
    if not os.path.isfile(path) or sha256(path) != digest:
        log(f"indiriliyor: {name}")
        try:
            with urllib.request.urlopen(base + name) as r, open(path + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
        except urllib.error.HTTPError as exc:
            raise SystemExit(
                f"HATA: {name} indirilemedi ({exc.code}). Yayinci eski surumu kaldirmis olabilir; "
                f"tools/appimage.py basindaki yorumdaki komutla yeni ad ve sha256 sabitlenir.")
        os.replace(path + ".part", path)
    if sha256(path) != digest:
        raise SystemExit(f"HATA: {name} SHA-256 tutmuyor")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def app_version() -> str:
    text = open(os.path.join(ROOT, "src", "networkplus", "__init__.py"), encoding="utf-8").read()
    return re.search(r'^__version__ = "([^"]+)"', text, re.M).group(1)


def run(cmd, **kw) -> None:
    subprocess.run(cmd, check=True, **kw)


def trim(appdir: str) -> None:
    """Kullanilmayan Qt ve Python parcalarini siler."""
    site = os.path.join(appdir, "opt", PY, "lib", PY, "site-packages")
    pyqt = os.path.join(site, "PyQt5")
    qt = os.path.join(pyqt, "Qt5")
    for name in os.listdir(os.path.join(qt, "lib")):
        m = re.match(r"libQt5(\w+?)\.so", name)
        if m and m.group(1) not in QT_LIBS_KEEP:
            os.remove(os.path.join(qt, "lib", name))
    plugins = os.path.join(qt, "plugins")
    for name in os.listdir(plugins):
        if name not in QT_PLUGIN_DIRS_KEEP:
            shutil.rmtree(os.path.join(plugins, name))
    for name in os.listdir(os.path.join(plugins, "platforms")):
        if name not in PLATFORMS_KEEP:
            os.remove(os.path.join(plugins, "platforms", name))
    shutil.rmtree(os.path.join(qt, "qml"), ignore_errors=True)
    translations = os.path.join(qt, "translations")
    if os.path.isdir(translations):
        # Qt'nin kendi metinleri (dosya diyalogu, Evet/Hayir) icin qtbase_<dil>.qm gerekir
        # (i18n.install_qt_translations); yalniz uygulamanin dilleri tutulur.
        langs = {"tr"} | {n[:-3] for n in os.listdir(os.path.join(ROOT, "src", "networkplus", "i18n"))
                          if n.endswith(".ts")}
        keep = re.compile(r"qtbase_(%s)\.qm$" % "|".join(sorted(langs)))
        for name in os.listdir(translations):
            if not keep.match(name):
                os.remove(os.path.join(translations, name))
    # Silinmis bir Qt kutuphanesine baglanan eklenti de silinir (orn. imageformats/libqpdf.so).
    kept = set(os.listdir(os.path.join(qt, "lib")))
    for dirpath, _, files in os.walk(plugins):
        for name in files:
            full = os.path.join(dirpath, name)
            out = subprocess.run(["readelf", "-dW", full], capture_output=True, text=True).stdout
            needs = re.findall(r"\(NEEDED\)\s+Shared library: \[(libQt5[^\]]+)\]", out)
            gone = [n for n in needs if n not in kept]
            if gone:
                log(f"  eklenti siliniyor: {os.path.relpath(full, qt)} ({', '.join(gone)})")
                os.remove(full)
    for name in os.listdir(pyqt):
        full = os.path.join(pyqt, name)
        mod = name.split(".")[0]
        if (name.endswith(".so") or name.endswith(".pyi")) and mod not in PYQT_KEEP:
            os.remove(full)
    # `uic` KALIR: arayuz .ui dosyalarini calisma aninda yukler (ADR 0006).
    for name in ("bindings", "pyrcc_main.py", "pylupdate_main.py", "pyrcc.abi3.so", "pylupdate.abi3.so"):
        full = os.path.join(pyqt, name)
        if os.path.isdir(full):
            shutil.rmtree(full)
        elif os.path.exists(full):
            os.remove(full)
    for name in os.listdir(site):
        if name.startswith(("pip", "setuptools", "wheel")):
            full = os.path.join(site, name)
            shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
    stdlib = os.path.join(appdir, "opt", PY, "lib", PY)
    for sub in STDLIB_DROP:
        shutil.rmtree(os.path.join(stdlib, sub), ignore_errors=True)
    shutil.rmtree(os.path.join(appdir, "usr", "share", "tcltk"), ignore_errors=True)
    for dirpath, dirnames, _ in os.walk(appdir):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d))
                dirnames.remove(d)


def elf_files(appdir: str):
    for dirpath, _, files in os.walk(appdir):
        for name in files:
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                if f.read(4) == b"\x7fELF":
                    yield path


def check_dependencies(appdir: str) -> str:
    """Her ELF'in Qt/ICU NEEDED listesi pakette var mi; gereken en yuksek glibc."""
    bundled = {os.path.basename(p) for p in elf_files(appdir)}
    for dirpath, _, files in os.walk(appdir):
        bundled.update(f for f in files if ".so" in f)
    missing: dict[str, list[str]] = {}
    glibc = []
    for path in elf_files(appdir):
        out = subprocess.run(["readelf", "-dW", path], capture_output=True, text=True).stdout
        for need in re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out):
            if need.startswith(("libQt5", "libicu")) and need not in bundled:
                missing.setdefault(need, []).append(os.path.relpath(path, appdir))
        sym = subprocess.run(["readelf", "-VW", path], capture_output=True, text=True).stdout
        glibc += [tuple(int(x) for x in v.split("."))
                  for v in re.findall(r"GLIBC_(\d+\.\d+(?:\.\d+)?)", sym)]
    if missing:
        for need, users in missing.items():
            log(f"  EKSIK {need}: {users[:3]}")
        raise SystemExit("HATA: silinen bir Qt kutuphanesine hala ihtiyac var")
    top = max(glibc) if glibc else ()
    return ".".join(str(x) for x in top)


def build(keep: bool = False) -> str:
    version = app_version()
    python_ai = fetch(PYTHON)
    tool = fetch(APPIMAGETOOL)

    appdir = os.path.join(WORK, "networkPlus.AppDir")
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.rmtree(os.path.join(WORK, "squashfs-root"), ignore_errors=True)
    log("Python aciliyor...")
    run([python_ai, "--appimage-extract"], cwd=WORK, stdout=subprocess.DEVNULL)
    os.rename(os.path.join(WORK, "squashfs-root"), appdir)
    for name in os.listdir(appdir):          # Python'un kendi baslaticisi/simgesi
        if name.endswith((".desktop", ".png")) or name in ("AppRun", ".DirIcon"):
            os.remove(os.path.join(appdir, name))
    for sub in ("applications", "icons", "metainfo"):
        shutil.rmtree(os.path.join(appdir, "usr", "share", sub), ignore_errors=True)

    log("PyQt5 kuruluyor: " + " ".join(PIP_PACKAGES))
    py = os.path.join(appdir, "opt", PY, "bin", PY)
    run([py, "-s", "-m", "pip", "install", "--no-cache-dir", "--quiet",
         "--no-warn-script-location", *PIP_PACKAGES])

    log("Kullanilmayan parcalar siliniyor...")
    trim(appdir)

    log("Uygulama kopyalaniyor...")
    share = os.path.join(appdir, "usr", "share", "networkplus")
    os.makedirs(share)
    shutil.copy2(os.path.join(ROOT, "main.py"), share)
    shutil.copy2(os.path.join(ROOT, "LICENSE"), share)
    # Windows katmani (PowerShell betikleri) Linux'ta kullanilmaz; kod onu yalniz win32'de ice aktarir.
    shutil.copytree(os.path.join(ROOT, "src", "networkplus"), os.path.join(share, "src", "networkplus"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.ico", "*.icns"))
    with open(os.path.join(appdir, "AppRun"), "w", newline="\n") as f:
        f.write(APPRUN)
    os.chmod(os.path.join(appdir, "AppRun"), 0o755)
    with open(os.path.join(appdir, "networkplus.desktop"), "w", encoding="utf-8") as f:
        f.write(DESKTOP)
    icon = os.path.join(ROOT, "src", "networkplus", "resources", "networkplus.png")
    shutil.copy2(icon, os.path.join(appdir, "networkplus.png"))
    os.symlink("networkplus.png", os.path.join(appdir, ".DirIcon"))
    hicolor = os.path.join(appdir, "usr", "share", "icons", "hicolor", "256x256", "apps")
    os.makedirs(hicolor)
    shutil.copy2(icon, os.path.join(hicolor, "networkplus.png"))

    log("Bagimliliklar denetleniyor...")
    glibc = check_dependencies(appdir)
    log(f"  gereken en yuksek glibc: {glibc}")

    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", f"networkPlus-{version}-x86_64.AppImage")
    log("Paketleniyor...")
    env = dict(os.environ, ARCH="x86_64", VERSION=version)
    run([tool, "--appimage-extract-and-run", "--no-appstream", appdir, out],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if not keep:
        shutil.rmtree(appdir)
    log(f"Hazir: {out} ({os.path.getsize(out) / 1e6:.1f} MB)")
    log(f"SHA-256: {sha256(out)}")
    return out


if __name__ == "__main__":
    if not sys.platform.startswith("linux"):
        raise SystemExit("AppImage yalniz Linux'ta uretilir")
    build(keep="--keep" in sys.argv)
