"""Couleurs, polices et petits outils de dessin partagés par l'interface."""

import colorsys
import sys

BG = "#0b0d10"
SIDEBAR = "#101317"
CARD = "#15191e"
CARD_HI = "#1c2128"
BORDER = "#252b33"
TEXT = "#e9eef3"
MUTED = "#8793a0"
FAINT = "#4b5562"
ACCENT = "#44d62c"
ACCENT_HOVER = "#3ab826"
ACCENT_TEXT = "#071004"
DANGER = "#ff5d5d"
WARNING = "#ffb547"

FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

SWATCHES = ["#44d62c", "#00e5ff", "#2d6bff", "#8a2be2", "#ff2d95", "#ff2a2a", "#ff8c00", "#ffe14d", "#ffffff"]


def hex_to_rgb(color):
    color = (color or "#000000").lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(a, b, t):
    """Mélange a vers b (t = 0 -> a, t = 1 -> b)."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([x + (y - x) * t for x, y in zip(ra, rb)])


def dim(color, factor, base="#000000"):
    return mix(base, color, max(0.0, min(1.0, factor)))


def hue(h, s=1.0, v=1.0):
    return rgb_to_hex([c * 255 for c in colorsys.hsv_to_rgb(h % 1.0, s, v)])


def rounded_rect(canvas, x1, y1, x2, y2, r=10, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)
