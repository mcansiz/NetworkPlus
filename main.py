"""networkPlus giris noktasi: python main.py [--snapshot DOSYA]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

if __name__ == "__main__":
    # Paketli (PyInstaller) exe yardimci rolunde (DHCP sunucusu, Linux uygulayici) cagrildiysa
    # Qt'ye hic dokunmadan o calisir (platform/selfexec.py).
    from networkplus.platform.selfexec import dispatch
    code = dispatch(sys.argv)
    if code is not None:
        sys.exit(code)
    from networkplus.app import main
    sys.exit(main())
