import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("APPDATA", tempfile.mkdtemp())

from razerlite import audio  # noqa: E402


class AudioConfigTest(unittest.TestCase):
    def test_build_config(self):
        text = audio.build_config("{out}", "{mic}", audio.HEADSET_PRESETS["Basses+"], audio.MIC_PRESETS["Neutre"],
                                  r"C:\x\rnnoise_mono.dll", True)
        self.assertIn("Device: {out}\nPreamp: -6 dB\nGraphicEQ: 31 6; 62 5;", text)
        self.assertIn('Device: {mic}\nFilter: ON HP Fc 90 Hz\nVSTPlugin: Library "C:\\x\\rnnoise_mono.dll"', text)
        self.assertTrue(text.rstrip().endswith("Device: all"))

    def test_mic_chain_order(self):
        text = audio.build_config(None, "{mic}", None, audio.MIC_PRESETS["Voix forte"], r"C:\x\rnnoise_mono.dll",
                                  True, 6, True)
        mic = text.split("Device: {mic}\n")[1].split("\n\n")[0].splitlines()
        self.assertEqual(mic[0], "Filter: ON HP Fc 90 Hz")
        self.assertTrue(mic[1].startswith("VSTPlugin:"))
        self.assertEqual(mic[-2:], ["Filter: ON LPQ Fc 8000 Hz Q 0.7", "Preamp: 6 dB"])  # volume en dernier

    def test_mic_gain_is_capped(self):
        self.assertIn("Preamp: 12 dB", audio.build_config(None, "{mic}", None, None, None, False, 40))

    def test_default_apo_lines_disabled(self):
        text = audio.disable_default_lines("Preamp: -6 dB\nInclude: example.txt\nInclude: razerlite.txt\n")
        self.assertEqual(text, "# (désactivé par RazerLite) Preamp: -6 dB\n"
                               "# (désactivé par RazerLite) Include: example.txt\nInclude: razerlite.txt\n")

    def test_flat_writes_nothing(self):
        text = audio.build_config("{out}", "{mic}", audio.HEADSET_PRESETS["Neutre"], None, None, False)
        self.assertNotIn("{out}", text)
        self.assertNotIn("{mic}", text)

    def test_write_apo_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "config.txt").write_text("Preamp: -3 dB\n")
            with mock.patch.object(audio, "apo_config_dir", return_value=folder):
                audio.write_apo_config("x\n")
                audio.write_apo_config("y\n")
            self.assertEqual((folder / "razerlite.txt").read_text(), "y\n")
            self.assertEqual((folder / "config.txt").read_text(), "Preamp: -3 dB\nInclude: razerlite.txt\n")

    def test_rnnoise_dll(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("vst3/rnnoise_stereo.dll", "rnnoise_mono.dll", "rnnoise_stereo.dll"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(b"")
            with mock.patch.object(audio, "rnnoise_dir", return_value=root):
                self.assertEqual(audio.rnnoise_dll(1).name, "rnnoise_mono.dll")
                self.assertEqual(audio.rnnoise_dll(2), root / "rnnoise_stereo.dll")


if __name__ == "__main__":
    unittest.main()
