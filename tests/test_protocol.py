"""Tests sans matériel : on compare les paquets aux traces publiées par OpenRazer et OpenRGB."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["APPDATA"] = tempfile.mkdtemp()

from razerlite import devices as dv, profiles, protocol as p


def payload(cmd, tid=0x3F):
    """Représentation 'Status Trans Packet Proto DataSize Class CMD Args' des commentaires OpenRazer."""
    r = p.build_report(tid, *cmd)
    return r[:8].hex() + r[8:8 + r[5]].hex()


class FakeTransport:
    """Simule un appareil : répond OK seulement à l'identifiant de transaction attendu."""

    def __init__(self, good_tid=0x1F, answers=None):
        self.good_tid, self.answers, self.sent, self.writes = good_tid, answers or {}, [], []

    def send_feature(self, data):
        assert len(data) == 91 and data[0] == 0
        self.sent.append(bytes(data[1:]))

    def get_feature(self, length):
        req = bytearray(self.sent[-1])
        if req[1] == self.good_tid:
            req[0] = p.STATUS_OK
            extra = self.answers.get((req[6], req[7]))
            if extra:
                req[8:8 + len(extra)] = extra
        else:
            req[0] = p.STATUS_NEW
        return b"\x00" + bytes(req)

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def close(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_crc_and_length(self):
        r = p.build_report(0x1F, 0x0F, 0x02, 0x06, b"\x01\x05\x03")
        self.assertEqual(len(r), 90)
        x = 0
        for b in r[2:88]:
            x ^= b
        self.assertEqual(r[88], x)

    def test_openrazer_traces(self):
        # Traces copiées des commentaires de razerchromacommon.c
        self.assertEqual(payload(p.effect_static(p.BACKLIGHT_LED, "#ff0000")), "003f000000090f02010501000001ff0000")
        self.assertEqual(payload(p.effect_none(p.BACKLIGHT_LED)), "003f000000060f02010500000000")
        self.assertEqual(payload(p.effect_wave(p.BACKLIGHT_LED, 1)), "003f000000060f02010504012800")
        self.assertEqual(payload(p.effect_breathing(p.BACKLIGHT_LED, "#00ff00")), "003f000000090f0201050201000100ff00")
        self.assertEqual(payload(p.effect_breathing(p.BACKLIGHT_LED, "#00ff00", "#ff0000")),
                         "003f0000000c0f0201050202000200ff00ff0000")
        self.assertEqual(payload(p.effect_breathing(p.BACKLIGHT_LED)), "003f000000060f02010502000000")
        self.assertEqual(payload(p.effect_reactive(p.BACKLIGHT_LED, "#ff0000", 3)), "003f000000090f02010505000301ff0000")
        self.assertEqual(payload(p.effect_starlight(p.BACKLIGHT_LED, 3, "#ff0000", "#00ff00")),
                         "003f0000000c0f02010507000302ff000000ff00")
        self.assertEqual(payload(p.set_brightness(p.BACKLIGHT_LED, 0xB7)), "003f000000030f040105b7")
        self.assertEqual(payload(p.effect_custom_frame()), "003f0000000c0f02000008000000000000000000")

    def test_scroll_and_mode_traces(self):
        self.assertEqual(payload(p.set_scroll_mode(p.SCROLL_FREESPIN), 0x1F), "001f00000002021401" + "01")
        self.assertEqual(payload(p.set_scroll_acceleration(True), 0x1F), "001f0000000202160101")
        self.assertEqual(payload(p.set_smart_reel(False), 0x1F), "001f0000000202170100")
        self.assertEqual(payload(p.set_device_mode(), 0x1F), "001f0000000200040000")

    def test_dpi(self):
        cls, cmd, size, args = p.set_dpi(1600)
        self.assertEqual((cls, cmd, size), (0x04, 0x05, 0x07))
        self.assertEqual(args.hex(), "0106400640" + "0000")
        cls, cmd, size, args = p.set_dpi_stages([800, 1600, 3200], 2)
        self.assertEqual(args[:3], bytes((1, 2, 3)))
        stages, active = p.parse_dpi_stages(args)
        self.assertEqual((stages, active), ([(800, 800), (1600, 1600), (3200, 3200)], 2))
        with self.assertRaises(ValueError):
            p.set_dpi_stages([800] * 6, 1)

    def test_kraken_traces(self):
        # Traces copiées des commentaires de RazerKrakenV3Controller.cpp (OpenRGB)
        self.assertTrue(p.kraken_mode_direct().hex().startswith("4001000f08"))
        self.assertTrue(p.kraken_set_color("#ffffff").hex().startswith("400300ffffff"))
        self.assertTrue(p.kraken_set_brightness(255).hex().startswith("40020000ff"))
        self.assertTrue(p.kraken_mode_breathing(["#ff0000"]).hex().startswith("400101000101ff0000"))
        self.assertTrue(p.kraken_mode_breathing(["#ff0000", "#00ff00"]).hex().startswith("400101000202ff000000ff00"))
        self.assertEqual(len(p.kraken_mode_wave()), 15)


class DeviceTests(unittest.TestCase):
    def mouse(self, **kw):
        t = FakeTransport(**kw)
        return dv.ChromaDevice(dv.SPECS_BY_PID[0x00AB], transport=t), t

    def test_transaction_id_fallback(self):
        kbd = dv.ChromaDevice(dv.SPECS_BY_PID[0x0290], transport=FakeTransport(good_tid=0x3F))
        kbd.set_effect("static", color1="#123456")
        self.assertEqual(kbd._tid, 0x3F)
        self.assertEqual([r[1] for r in kbd.transport.sent], [0x9F, 0x3F])
        kbd.set_brightness(50)
        self.assertEqual(kbd.transport.sent[-1][1], 0x3F)

    def test_refused(self):
        m, _ = self.mouse(good_tid=0x42)
        with self.assertRaises(dv.RazerError):
            m.set_dpi(800)

    def test_battery_and_reads(self):
        m, _ = self.mouse(answers={(0x07, 0x80): b"\x00\x80", (0x07, 0x84): b"\x00\x01",
                                   (0x00, 0x85): b"\x01", (0x04, 0x85): b"\x00\x03\x20\x03\x20"})
        self.assertEqual(m.battery(), (50, True))
        self.assertEqual(m.poll_rate(), 1000)
        self.assertEqual(m.dpi(), (800, 800))

    def test_zone_colors(self):
        m, t = self.mouse()
        m.set_zone_colors({"Molette": "#ff0000", "Logo": "#00ff00", "Bande": "#0000ff"})
        frame, activate = t.sent[-2], t.sent[-1]
        self.assertEqual(frame[6:8], b"\x0f\x03")
        self.assertEqual(frame[8:13], bytes((0, 0, 0, 0, 12)))
        self.assertEqual(frame[13:19].hex(), "ff000000ff00")
        self.assertEqual(frame[19:22].hex(), "0000ff")
        self.assertEqual(frame[13 + 12 * 3:13 + 13 * 3].hex(), "0000ff")
        self.assertEqual(activate[6:11], bytes((0x0F, 0x02, 0, 0, 0x08)))

    def test_kraken(self):
        t = FakeTransport()
        k = dv.KrakenV3(dv.SPECS_BY_PID[0x0533], transport=t)
        k.set_effect("static", color1="#ff8800")
        self.assertEqual([w[:6].hex() for w in t.writes], ["4001000f0800", "400300ff8800"])

    def test_kraken_sidetone(self):
        # octets relevés dans la capture USB de Synapse (retour micro coupé à 100 %, activé à 0, 50, 100 %)
        self.assertEqual(p.kraken_sidetone(False, 100).hex(), "7001010064")
        self.assertEqual(p.kraken_sidetone(True, 0).hex(), "7001010100")
        self.assertEqual(p.kraken_sidetone(True, 50).hex(), "7001010132")
        self.assertEqual(p.kraken_sidetone(True, 100).hex(), "7001010164")
        t = FakeTransport()
        k = dv.KrakenV3(dv.SPECS_BY_PID[0x0533], path=b"kraken", transport=t)
        with mock.patch.object(dv, "enumerate_raw", return_value=[]):
            k.set_sidetone(True, 50)
        self.assertEqual(t.writes, [bytes.fromhex("7001010132")])
        settings = {"audio": {"sidetone": {"on": True, "level": 100}}}
        with mock.patch.object(dv, "enumerate_raw", return_value=[]):
            self.assertEqual(profiles.apply_device(k, settings), [])
        self.assertEqual(t.writes[-1], bytes.fromhex("7001010164"))

    def test_profile_apply(self):
        m, t = self.mouse()
        k = dv.KrakenV3(dv.SPECS_BY_PID[0x0533], transport=FakeTransport())
        errors = profiles.apply_profile([m, k], profiles.active_profile(profiles.load()))
        self.assertEqual(errors, [])
        cmds = [(r[6], r[7]) for r in t.sent]
        for expected in [(0x0F, 0x02), (0x0F, 0x04), (0x04, 0x06), (0x04, 0x05), (0x00, 0x05), (0x07, 0x03)]:
            self.assertIn(expected, cmds)

    def test_normal_mode_only_when_needed(self):
        m, t = self.mouse(answers={(0x00, 0x84): b"\x03\x00"})
        self.assertTrue(m.set_normal_mode())
        self.assertEqual(t.sent[-1][6:10].hex(), "00040000")
        m2, t2 = self.mouse(answers={(0x00, 0x84): b"\x00\x00"})
        self.assertFalse(m2.set_normal_mode())
        self.assertEqual(len(t2.sent), 1)

    def test_keyboard_codes_match_layout(self):
        from razerlite import render
        for row, codes in zip(render.KEY_ROWS, render.KEY_CODES):
            self.assertEqual(len([k for k, _ in row if k is not None]), len(codes))

    def test_profiles_roundtrip(self):
        cfg = profiles.load()
        cfg["active"] = "Nuit"
        profiles.save(cfg)
        self.assertEqual(profiles.load()["active"], "Nuit")
        self.assertEqual(profiles.active_profile(profiles.load())["mouse"]["brightness"], 20)


if __name__ == "__main__":
    unittest.main()
