#!/usr/bin/env bash
# networkPlus — Linux TEK DOSYA paketi (PyInstaller, ortak spec: packaging/networkplus.spec).
#
#   ./build_linux.sh
#   SKIP_TESTS=1 ./build_linux.sh
#   PYTHON=python3.12 ./build_linux.sh
#
# Cikti: dist/networkPlus-<surum>-linux-x64
# Gerekenler: python3 + venv modulu (Debian/Ubuntu/Mint: sudo apt install python3-venv).
# Derleme ortami proje icinde (.venv-build-linux); sistem Python'una paket KURULMAZ.
# Hedef makinede: NetworkManager (nmcli), pkexec (policykit-1); Qt'nin xcb kitapliklari
# (libxcb-xinerama0, libxkbcommon-x11-0 ...) cogu masaustunde zaten kurulu.
# Not: paket, derlendigi sistemin glibc surumunden ESKI sistemlerde calismaz; en eski hedefte derleyin.
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(uname -s)" != "Linux" ]; then
  echo "Bu betik Linux'ta calisir; Windows icin ./build_win.sh" >&2; exit 1
fi

PYTHON="${PYTHON:-python3}"
VENV=".venv-build-linux"
VPY="$VENV/bin/python"

if [ ! -x "$VPY" ]; then
  echo ">> Derleme ortami olusturuluyor: $VENV"
  if ! "$PYTHON" -m venv "$VENV"; then
    echo "venv olusturulamadi. Debian/Ubuntu/Mint: sudo apt install python3-venv" >&2
    rm -rf "$VENV"; exit 1
  fi
fi
echo ">> Bagimliliklar (PyQt5 + PyInstaller)"
"$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-build.txt

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo ">> Testler"
  QT_QPA_PLATFORM=offscreen "$VPY" -m unittest discover -s tests
fi
echo ">> Ceviri denetimi"
"$VPY" tools/i18n_update.py --check
echo ">> Uygulama simgesi"
"$VPY" tools/make_app_icon.py

echo ">> PyInstaller"
"$VPY" -m PyInstaller --noconfirm --clean --distpath dist --workpath .tmp/build/linux packaging/networkplus.spec

BIN="$(ls -t dist/networkPlus-*-linux-* | head -1)"
chmod +x "$BIN"
echo ">> Paketli program sinamasi: $BIN"
"$VPY" tools/smoke_frozen.py "$BIN"
echo ">> Hazir: $BIN"
