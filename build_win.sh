#!/usr/bin/env bash
# networkPlus — Windows TEK DOSYA paketi (PyInstaller, ortak spec: packaging/networkplus.spec).
#
#   ./build_win.sh                 # Git Bash'te, proje kokunden ya da herhangi bir yerden
#   SKIP_TESTS=1 ./build_win.sh    # testleri atla
#   PYTHON=py ./build_win.sh       # baska bir Python ile
#
# Cikti: dist/networkPlus-<surum>-windows-x64.exe
# Derleme ortami proje icinde ayri bir sanal ortamdir (.venv-build-win); sistem Python'una
# paket KURULMAZ. Ara dosyalar .tmp/build/windows (Windows TEMP kullanilmaz, ai_rules/10).
set -euo pipefail
cd "$(dirname "$0")"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *) echo "Bu betik Windows'ta (Git Bash) calisir; Linux icin ./build_linux.sh" >&2; exit 1 ;;
esac

PYTHON="${PYTHON:-python}"
VENV=".venv-build-win"
VPY="$VENV/Scripts/python.exe"

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
PYTHONIOENCODING=utf-8 "$VPY" tools/i18n_update.py --check
echo ">> Uygulama simgesi (.ico)"
"$VPY" tools/make_app_icon.py

echo ">> PyInstaller"
"$VPY" -m PyInstaller --noconfirm --clean --distpath dist --workpath .tmp/build/windows packaging/networkplus.spec

EXE="$(ls -t dist/networkPlus-*-windows-*.exe | head -1)"
echo ">> Paketli exe sinamasi: $EXE"
PYTHONIOENCODING=utf-8 "$VPY" tools/smoke_frozen.py "$EXE"
echo ">> Hazir: $EXE"
