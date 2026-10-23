import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from razerlite import updater


class UpdaterTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updater.parse_version("v0.5.12"), (0, 5, 12))
        self.assertEqual(updater.parse_version("1.2"), (1, 2, 0))
        self.assertGreater(updater.parse_version("0.5.10"), updater.parse_version("0.5.9"))

    def release(self, tag):
        return json.dumps({"tag_name": tag, "body": "Nouveau truc\nDétails",
                           "assets": [{"name": "RazerLite-pack.zip", "browser_download_url": "https://x/pack.zip"},
                                      {"name": "RazerLite.exe", "browser_download_url": "https://x/app.exe"}]}).encode()

    def test_check(self):
        with mock.patch.object(updater, "repo", return_value="erwan/razerlite"), \
             mock.patch.object(updater, "__version__", "0.5.3"):
            with mock.patch.object(updater, "_get", return_value=self.release("v0.5.3")):
                self.assertIsNone(updater.check())
            with mock.patch.object(updater, "_get", return_value=self.release("v0.5.4")):
                info = updater.check()
                self.assertEqual(info["version"], "0.5.4")
                self.assertEqual(info["url"], "https://x/pack.zip")
                with mock.patch.object(updater, "frozen", return_value=True):
                    self.assertEqual(updater.check()["url"], "https://x/app.exe")

    def test_no_repo(self):
        with mock.patch.object(updater, "repo", return_value=None):
            self.assertIsNone(updater.check())

    def test_extract_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            archive = tmp / "pack.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("razerlite/GUIDE.md", "nouveau")
                z.writestr("razerlite/razerlite/app.py", "x = 1")
                z.writestr("razerlite/../evil.txt", "non")
            root = tmp / "install"
            (root / "razerlite").mkdir(parents=True)
            (root / "GUIDE.md").write_text("ancien")
            updater.extract_pack(archive, root)
            self.assertEqual((root / "GUIDE.md").read_text(), "nouveau")
            self.assertEqual((root / "razerlite" / "app.py").read_text(), "x = 1")
            self.assertFalse((tmp / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
