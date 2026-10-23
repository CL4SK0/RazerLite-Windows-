"""Détection et pilotage des périphériques Razer via hidapi (sans pilote, sans Synapse)."""

import os
import time
from dataclasses import dataclass, field

from . import protocol as p

RAZER_VID = 0x1532


@dataclass(frozen=True)
class Spec:
    pid: int
    name: str
    kind: str                       # "mouse", "keyboard", "headset"
    interface: int                  # interface USB qui reçoit les commandes
    usage_page: int
    usage: int
    wireless: bool = False
    # Identifiants de transaction essayés dans l'ordre (le premier qui répond "ok" est retenu)
    tids: tuple = (0x1F,)
    # Zones : nom affiché -> identifiant de LED
    zones: dict = field(default_factory=dict)
    # Disposition pour l'image personnalisée : liste de (zone, ligne, colonne, nombre de LED)
    frame: tuple = ()
    effects: tuple = ()
    features: tuple = ()


MOUSE_ZONES = {"Tout": p.ZERO_LED, "Logo": p.LOGO_LED, "Molette": p.SCROLL_WHEEL_LED}
# Basilisk V3 Pro : ligne 0, colonne 0 molette, 1 logo, 2 à 12 bande inférieure (OpenRGB)
MOUSE_FRAME = (("Molette", 0, 0, 1), ("Logo", 0, 1, 1), ("Bande", 0, 2, 11))
MOUSE_EFFECTS = ("static", "spectrum", "wave", "breathing", "zones", "off")
MOUSE_FEATURES = ("dpi", "poll_rate", "battery", "idle_time", "brightness", "scroll", "device_mode")

KBD_ZONES = {"Clavier": p.BACKLIGHT_LED}
KBD_EFFECTS = ("static", "spectrum", "wave", "breathing", "reactive", "starlight", "off")

SPECS = [
    Spec(0x00AA, "Basilisk V3 Pro (filaire)", "mouse", 0, 0x01, 0x02, False, (0x1F, 0x3F, 0xFF),
         MOUSE_ZONES, MOUSE_FRAME, MOUSE_EFFECTS, MOUSE_FEATURES),
    Spec(0x00AB, "Basilisk V3 Pro (sans fil)", "mouse", 0, 0x01, 0x02, True, (0x1F, 0x3F, 0xFF),
         MOUSE_ZONES, MOUSE_FRAME, MOUSE_EFFECTS, MOUSE_FEATURES),
    Spec(0x0292, "DeathStalker V2 Pro (filaire)", "keyboard", 3, 0x0C, 0x01, False, (0x3F, 0x9F, 0x1F),
         KBD_ZONES, (), KBD_EFFECTS, ("battery", "brightness", "device_mode")),
    Spec(0x0290, "DeathStalker V2 Pro (sans fil)", "keyboard", 2, 0x01, 0x02, True, (0x9F, 0x3F, 0x1F),
         KBD_ZONES, (), KBD_EFFECTS, ("battery", "brightness", "device_mode")),
    Spec(0x0533, "Kraken V3 HyperSense", "headset", 3, 0x0C, 0x01, False, (),
         {"Casque": 0}, (), ("static", "wave", "breathing", "off"), ("brightness",)),
]
SPECS_BY_PID = {s.pid: s for s in SPECS}


class RazerError(Exception):
    pass


def backend():
    """winhid (ctypes, intégré) sous Windows, sinon le module pip « hidapi »."""
    if os.name == "nt":
        from . import winhid
        return winhid
    try:
        import hid
    except ImportError as exc:
        raise RazerError("Module hidapi absent : « pip install hidapi ».") from exc
    return hid


def _matches(spec: Spec, info: dict) -> bool:
    # Sous Windows, chaque collection HID a sa propre entrée : on filtre sur la page d'usage.
    # Sous Linux/macOS usage_page vaut souvent 0, on se rabat alors sur l'interface.
    interface = info.get("interface_number", -1)
    if interface not in (-1, spec.interface):
        return False
    if info.get("usage_page"):
        return info["usage_page"] == spec.usage_page and info.get("usage") == spec.usage
    return interface == spec.interface


def enumerate_raw():
    """Toutes les interfaces HID Razer, pour le diagnostic."""
    return list(backend().enumerate(RAZER_VID, 0))


def find_devices():
    """Renvoie les appareils connus, un par modèle, filaire préféré au sans-fil."""
    found = {}
    for info in enumerate_raw():
        spec = SPECS_BY_PID.get(info["product_id"])
        if spec and _matches(spec, info) and spec.pid not in found:
            found[spec.pid] = info
    devices = []
    for kind in ("mouse", "keyboard", "headset"):
        candidates = [s for s in SPECS if s.kind == kind and s.pid in found]
        candidates.sort(key=lambda s: s.wireless)
        if candidates:
            spec = candidates[0]
            cls = KrakenV3 if kind == "headset" else ChromaDevice
            devices.append(cls(spec, found[spec.pid]["path"]))
    return devices


def open_transport(path):
    hid = backend()
    if hasattr(hid, "Transport"):
        return hid.Transport(path)
    return HidTransport(path)


class HidTransport:
    def __init__(self, path):
        self.dev = backend().device()
        self.dev.open_path(path)

    def send_feature(self, data: bytes):
        written = self.dev.send_feature_report(list(data))
        if written is not None and written < 0:
            raise OSError("send_feature_report a échoué")
        return written

    def get_feature(self, length: int) -> bytes:
        return bytes(self.dev.get_feature_report(0, length))

    def write(self, data: bytes):
        return self.dev.write(list(data))

    def close(self):
        self.dev.close()


class Device:
    def __init__(self, spec: Spec, path=None, transport=None):
        self.spec = spec
        self.path = path
        self._transport = transport

    @property
    def transport(self):
        if self._transport is None:
            try:
                self._transport = open_transport(self.path)
            except OSError as exc:
                raise RazerError(f"Impossible d'ouvrir {self.spec.name} ({exc}). "
                                 "Synapse est peut-être encore lancé.") from exc
        return self._transport

    @property
    def name(self):
        return self.spec.name

    @property
    def kind(self):
        return self.spec.kind

    def close(self):
        if self._transport is not None:
            self._transport.close()
            self._transport = None


class ChromaDevice(Device):
    """Souris et claviers : paquets de 90 octets en feature report."""

    def __init__(self, spec, path=None, transport=None):
        super().__init__(spec, path, transport)
        self._tid = None
        self.log = []

    def transact(self, command, retries=8):
        try:
            return self._transact(command, retries)
        except (OSError, ValueError) as exc:
            self.close()
            raise RazerError(f"{self.name} : erreur USB ({exc}). Débranché ou utilisé par Synapse ?") from exc

    def _transact(self, command, retries):
        cls_, cmd, size, args = command
        tids = [self._tid] if self._tid is not None else list(self.spec.tids)
        last = None
        for tid in tids:
            request = p.build_report(tid, cls_, cmd, size, args)
            # Report ID 0 en tête, exigé par hidapi
            self.transport.send_feature(b"\x00" + request)
            for _ in range(retries):
                time.sleep(0.004 if not self.spec.wireless else 0.012)
                raw = self.transport.get_feature(p.REPORT_LEN + 1)
                last = p.Response(raw[1:] if len(raw) > p.REPORT_LEN else raw)
                if last.status != p.STATUS_BUSY:
                    break
            self.log.append((request.hex(), last.raw.hex()))
            del self.log[:-50]
            if last.status == p.STATUS_OK and last.matches(request):
                self._tid = tid
                return last
            if last.status == p.STATUS_UNSUPPORTED:
                break
        status = last.status_name if last else "aucune réponse"
        raise RazerError(f"{self.name} : commande {cls_:02x}:{cmd:02x} refusée ({status}).")

    # --- infos ---
    def firmware(self):
        r = self.transact(p.get_firmware())
        return f"v{r.args[0]}.{r.args[1]}"

    def serial(self):
        r = self.transact(p.get_serial())
        return bytes(b for b in r.args[:22] if 32 <= b < 127).decode().strip()

    def battery(self):
        """(pourcentage, en charge) ou None pour un appareil filaire sans batterie."""
        if "battery" not in self.spec.features:
            return None
        level = self.transact(p.get_battery()).args[1]
        charging = bool(self.transact(p.get_charging()).args[1])
        return round(level * 100 / 255), charging

    # --- éclairage ---
    def zone_led(self, zone):
        try:
            return self.spec.zones[zone]
        except KeyError:
            raise RazerError(f"Zone inconnue « {zone} » pour {self.name}") from None

    def set_effect(self, effect, zone=None, color1="#00ff00", color2=None, speed=2, direction=1):
        led = self.zone_led(zone or next(iter(self.spec.zones)))
        if effect == "static":
            cmd = p.effect_static(led, color1)
        elif effect == "spectrum":
            cmd = p.effect_spectrum(led)
        elif effect == "wave":
            cmd = p.effect_wave(led, direction)
        elif effect == "breathing":
            cmd = p.effect_breathing(led, color1, color2)
        elif effect == "reactive":
            cmd = p.effect_reactive(led, color1, speed)
        elif effect == "starlight":
            cmd = p.effect_starlight(led, speed, color1, color2)
        elif effect == "off":
            cmd = p.effect_none(led)
        else:
            raise RazerError(f"Effet « {effect} » non géré par {self.name}")
        self.transact(cmd)

    def set_zone_colors(self, colors: dict):
        """Une couleur par zone (souris) via l'image personnalisée. Non mémorisé par l'appareil."""
        if not self.spec.frame:
            raise RazerError(f"{self.name} : couleurs par zone non gérées")
        rows = {}
        for zone, row, col, count in self.spec.frame:
            rows.setdefault(row, {})
            for i in range(count):
                rows[row][col + i] = colors.get(zone, "#000000")
        for row, cols in rows.items():
            start = min(cols)
            self.transact(p.set_custom_frame(row, start, [cols[c] for c in sorted(cols)]))
        self.transact(p.effect_custom_frame())

    def set_brightness(self, percent, zone=None):
        led = self.zone_led(zone or next(iter(self.spec.zones)))
        self.transact(p.set_brightness(led, round(max(0, min(100, percent)) * 255 / 100)))

    def brightness(self, zone=None):
        led = self.zone_led(zone or next(iter(self.spec.zones)))
        return round(self.transact(p.get_brightness(led)).args[2] * 100 / 255)

    # --- souris ---
    def _need(self, feature):
        if feature not in self.spec.features:
            raise RazerError(f"{self.name} : « {feature} » non disponible")

    def dpi(self):
        self._need("dpi")
        a = self.transact(p.get_dpi()).args
        return int.from_bytes(a[1:3], "big"), int.from_bytes(a[3:5], "big")

    def set_dpi(self, x, y=None):
        self._need("dpi")
        self.transact(p.set_dpi(x, y))

    def dpi_stages(self):
        self._need("dpi")
        return p.parse_dpi_stages(self.transact(p.get_dpi_stages()).args)

    def set_dpi_stages(self, stages, active):
        self._need("dpi")
        self.transact(p.set_dpi_stages(stages, active))

    def poll_rate(self):
        self._need("poll_rate")
        return p.POLL_RATES_REV.get(self.transact(p.get_poll_rate()).args[0])

    def set_poll_rate(self, hz):
        self._need("poll_rate")
        self.transact(p.set_poll_rate(hz))

    def device_mode(self):
        self._need("device_mode")
        return self.transact(p.get_device_mode()).args[0]

    def set_normal_mode(self):
        """Rend la main au firmware (boutons DPI, touches) si Synapse a laissé le mode pilote."""
        self._need("device_mode")
        if self.device_mode() != p.DEVICE_MODE_NORMAL:
            self.transact(p.set_device_mode(p.DEVICE_MODE_NORMAL))
            return True
        return False

    def scroll_settings(self):
        self._need("scroll")
        return {
            "scroll_mode": "free" if self.transact(p.get_scroll_mode()).args[1] else "tactile",
            "scroll_accel": bool(self.transact(p.get_scroll_acceleration()).args[1]),
            "smart_reel": bool(self.transact(p.get_smart_reel()).args[1]),
        }

    def set_scroll_mode(self, mode):
        self._need("scroll")
        self.transact(p.set_scroll_mode(p.SCROLL_FREESPIN if mode == "free" else p.SCROLL_TACTILE))

    def set_scroll_acceleration(self, enabled):
        self._need("scroll")
        self.transact(p.set_scroll_acceleration(enabled))

    def set_smart_reel(self, enabled):
        self._need("scroll")
        self.transact(p.set_smart_reel(enabled))

    def idle_time(self):
        self._need("idle_time")
        return int.from_bytes(self.transact(p.get_idle_time()).args[0:2], "big")

    def set_idle_time(self, seconds):
        self._need("idle_time")
        self.transact(p.set_idle_time(seconds))


class KrakenV3(Device):
    """Kraken V3 HyperSense : petits output reports 0x40, sans réponse."""

    def _send(self, data):
        try:
            written = self.transport.write(data)
        except (OSError, ValueError) as exc:
            self.close()
            raise RazerError(f"{self.name} : erreur USB ({exc})") from exc
        if written < 0:
            raise RazerError(f"{self.name} : écriture refusée")
        time.sleep(0.005)

    def firmware(self):
        return "?"

    def battery(self):
        return None

    def set_effect(self, effect, zone=None, color1="#00ff00", color2=None, speed=2, direction=1):
        if effect == "static":
            self._send(p.kraken_mode_direct())
            self._send(p.kraken_set_color(color1))
        elif effect == "off":
            self._send(p.kraken_mode_direct())
            self._send(p.kraken_set_color("#000000"))
        elif effect == "wave":
            self._send(p.kraken_mode_wave())
        elif effect == "breathing":
            self._send(p.kraken_mode_breathing([c for c in (color1, color2) if c]))
        else:
            raise RazerError(f"Effet « {effect} » non géré par {self.name}")

    def set_brightness(self, percent, zone=None):
        self._send(p.kraken_set_brightness(round(max(0, min(100, percent)) * 255 / 100)))
