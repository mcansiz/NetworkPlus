#!/usr/bin/env bash
# networkPlus — macOS .app paketi (PyInstaller, ortak spec: packaging/networkplus.spec). DENEYSEL:
# macOS'ta canli ag kesfi yok, uygulama kayitli anlik goruntuleri gosterir (ADR 0013).
#
#   ./build_macos.sh
#   SKIP_TESTS=1 ./build_macos.sh
#
# Cikti: dist/networkPlus-<surum>-macos-<mimari>.zip (icinde networkPlus.app; imzasiz)
# Derleme ortami proje icinde (.venv-build-macos); sistem Python'una paket KURULMAZ.
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Bu betik macOS'ta calisir; Windows icin ./build_win.sh, Linux icin ./build_appimage.sh" >&2; exit 1
fi

PYTHON="${PYTHON:-python3}"
VENV=".venv-build-macos"
VPY="$VENV/bin/python"

if [ ! -x "$VPY" ]; then
  echo ">> Derleme ortami olusturuluyor: $VENV"
  "$PYTHON" -m venv "$VENV"
fi
echo ">> Bagimliliklar (PyQt5 + PyInstaller)"
"$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-build.txt

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo ">> Testler"
  QT_QPA_PLATFORM=offscreen "$VPY" -m unittest discover -s tests
fi
echo ">> Ceviri denetimi"
"$VPY" tools/i18n_update.py --check
echo ">> Uygulama simgesi (.icns)"
"$VPY" tools/make_app_icon.py

echo ">> PyInstaller"
rm -rf dist/networkPlus.app dist/networkPlus
"$VPY" -m PyInstaller --noconfirm --clean --distpath dist --workpath .tmp/build/macos packaging/networkplus.spec

VER="$(PYTHONPATH=src "$VPY" -c 'from networkplus import __version__; print(__version__)')"
ARCH="$(uname -m)"; [ "$ARCH" = "x86_64" ] && ARCH=x64
ZIP="dist/networkPlus-$VER-macos-$ARCH.zip"
echo ">> Paketli program sinamasi"
"$VPY" tools/smoke_frozen.py dist/networkPlus.app/Contents/MacOS/networkPlus
rm -f "$ZIP"
ditto -c -k --keepParent dist/networkPlus.app "$ZIP"
echo ">> Hazir: $ZIP"
