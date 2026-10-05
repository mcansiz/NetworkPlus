"""Paketleme (ADR 0013): AppImage'da kendini cagirma, calisma klasoru, desteklenmeyen sistem,
macOS simgesi. Hicbir surec baslatilmaz; ortam degiskeni gecici olarak degistirilir."""

from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from networkplus import paths                                      # noqa: E402
from networkplus.platform import CollectError, UnsupportedCollector, get_collector   # noqa: E402
from networkplus.platform import selfexec                           # noqa: E402


class AppImageSelfExec(unittest.TestCase):
    def test_source_tree(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPIMAGE", None)
            self.assertFalse(selfexec.is_packaged())
            self.assertEqual(selfexec.self_command(), [sys.executable, str(ROOT / "main.py")])
            script = Path("/x/helper.py")
            self.assertEqual(selfexec.command_for(script, selfexec.LINUX_HELPER_FLAG)[1], str(script))

    def test_appimage_calls_itself(self):
        """Kok (pkexec) kullanicinin FUSE baglamasina erisemez -> .AppImage dosyasi + bayrak."""
        with mock.patch.dict(os.environ, {"APPIMAGE": "/home/u/networkPlus.AppImage"}):
            self.assertTrue(selfexec.is_packaged())
            self.assertEqual(selfexec.self_command(), ["/home/u/networkPlus.AppImage"])
            self.assertEqual(selfexec.command_for(Path("/mnt/x/helper.py"), selfexec.LINUX_HELPER_FLAG),
                             ["/home/u/networkPlus.AppImage", "--np-linux-helper"])

    def test_dispatch_ignores_normal_args(self):
        self.assertIsNone(selfexec.dispatch(["main.py", "--snapshot", "x.json"]))

    def test_appimage_workdir_is_not_mount(self):
        """AppImage'da kaynak agaci salt okunurdur -> ~/.cache (ya da XDG_CACHE_HOME)."""
        cache = ROOT / ".tmp" / "test" / "xdg-cache"
        env = {"APPIMAGE": "/home/u/networkPlus.AppImage", "XDG_CACHE_HOME": str(cache),
               "LOCALAPPDATA": str(cache)}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("NETWORKPLUS_WORKDIR", None)
            root = paths.work_root()
        self.assertNotEqual(root, ROOT / ".tmp")
        self.assertTrue(str(root).startswith(str(cache)))


class Unsupported(unittest.TestCase):
    def test_collector_opens_but_reports(self):
        with mock.patch.object(sys, "platform", "darwin"):
            collector = get_collector()
        self.assertIsInstance(collector, UnsupportedCollector)
        with self.assertRaises(CollectError):
            collector.collect()

    def test_snapshot_still_works(self):
        with mock.patch.object(sys, "platform", "darwin"):
            collector = get_collector(str(ROOT / "tests" / "fixtures" / "win-host.raw.json"))
        self.assertTrue(collector.collect()["adapters"])


class MacIcon(unittest.TestCase):
    def test_icns_structure(self):
        data = (ROOT / "src" / "networkplus" / "resources" / "networkplus.icns").read_bytes()
        self.assertEqual(data[:4], b"icns")
        self.assertEqual(struct.unpack(">I", data[4:8])[0], len(data))
        pos, kinds = 8, []
        while pos < len(data):
            kind, size = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
            self.assertEqual(data[pos + 8:pos + 16], b"\x89PNG\r\n\x1a\n")
            kinds.append(kind)
            pos += size
        self.assertEqual(pos, len(data))
        self.assertIn(b"ic10", kinds)          # 1024 px (Retina 512@2x)


if __name__ == "__main__":
    unittest.main()
