import array
import unittest

from razerlite import monitor


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

    def test_buffer_never_grows_past_limit(self):
        buf = monitor.Buffer(8, frame=4)
        buf.write(pcm(1, 1, 2, 2))
        buf.write(pcm(3, 3, 4, 4))  # 16 octets : les 8 plus anciens sont jetés
        self.assertEqual(buf.read(8), pcm(3, 3, 4, 4))
        self.assertEqual(buf.read(4), bytes(4))  # vide : silence


if __name__ == "__main__":
    unittest.main()
