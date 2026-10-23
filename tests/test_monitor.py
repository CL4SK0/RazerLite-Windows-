import array
import unittest

from razerlite import lowlat, monitor


def pcm(*values):
    return array.array("h", values).tobytes()


class MonitorTest(unittest.TestCase):
    def test_gain(self):
        self.assertEqual(monitor.gain_for(50), 1)
        self.assertEqual(monitor.gain_for(100), 2)
        self.assertEqual(monitor.gain_for(-5), 0)

    def test_mono_to_stereo_with_gain_and_clip(self):
        out = monitor.process(pcm(100, -200, 30000), 1, 2, 2)
        self.assertEqual(array.array("h", out).tolist(), [200, 200, -400, -400, 32767, 32767])

    def test_same_channels(self):
        self.assertEqual(monitor.process(pcm(1, 2), 1, 1, 1), pcm(1, 2))

    def test_buffer_keeps_at_most_one_block_ahead(self):
        buf = monitor.Buffer(frame=4)
        for i in range(5):  # le micro prend de l'avance sur le casque
            buf.write(pcm(i, i))
        self.assertEqual(buf.read(4), pcm(3, 3))  # les plus anciens ont été jetés
        self.assertEqual(buf.read(4), pcm(4, 4))
        self.assertEqual(buf.read(4), bytes(4))  # vide : silence

    def test_buffer_drift_does_not_accumulate(self):
        buf = monitor.Buffer(frame=4)
        for _ in range(100):  # le micro livre un peu plus que ce que lit le casque
            buf.write(pcm(1, 1, 1, 1, 1, 1))
            buf.read(8)
        self.assertLessEqual(len(buf.data), 12)

    def test_lowlat_mix_mono_to_stereo(self):
        out = lowlat.mix(array.array("f", [0.25, -0.5]), 1, 2, 2)
        self.assertEqual(out.tolist(), [0.5, 0.5, -1.0, -1.0])

    def test_lowlat_mix_keeps_virtual_surround_channels_silent(self):
        out = lowlat.mix(array.array("f", [0.5, 0.1]), 2, 8, 1)  # micro stéréo, casque 7.1 virtuel
        self.assertEqual(out.tolist(), [0.5, 0.5, 0, 0, 0, 0, 0, 0])

    def test_auto_monitor_falls_back(self):
        m = monitor.AutoMonitor()
        with self.assertRaises(RuntimeError):  # ni WASAPI ni PortAudio ici : erreur claire
            m.start(50)
        self.assertTrue(m.fallback_reason)


if __name__ == "__main__":
    unittest.main()
