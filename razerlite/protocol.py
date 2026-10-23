"""Construction des paquets Razer (protocole repris d'OpenRazer et d'OpenRGB).

Deux familles :
- les paquets "Chroma" de 90 octets, envoyés en feature report (souris, clavier) ;
- les paquets courts 0x40 du Kraken V3, envoyés en output report (casque).

Aucune dépendance ici : tout est testable sans matériel.
"""

REPORT_LEN = 90

# Octet "status" de la réponse
STATUS_NEW = 0x00
STATUS_BUSY = 0x01
STATUS_OK = 0x02
STATUS_FAIL = 0x03
STATUS_TIMEOUT = 0x04
STATUS_UNSUPPORTED = 0x05

STATUS_NAMES = {
    STATUS_NEW: "pas de réponse",
    STATUS_BUSY: "occupé",
    STATUS_OK: "ok",
    STATUS_FAIL: "échec",
    STATUS_TIMEOUT: "délai dépassé",
    STATUS_UNSUPPORTED: "commande non supportée",
}

NOSTORE = 0x00
VARSTORE = 0x01

# Identifiants de LED (razercommon.h)
ZERO_LED = 0x00
SCROLL_WHEEL_LED = 0x01
LOGO_LED = 0x04
BACKLIGHT_LED = 0x05

# Effets "extended matrix" (classe 0x0F, commande 0x02)
EFFECT_NONE = 0x00
EFFECT_STATIC = 0x01
EFFECT_BREATHING = 0x02
EFFECT_SPECTRUM = 0x03
EFFECT_WAVE = 0x04
EFFECT_REACTIVE = 0x05
EFFECT_STARLIGHT = 0x07
EFFECT_CUSTOM = 0x08

POLL_RATES = {1000: 0x01, 500: 0x02, 125: 0x08}
POLL_RATES_REV = {v: k for k, v in POLL_RATES.items()}


def crc(report: bytes) -> int:
    """XOR des octets 2 à 87 (inclus)."""
    value = 0
    for b in report[2:88]:
        value ^= b
    return value


def build_report(transaction_id: int, command_class: int, command_id: int,
                 data_size: int, args=()) -> bytes:
    args = bytes(args)
    if len(args) > 80:
        raise ValueError("80 octets d'arguments maximum")
    buf = bytearray(REPORT_LEN)
    buf[0] = STATUS_NEW
    buf[1] = transaction_id
    # buf[2:4] remaining_packets = 0, buf[4] protocol_type = 0
    buf[5] = data_size
    buf[6] = command_class
    buf[7] = command_id
    buf[8:8 + len(args)] = args
    buf[88] = crc(buf)
    return bytes(buf)


class Response:
    def __init__(self, raw: bytes):
        if len(raw) < REPORT_LEN:
            raw = bytes(raw) + bytes(REPORT_LEN - len(raw))
        self.raw = bytes(raw[:REPORT_LEN])
        self.status = self.raw[0]
        self.transaction_id = self.raw[1]
        self.data_size = self.raw[5]
        self.command_class = self.raw[6]
        self.command_id = self.raw[7]
        self.args = self.raw[8:88]

    def matches(self, request: bytes) -> bool:
        return self.command_class == request[6] and self.command_id == request[7]

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, hex(self.status))


def rgb(color) -> bytes:
    """Accepte '#rrggbb', 'rrggbb' ou un tuple (r, g, b)."""
    if isinstance(color, str):
        c = color.lstrip("#")
        if len(c) != 6:
            raise ValueError(f"couleur invalide : {color!r}")
        return bytes.fromhex(c)
    r, g, b = color
    return bytes((r & 0xFF, g & 0xFF, b & 0xFF))


# --- Commandes "Chroma" : (classe, commande, taille, arguments) ----------------
# Chaque fonction renvoie un tuple ; l'appelant choisit l'identifiant de transaction.

def effect_none(led):
    return 0x0F, 0x02, 0x06, bytes((VARSTORE, led, EFFECT_NONE, 0, 0, 0))


def effect_static(led, color):
    return 0x0F, 0x02, 0x09, bytes((VARSTORE, led, EFFECT_STATIC, 0, 0, 0x01)) + rgb(color)


def effect_spectrum(led):
    return 0x0F, 0x02, 0x06, bytes((VARSTORE, led, EFFECT_SPECTRUM, 0, 0, 0))


def effect_wave(led, direction=1, speed=0x28):
    direction = max(0, min(2, direction))
    return 0x0F, 0x02, 0x06, bytes((VARSTORE, led, EFFECT_WAVE, direction, speed, 0))


def effect_breathing(led, color1=None, color2=None):
    if color1 is None:
        return 0x0F, 0x02, 0x06, bytes((VARSTORE, led, EFFECT_BREATHING, 0, 0, 0))
    if color2 is None:
        return 0x0F, 0x02, 0x09, bytes((VARSTORE, led, EFFECT_BREATHING, 0x01, 0, 0x01)) + rgb(color1)
    return (0x0F, 0x02, 0x0C,
            bytes((VARSTORE, led, EFFECT_BREATHING, 0x02, 0, 0x02)) + rgb(color1) + rgb(color2))


def effect_reactive(led, color, speed=2):
    speed = max(1, min(4, speed))
    return 0x0F, 0x02, 0x09, bytes((VARSTORE, led, EFFECT_REACTIVE, 0, speed, 0x01)) + rgb(color)


def effect_starlight(led, speed=2, color1=None, color2=None):
    speed = max(1, min(3, speed))
    if color1 is None:
        return 0x0F, 0x02, 0x06, bytes((VARSTORE, led, EFFECT_STARLIGHT, 0, speed, 0))
    if color2 is None:
        return 0x0F, 0x02, 0x09, bytes((VARSTORE, led, EFFECT_STARLIGHT, 0, speed, 0x01)) + rgb(color1)
    return (0x0F, 0x02, 0x0C,
            bytes((VARSTORE, led, EFFECT_STARLIGHT, 0, speed, 0x02)) + rgb(color1) + rgb(color2))


def effect_custom_frame():
    """Bascule l'appareil sur l'image envoyée par set_custom_frame (non mémorisé)."""
    return 0x0F, 0x02, 0x0C, bytes((NOSTORE, ZERO_LED, EFFECT_CUSTOM)) + bytes(9)


def set_custom_frame(row, start_col, colors):
    data = b"".join(rgb(c) for c in colors)
    stop_col = start_col + len(colors) - 1
    if len(data) > 75:
        raise ValueError("trop de LED pour une seule ligne")
    return 0x0F, 0x03, 0x47, bytes((0, 0, row, start_col, stop_col)) + data


def set_brightness(led, value):
    return 0x0F, 0x04, 0x03, bytes((VARSTORE, led, max(0, min(255, value))))


def get_brightness(led):
    return 0x0F, 0x84, 0x03, bytes((VARSTORE, led))


def get_firmware():
    return 0x00, 0x81, 0x02, b""


def get_serial():
    return 0x00, 0x82, 0x16, b""


def get_battery():
    return 0x07, 0x80, 0x02, b""


def get_charging():
    return 0x07, 0x84, 0x02, b""


def set_idle_time(seconds):
    seconds = max(60, min(900, seconds))
    return 0x07, 0x03, 0x02, seconds.to_bytes(2, "big")


def get_idle_time():
    return 0x07, 0x83, 0x02, b""


def set_poll_rate(hz):
    if hz not in POLL_RATES:
        raise ValueError("fréquence possible : 125, 500 ou 1000 Hz")
    return 0x00, 0x05, 0x01, bytes((POLL_RATES[hz],))


def get_poll_rate():
    return 0x00, 0x85, 0x01, b""


def set_dpi(dpi_x, dpi_y=None):
    dpi_y = dpi_x if dpi_y is None else dpi_y
    dpi_x = max(100, min(45000, dpi_x))
    dpi_y = max(100, min(45000, dpi_y))
    return 0x04, 0x05, 0x07, bytes((VARSTORE,)) + dpi_x.to_bytes(2, "big") + dpi_y.to_bytes(2, "big") + bytes(2)


def get_dpi():
    return 0x04, 0x85, 0x07, bytes((NOSTORE,))


def set_dpi_stages(stages, active):
    """stages : liste de DPI (ou de couples x, y), active : numéro à partir de 1."""
    if not 1 <= len(stages) <= 5:
        raise ValueError("entre 1 et 5 paliers de DPI")
    if not 1 <= active <= len(stages):
        raise ValueError("palier actif hors limites")
    args = bytearray((VARSTORE, active, len(stages)))
    for i, stage in enumerate(stages):
        x, y = (stage, stage) if isinstance(stage, int) else stage
        x = max(100, min(45000, x))
        y = max(100, min(45000, y))
        args += bytes((i,)) + x.to_bytes(2, "big") + y.to_bytes(2, "big") + bytes(2)
    return 0x04, 0x06, 0x26, bytes(args)


def get_dpi_stages():
    return 0x04, 0x86, 0x26, bytes((VARSTORE,))


def parse_dpi_stages(args: bytes):
    active, count = args[1], args[2]
    stages = []
    for i in range(min(count, 5)):
        o = 3 + i * 7
        stages.append((int.from_bytes(args[o + 1:o + 3], "big"), int.from_bytes(args[o + 3:o + 5], "big")))
    return stages, active


# --- Kraken V3 (report 0x40 de 15 octets) ----------------------------------

KRAKEN_REPORT_ID = 0x40
KRAKEN_LEN = 15
KRAKEN_SET_MODE = 0x01
KRAKEN_SET_BRIGHTNESS = 0x02
KRAKEN_SET_COLOR = 0x03
KRAKEN_MODE_WAVE = 0x03
KRAKEN_MODE_DIRECT = 0x08


def _kraken(command, args=b""):
    buf = bytearray(KRAKEN_LEN)
    buf[0] = KRAKEN_REPORT_ID
    buf[1] = command
    buf[2:2 + len(args)] = args
    return bytes(buf)


def kraken_mode_direct():
    return _kraken(KRAKEN_SET_MODE, bytes((0x00, 0x0F, KRAKEN_MODE_DIRECT)))


def kraken_set_color(color):
    return _kraken(KRAKEN_SET_COLOR, b"\x00" + rgb(color))


def kraken_mode_wave():
    return _kraken(KRAKEN_SET_MODE, bytes((0x00, 0x0F, KRAKEN_MODE_WAVE)))


def kraken_mode_breathing(colors):
    colors = list(colors)[:2]
    if not colors:
        raise ValueError("au moins une couleur")
    n = len(colors)
    return _kraken(KRAKEN_SET_MODE, bytes((0x01, 0x00, n, n)) + b"".join(rgb(c) for c in colors))


def kraken_set_brightness(value):
    return _kraken(KRAKEN_SET_BRIGHTNESS, bytes((0x00, 0x00, max(0, min(255, value)))))


# Retour micro (sidetone), relevé dans une capture USB de Synapse :
# SET_REPORT sortie, report 0x70 sur l'interface 3, 5 octets « 70 01 01 <activé> <niveau 0-100> ».
KRAKEN_SIDETONE_REPORT = 0x70


def kraken_sidetone(enabled, level):
    return bytes((KRAKEN_SIDETONE_REPORT, 0x01, 0x01, 1 if enabled else 0, max(0, min(100, int(level)))))


# Variantes à essayer pour retrouver un éventuel retour micro matériel caché dans le firmware 1020.
# Seuls « 70 01 01 » est connu (capture de Synapse) ; les deux octets suivant 0x70 ont un rôle inconnu.
SIDETONE_LAB = (
    ("A", "70 01 00"), ("B", "70 01 02"), ("C", "70 01 03"),
    ("D", "70 00 01"), ("E", "70 02 01"), ("F", "70 03 01"),
)


def kraken_sidetone_variant(prefix_hex, level):
    return bytes.fromhex(prefix_hex) + bytes((1, max(0, min(100, int(level)))))


# --- Mode de l'appareil et molette ------------------------------------------

DEVICE_MODE_NORMAL = 0x00   # le firmware gère lui-même les boutons DPI
DEVICE_MODE_DRIVER = 0x03   # mode imposé par Synapse : boutons DPI inactifs sans logiciel


def set_device_mode(mode=DEVICE_MODE_NORMAL):
    return 0x00, 0x04, 0x02, bytes((mode, 0x00))


def get_device_mode():
    return 0x00, 0x84, 0x02, b""


SCROLL_TACTILE = 0x00
SCROLL_FREESPIN = 0x01


def set_scroll_mode(mode):
    return 0x02, 0x14, 0x02, bytes((VARSTORE, mode))


def get_scroll_mode():
    return 0x02, 0x94, 0x02, bytes((VARSTORE,))


def set_scroll_acceleration(enabled):
    return 0x02, 0x16, 0x02, bytes((VARSTORE, int(bool(enabled))))


def get_scroll_acceleration():
    return 0x02, 0x96, 0x02, bytes((VARSTORE,))


def set_smart_reel(enabled):
    return 0x02, 0x17, 0x02, bytes((VARSTORE, int(bool(enabled))))


def get_smart_reel():
    return 0x02, 0x97, 0x02, bytes((VARSTORE,))
