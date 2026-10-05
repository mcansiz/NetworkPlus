#!/usr/bin/env bash
# networkPlus — Linux AppImage paketi (ADR 0013). Surum dosyasi olarak bunu kullanin; tek dosya
# PyInstaller ciktisi (build_linux.sh) derlendigi makinenin glibc'sine baglidir.
#
#   ./build_appimage.sh          dist/networkPlus-<surum>-x86_64.AppImage uretir
#   ./build_appimage.sh --keep   AppDir'i .tmp/appimage altinda birakir
#
# Butun adimlar tools/appimage.py icindedir. Tasinabilir Python (manylinux2014, glibc 2.17) ve
# appimagetool sabit surumlerle indirilir, SHA-256 denetlenir. Ag baglantisi gerekir.
# Sinama: APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/smoke_frozen.py dist/networkPlus-*.AppImage
set -eu
cd "$(dirname "$(readlink -f "$0")")"
command -v readelf >/dev/null || { echo "HATA: readelf yok (sudo apt install binutils)"; exit 1; }
exec python3 tools/appimage.py "$@"
