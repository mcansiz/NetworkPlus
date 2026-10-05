# -*- mode: python ; coding: utf-8 -*-
"""networkPlus — ORTAK PyInstaller spec (Windows + Linux + macOS).

Dogrudan degil, build_win.sh / build_linux.sh / build_macos.sh ile calistirilir:
    python -m PyInstaller --noconfirm --clean packaging/networkplus.spec

Cikti: dist/networkPlus-<surum>-<windows|linux>-<mimari>[.exe] (TEK DOSYA)
       dist/networkPlus.app (macOS, deneysel — ADR 0013; build_macos.sh zip'ler)

Notlar (ADR 0012):
- Veri dosyalari (.ui, .ts, .qss, .ps1, simge) KAYNAK AGACINDAKI yerleriyle eklenir; kod
  onlari `Path(__file__)` ile buldugu icin paketli halde de ayni yol calisir.
- .ui dosyalarindaki promote edilmis moduller (`networkplus.ui.modules...`) uic tarafindan
  calisma aninda ice aktarilir -> tum paket alt modulleri hiddenimports'a eklenir.
- Yardimci surecler (DHCP sunucusu, Linux uygulayici) ayni exe ile, gizli bayrakla calisir
  (platform/selfexec.py); ayri Python gerekmez.
- UPX kapali: virus tarayicilarinda yanlis alarm ve acilis gecikmesi yapiyor.
"""

import platform
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent          # noqa: F821 - PyInstaller tanimlar
SRC = ROOT / "src"
PKG = SRC / "networkplus"
sys.path.insert(0, str(SRC))
from networkplus import __version__             # noqa: E402

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
OS_NAME = "windows" if IS_WIN else "macos" if IS_MAC else "linux"
ARCH = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
    platform.machine().lower(), platform.machine().lower())
NAME = f"networkPlus-{__version__}-{OS_NAME}-{ARCH}"

# ---- veri dosyalari (kaynak agacindaki goreli yerleriyle)
DATA_PATTERNS = ("*.ui", "*.ts", "*.qss", "*.ps1", "*.png", "*.ico")
datas = []
for pattern in DATA_PATTERNS:
    for f in sorted(PKG.rglob(pattern)):
        if "__pycache__" not in f.parts:
            datas.append((str(f), str(f.parent.relative_to(SRC))))

# ---- moduller: diger isletim sisteminin platform katmani pakete girmez
OTHER_OS = ".platform.linux" if IS_WIN else ".platform.windows"
hiddenimports = [m for m in collect_submodules("networkplus") if OTHER_OS not in m]

# Kullanilmayan buyuk Qt modulleri ve stdlib parcalari (boyut)
excludes = [
    "tkinter", "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebKit", "PyQt5.QtWebKitWidgets", "PyQt5.QtQml", "PyQt5.QtQuick",
    "PyQt5.QtQuickWidgets", "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtBluetooth", "PyQt5.QtLocation", "PyQt5.QtPositioning", "PyQt5.QtSql",
    "PyQt5.QtTest", "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtOpenGL", "PyQt5.QtSensors",
    "PyQt5.QtSerialPort", "PyQt5.QtWebSockets", "PyQt5.QtXmlPatterns", "PyQt5.QtNfc",
    "PyQt5.QtWebChannel", "PyQt5.QtTextToSpeech", "PyQt5.QtRemoteObjects", "PyQt5.Qt3DCore",
    "PyQt5.QtCharts", "PyQt5.QtDataVisualization",
]

a = Analysis(                                   # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)                               # noqa: F821

# ---- Windows: exe simgesi + dosya ozellikleri (surum bilgisi); macOS: .icns
icon = (str(PKG / "resources" / "networkplus.ico") if IS_WIN
        else str(PKG / "resources" / "networkplus.icns") if IS_MAC else None)
version = None
if IS_WIN:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )
    nums = tuple(int(x) for x in (__version__.split(".") + ["0", "0", "0"])[:4])
    version = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[
            StringFileInfo([StringTable("041F04B0", [           # Turkce, Unicode
                StringStruct("ProductName", "networkPlus"),
                StringStruct("FileDescription", "networkPlus — ağ bağdaştırıcısı diyagramı"),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductVersion", __version__),
                StringStruct("OriginalFilename", f"{NAME}.exe"),
                StringStruct("LegalCopyright", "GNU GPL v3"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x041F, 1200])]),
        ],
    )

if IS_MAC:
    # macOS kullanicisi cift tiklanan .app bekler; PyInstaller tek dosya + .app birlesimini
    # onermez (her acilista /tmp'ye acar) -> klasor cikti (COLLECT) + BUNDLE. Yardimci roller
    # (--np-dhcp-daemon) .app icindeki ayni ikiliyle calisir (platform/selfexec.py).
    exe = EXE(                                  # noqa: F821
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="networkPlus",
        debug=False,
        strip=False,
        upx=False,
        console=False,
        argv_emulation=False,
        icon=icon,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="networkPlus")  # noqa: F821
    app = BUNDLE(                               # noqa: F821
        coll,
        name="networkPlus.app",
        icon=icon,
        bundle_identifier="io.github.mcansiz.networkplus",
        version=__version__,
        info_plist={
            "CFBundleName": "networkPlus",
            "CFBundleDisplayName": "networkPlus",
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
else:
    exe = EXE(                                      # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=NAME,
        debug=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,              # pencereli uygulama; yardimci surecler yine stdin/stdout borusu kullanir
        icon=icon,
        version=version,
    )
