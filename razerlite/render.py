"""Rendus réalistes des appareils (PIL), avec masques par zone pour l'éclairage.

Chaque appareil est dessiné une fois par taille (sur-échantillonné puis réduit pour l'anticrénelage).
Ensuite compose() ne fait que colorer les masques des zones : assez rapide pour animer.
"""

import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SS = 3  # sur-échantillonnage


# --- outils ----------------------------------------------------------------

def spline(points, closed=True, steps=14):
    """Courbe de Catmull-Rom passant par les points (pour des contours bien lisses)."""
    pts = list(points)
    n = len(pts)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed or i > 0 else pts[0]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed or i + 2 < n else pts[-1]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    if not closed:
        out.append(pts[-1])
    return out


def mask_of(size, draw_fn):
    m = Image.new("L", size, 0)
    draw_fn(ImageDraw.Draw(m))
    return m


def gradient(size, top, bottom, horizontal=False):
    w, h = size
    g = Image.new("RGB", (1, 256) if not horizontal else (256, 1))
    px = g.load()
    for i in range(256):
        c = tuple(int(top[k] + (bottom[k] - top[k]) * i / 255) for k in range(3))
        px[(0, i) if not horizontal else (i, 0)] = c
    return g.resize(size, Image.BILINEAR)


def radial(size, center, radius, inner, outer):
    """Dégradé radial (luminosité) en niveaux de gris."""
    w, h = size
    small = Image.new("L", (64, 64))
    px = small.load()
    cx, cy = center[0] / w * 64, center[1] / h * 64
    rx, ry = radius[0] / w * 64, radius[1] / h * 64
    for y in range(64):
        for x in range(64):
            d = min(1.0, math.hypot((x - cx) / rx, (y - cy) / ry))
            px[x, y] = int(inner + (outer - inner) * d)
    return small.resize(size, Image.BILINEAR)


def paint(base, color, mask):
    layer = Image.new("RGBA", base.size, color if len(color) == 4 else color + (255,))
    layer.putalpha(mask)
    base.alpha_composite(layer)


def relief(base, mask, radius, strength=1.0, light=(-1, -1)):
    """Donne du volume : éclaire les pentes tournées vers la lumière, assombrit les autres."""
    blur = mask.filter(ImageFilter.GaussianBlur(radius))
    d = max(1, int(radius * 0.45))
    inner = ImageChops.offset(blur, -light[0] * d, -light[1] * d)
    hi = ImageChops.multiply(ImageChops.subtract(blur, inner, scale=1.0 / (3.0 * strength)), mask)
    lo = ImageChops.multiply(ImageChops.subtract(inner, blur, scale=1.0 / (3.2 * strength)), mask)
    paint(base, (255, 255, 255), hi)
    paint(base, (0, 0, 0), lo)


def grain(base, mask, amount=10):
    """Texture mate très légère (plastique soft-touch)."""
    noise = Image.effect_noise(base.size, 40).point(lambda v: max(0, v - 128) * amount // 40)
    paint(base, (255, 255, 255), ImageChops.multiply(noise, mask))


def edge_of(mask, width):
    return ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(max(3, int(width) | 1))))


def scale_mask(mask, factor):
    if factor >= 0.999:
        return mask
    return mask.point(lambda v: int(v * factor))


def find_font(size, bold=False):
    candidates = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        candidates += [os.path.join(windir, "Fonts", "segoeuib.ttf" if bold else "segoeui.ttf")]
    candidates += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def logo_mask(size, cx, cy, r):
    """Masque du symbole RazerLite exact (assets/mark.png), centré en (cx, cy), de rayon r."""
    from . import logo
    d = max(4, int(r * 2))
    alpha = logo.mark(d).getchannel("A").point(lambda v: 0 if v < 110 else min(255, (v - 110) * 3))
    m = Image.new("L", size, 0)
    m.paste(alpha, (int(cx - d / 2), int(cy - d / 2)))
    return m


def engrave(base, mask):
    """Symbole gravé, visible même éteint."""
    paint(base, (78, 83, 90), mask.point(lambda v: v * 2 // 3))


# --- appareils -----------------------------------------------------------------

class Rendered:
    """Image de base + masques de lumière, à la taille d'affichage."""

    def __init__(self, base, zones, under=None, keys=None, legend=None, gaps=None, buttons=None, key_codes=None):
        self.base = base          # RGBA
        self.zones = zones        # zone -> [(masque L, intensité)]
        self.under = under or {}  # zone -> masque L (halo dessiné sous l'appareil)
        self.keys = keys or []    # clavier : [(x0, y0, x1, y1, position 0..1)]
        self.legend = legend      # clavier : masque des légendes
        self.gaps = gaps          # clavier : masque des interstices entre touches
        self.buttons = buttons or {}  # souris : bouton -> (masque, contour)
        self.key_codes = key_codes or []  # clavier : code de touche Windows pour chaque touche

    def compose(self, colors, key_colors=None, pressed=(), accent=(68, 214, 44)):
        """colors : zone -> (r, g, b) ou None ; key_colors : (r, g, b) par touche ;
        pressed : index de touches (clavier) ou noms de boutons (souris) enfoncés."""
        size = self.base.size
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        for zone, mask in self.under.items():
            c = colors.get(zone)
            if c:
                paint(out, c, mask)
        out.alpha_composite(self.base)
        for zone, layers in self.zones.items():
            c = colors.get(zone)
            if not c:
                continue
            for mask, level in layers:
                paint(out, c, scale_mask(mask, level))
        if key_colors is not None and self.keys:
            light = Image.new("RGB", size, (0, 0, 0))
            d = ImageDraw.Draw(light)
            for (x0, y0, x1, y1, _), c in zip(self.keys, key_colors):
                if c:
                    d.rectangle((x0, y0, x1, y1), fill=c)
            glow = light.filter(ImageFilter.GaussianBlur(max(1, size[0] / 260)))
            glow_rgba = glow.convert("RGBA")
            glow_rgba.putalpha(ImageChops.multiply(self.gaps, glow.convert("L").point(lambda v: min(255, v * 3))))
            out.alpha_composite(glow_rgba)
            lit = light.convert("RGBA")
            lit.putalpha(ImageChops.multiply(self.legend, light.convert("L").point(lambda v: 255 if v > 8 else 0)))
            out.alpha_composite(lit)
        if pressed:
            d = ImageDraw.Draw(out)
            for p in pressed:
                if isinstance(p, int) and p < len(self.keys):
                    x0, y0, x1, y1, _ = self.keys[p]
                    layer = Image.new("RGBA", size, (0, 0, 0, 0))
                    ImageDraw.Draw(layer).rounded_rectangle((x0, y0 + 1, x1, y1 + 1), radius=3, fill=(255, 255, 255, 70),
                                                            outline=accent + (255,), width=2)
                    out.alpha_composite(layer)
                elif p in self.buttons:
                    fill, edge = self.buttons[p]
                    paint(out, (255, 255, 255), fill.point(lambda v: v * 2 // 7))
                    paint(out, accent, edge)
        return out


def render_mouse(w, h):
    """Basilisk V3 Pro vue de dessus (droitier, repose-pouce à gauche)."""
    W, H = w * SS, h * SS
    mw = min(W * 0.64, H * 0.52)
    mh = mw * 1.72
    ox, oy = (W - mw) / 2, (H - mh) / 2

    def P(x, y):
        return (ox + x * mw, oy + y * mh)

    outline = [P(*p) for p in [
        (0.50, 0.000), (0.68, 0.012), (0.82, 0.070), (0.89, 0.180), (0.915, 0.330), (0.93, 0.500),
        (0.925, 0.660), (0.895, 0.800), (0.83, 0.915), (0.70, 0.985), (0.52, 1.000), (0.33, 0.985),
        (0.18, 0.940), (0.075, 0.860), (0.02, 0.745), (0.035, 0.640), (0.085, 0.555), (0.105, 0.440),
        (0.105, 0.300), (0.135, 0.160), (0.21, 0.065), (0.33, 0.015)]]
    body = spline(outline)
    size = (W, H)
    base = Image.new("RGBA", size, (0, 0, 0, 0))

    # Ombre portée
    shadow = mask_of(size, lambda d: d.polygon([(x + mw * 0.015, y + mh * 0.02) for x, y in body], fill=200))
    paint(base, (0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(mw * 0.05)))

    body_mask = mask_of(size, lambda d: d.polygon(body, fill=255))
    shell = gradient(size, (38, 41, 46), (20, 22, 25)).convert("RGBA")
    shell.putalpha(body_mask)
    base.alpha_composite(shell)
    # Reflet doux sur le dos de la souris
    sheen = radial(size, P(0.40, 0.50), (mw * 0.42, mh * 0.30), 60, 0)
    paint(base, (255, 255, 255), ImageChops.multiply(sheen, body_mask).point(lambda v: v // 5))
    relief(base, body_mask, mw * 0.10, 0.65)
    grain(base, body_mask, 7)
    # Reflet spéculaire allongé sur la bosse
    spec = mask_of(size, lambda m: m.ellipse((*P(0.30, 0.40), *P(0.50, 0.64)), fill=34))
    paint(base, (255, 255, 255), ImageChops.multiply(spec.filter(ImageFilter.GaussianBlur(mw * 0.07)), body_mask))

    d = ImageDraw.Draw(base)
    rim = (58, 63, 70, 255)
    d.line(body + [body[0]], fill=rim, width=int(SS * 1.2), joint="curve")

    # Séparation des boutons gauche/droit et arrière des boutons
    split = spline([P(0.47, 0.0), P(0.475, 0.12), P(0.48, 0.25), P(0.485, 0.36)], closed=False)
    d.line(split, fill=(10, 11, 13, 255), width=int(SS * 1.6))
    rear = spline([P(0.12, 0.40), P(0.30, 0.375), P(0.50, 0.37), P(0.72, 0.375), P(0.915, 0.40)], closed=False)
    d.line(rear, fill=(12, 13, 15, 255), width=int(SS * 1.6))
    # Panneau du repose-pouce (texture légèrement différente)
    thumb = spline([P(0.03, 0.66), P(0.10, 0.56), P(0.13, 0.70), P(0.12, 0.86), P(0.07, 0.86), P(0.025, 0.75)])
    d.polygon(thumb, fill=(24, 26, 29, 255))
    # Boutons latéraux et gâchette de sensibilité
    for y0, y1 in ((0.43, 0.505), (0.515, 0.585)):
        d.rounded_rectangle((*P(0.085, y0), *P(0.125, y1)), radius=mw * 0.02, fill=(46, 50, 56, 255),
                            outline=(14, 15, 17, 255), width=SS)
    d.rounded_rectangle((*P(0.01, 0.625), *P(0.05, 0.665)), radius=mw * 0.015, fill=(46, 50, 56, 255))

    # Molette : logement, roue crantée
    d.rounded_rectangle((*P(0.43, 0.085), *P(0.565, 0.235)), radius=mw * 0.06, fill=(8, 9, 10, 255))
    wheel_box = (*P(0.455, 0.095), *P(0.54, 0.225))
    d.rounded_rectangle(wheel_box, radius=mw * 0.04, fill=(30, 33, 37, 255))
    for i in range(14):
        y = wheel_box[1] + (wheel_box[3] - wheel_box[1]) * (i + 0.5) / 14
        d.line((wheel_box[0] + SS * 2, y, wheel_box[2] - SS * 2, y), fill=(18, 20, 22, 255), width=SS)
    # Boutons derrière la molette (mode molette, palier DPI)
    for y0 in (0.255, 0.305):
        d.rounded_rectangle((*P(0.455, y0), *P(0.54, y0 + 0.035)), radius=mw * 0.02, fill=(40, 44, 49, 255),
                            outline=(12, 13, 15, 255), width=SS)

    # Volume des petites pièces
    small_parts = mask_of(size, lambda m: [m.rounded_rectangle(b, radius=mw * 0.02, fill=255) for b in (
        (*P(0.085, 0.43), *P(0.125, 0.505)), (*P(0.085, 0.515), *P(0.125, 0.585)),
        (*P(0.455, 0.255), *P(0.54, 0.29)), (*P(0.455, 0.305), *P(0.54, 0.34)), wheel_box)])
    relief(base, small_parts, mw * 0.012, 0.8)

    # Zones des boutons (pour afficher les appuis)
    split_x = P(0.478, 0)[0]
    front = ImageChops.multiply(body_mask, mask_of(size, lambda m: m.rectangle((0, 0, W, P(0, 0.375)[1]), fill=255)))
    holes = mask_of(size, lambda m: m.rounded_rectangle((*P(0.43, 0.085), *P(0.565, 0.235)), radius=mw * 0.06, fill=255))
    front = ImageChops.subtract(front, holes)
    left_btn = ImageChops.multiply(front, mask_of(size, lambda m: m.rectangle((0, 0, split_x, H), fill=255)))
    right_btn = ImageChops.subtract(front, left_btn)
    btn_masks = {
        "left": left_btn, "right": right_btn,
        "middle": mask_of(size, lambda m: m.rounded_rectangle(wheel_box, radius=mw * 0.04, fill=255)),
        "forward": mask_of(size, lambda m: m.rounded_rectangle((*P(0.085, 0.43), *P(0.125, 0.505)), radius=mw * 0.02, fill=255)),
        "back": mask_of(size, lambda m: m.rounded_rectangle((*P(0.085, 0.515), *P(0.125, 0.585)), radius=mw * 0.02, fill=255)),
        "mode": mask_of(size, lambda m: m.rounded_rectangle((*P(0.455, 0.255), *P(0.54, 0.29)), radius=mw * 0.02, fill=255)),
        "dpi": mask_of(size, lambda m: m.rounded_rectangle((*P(0.455, 0.305), *P(0.54, 0.34)), radius=mw * 0.02, fill=255)),
    }

    # Masques de lumière
    wheel_light = mask_of(size, lambda m: m.rounded_rectangle((*P(0.462, 0.10), *P(0.533, 0.22)),
                                                              radius=mw * 0.035, outline=255, width=int(SS * 2.2)))
    wheel_core = mask_of(size, lambda m: [m.line((P(0.47, 0.10 + 0.12 * (i + 0.5) / 14)[0], P(0, 0.10 + 0.12 * (i + 0.5) / 14)[1],
                                                  P(0.525, 0)[0], P(0, 0.10 + 0.12 * (i + 0.5) / 14)[1]), fill=110, width=SS)
                                                  for i in range(14)])
    logo_c, logo_r = P(0.515, 0.735), mw * 0.10
    logo = logo_mask(size, logo_c[0], logo_c[1], logo_r)
    engrave(base, logo)
    # Bande inférieure : bord arrière et flancs bas de la souris
    strip_pts = [p for p in body if p[1] > oy + mh * 0.50]
    strip = mask_of(size, lambda m: m.line(strip_pts, fill=255, width=int(mw * 0.035), joint="curve"))
    strip_under = strip.filter(ImageFilter.GaussianBlur(mw * 0.06)).point(lambda v: min(255, v * 2))
    strip_edge = ImageChops.multiply(strip, mask_of(size, lambda m: m.line(body + [body[0]], fill=255, width=int(SS * 2.5))))

    zones = {
        "Molette": [(ImageChops.lighter(wheel_light, wheel_core), 1.0),
                    (wheel_light.filter(ImageFilter.GaussianBlur(mw * 0.03)), 0.7)],
        "Logo": [(logo, 1.0), (logo.filter(ImageFilter.GaussianBlur(mw * 0.025)), 0.8)],
        "Bande": [(strip_edge, 1.0)],
    }
    small = lambda m: m.resize((w, h), Image.LANCZOS)  # noqa: E731
    buttons = {k: (small(m), small(edge_of(m, SS * 2))) for k, m in btn_masks.items()}
    return finish(base, zones, {"Bande": strip_under}, w, h, buttons=buttons)


def finish(base, zones, under, w, h, **kw):
    size = (w, h)
    shrink = lambda m: m.resize(size, Image.LANCZOS)  # noqa: E731
    return Rendered(base.resize(size, Image.LANCZOS),
                    {z: [(shrink(m), lvl) for m, lvl in layers] for z, layers in zones.items()},
                    {z: shrink(m) for z, m in under.items()}, **kw)


KEY_ROWS = [
    # (étiquette, largeur en unités) ; None = espace vide
    [("Esc", 1), (None, 1), ("F1", 1), ("F2", 1), ("F3", 1), ("F4", 1), (None, .5), ("F5", 1), ("F6", 1), ("F7", 1), ("F8", 1),
     (None, .5), ("F9", 1), ("F10", 1), ("F11", 1), ("F12", 1), (None, .25), ("Imp", 1), ("Arr", 1), ("Pse", 1)],
    [("²", 1), ("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1), ("8", 1), ("9", 1), ("0", 1), (")", 1),
     ("=", 1), ("⌫", 2), (None, .25), ("Ins", 1), ("Déb", 1), ("Pg↑", 1), (None, .25), ("Num", 1), ("/", 1), ("*", 1), ("-", 1)],
    [("Tab", 1.5), ("A", 1), ("Z", 1), ("E", 1), ("R", 1), ("T", 1), ("Y", 1), ("U", 1), ("I", 1), ("O", 1), ("P", 1),
     ("^", 1), ("$", 1), ("↵", 1.5), (None, .25), ("Suppr", 1), ("Fin", 1), ("Pg↓", 1), (None, .25), ("7", 1), ("8", 1),
     ("9", 1), ("+", 1)],
    [("Verr", 1.75), ("Q", 1), ("S", 1), ("D", 1), ("F", 1), ("G", 1), ("H", 1), ("J", 1), ("K", 1), ("L", 1), ("M", 1),
     ("ù", 1), ("*", 1), (None, 1.25), (None, .25), (None, 3), (None, .25), ("4", 1), ("5", 1), ("6", 1), (None, 1)],
    [("⇧", 1.25), ("<", 1), ("W", 1), ("X", 1), ("C", 1), ("V", 1), ("B", 1), ("N", 1), (",", 1), (";", 1), (":", 1),
     ("!", 1), ("⇧", 2.75), (None, .25), (None, 1), ("↑", 1), (None, 1), (None, .25), ("1", 1), ("2", 1), ("3", 1),
     ("↵", 1)],
    [("Ctrl", 1.25), ("⊞", 1.25), ("Alt", 1.25), ("", 6.25), ("AltGr", 1.25), ("Fn", 1.25), ("☰", 1.25), ("Ctrl", 1.25),
     (None, .25), ("←", 1), ("↓", 1), ("→", 1), (None, .25), ("0", 2), (".", 1), (None, 1)],
]
TALL_KEYS = {(2, 22), (4, 21)}


def _sc(*codes):
    return [("sc", c) for c in codes]


def _vk(*codes):
    return [("vk", c) for c in codes]


# Un code par touche étiquetée de KEY_ROWS, dans le même ordre
KEY_CODES = [
    _sc(0x01, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x57, 0x58) + _vk(0x2C) + _sc(0x46) + _vk(0x13),
    _sc(0x29, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E)
    + _vk(0x2D, 0x24, 0x21, 0x90, 0x6F, 0x6A, 0x6D),
    _sc(0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B) + _vk(0x0D, 0x2E, 0x23, 0x22,
                                                                                         0x67, 0x68, 0x69, 0x6B),
    _vk(0x14) + _sc(0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2B) + _vk(0x64, 0x65, 0x66),
    _vk(0xA0) + _sc(0x56, 0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35) + _vk(0xA1, 0x26, 0x61, 0x62,
                                                                                        0x63, 0x0D),
    _vk(0xA2, 0x5B, 0xA4, 0x20, 0xA5) + [None] + _vk(0x5D, 0xA3, 0x25, 0x28, 0x27, 0x60, 0x6E),
]  # « + » et « Entrée » du pavé numérique font deux rangées


def render_keyboard(w, h):
    """DeathStalker V2 Pro : clavier complet extra-plat, touches basses, molette média en haut à droite."""
    W, H = w * SS, h * SS
    units_w, units_h = 22.5, 6.6
    u = min((W * 0.94) / (units_w + 0.9), (H * 0.86) / (units_h + 1.0))
    kb_w, kb_h = (units_w + 0.9) * u, (units_h + 1.0) * u
    ox, oy = (W - kb_w) / 2, (H - kb_h) / 2
    size = (W, H)
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    plate_box = (ox, oy, ox + kb_w, oy + kb_h)
    shadow = mask_of(size, lambda d: d.rounded_rectangle((ox + u * .1, oy + u * .25, ox + kb_w + u * .1, oy + kb_h + u * .3),
                                                         radius=u * .5, fill=210))
    paint(base, (0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(u * .45)))
    plate_mask = mask_of(size, lambda d: d.rounded_rectangle(plate_box, radius=u * .45, fill=255))
    plate = gradient(size, (40, 42, 46), (24, 25, 28)).convert("RGBA")
    plate.putalpha(plate_mask)
    base.alpha_composite(plate)
    relief(base, plate_mask, u * .18, 1.0)
    grain(base, plate_mask, 5)
    d = ImageDraw.Draw(base)
    d.rounded_rectangle(plate_box, radius=u * .45, outline=(66, 70, 76, 255), width=int(SS * 1.2))
    # Bande de face avant (brossée)
    d.rounded_rectangle((ox + u * .3, oy + kb_h - u * .42, ox + kb_w - u * .3, oy + kb_h - u * .3), radius=u * .05,
                        fill=(52, 55, 60, 255))

    kx0, ky0 = ox + u * .45, oy + u * .55
    keys, legend_draws = [], []
    small = find_font(int(u * .26))
    tiny = find_font(int(u * .2))
    for r, row in enumerate(KEY_ROWS):
        x = kx0
        y = ky0 + (r * 1.0 + (0.35 if r > 0 else 0)) * u
        for c, (label, width) in enumerate(row):
            if label is not None:
                tall = (r, c) in TALL_KEYS
                x0, y0 = x + u * .07, y + u * .07
                x1, y1 = x + width * u - u * .07, y + (2 if tall else 1) * u - u * .07
                keys.append((x0, y0, x1, y1, (x - kx0) / (units_w * u)))
                legend_draws.append((label, x0, y0, x1, y1))
            x += width * u
    # Touches extra-plates : bord sombre, dessus légèrement plus clair
    for x0, y0, x1, y1, _ in keys:
        d.rounded_rectangle((x0, y0, x1, y1), radius=u * .1, fill=(13, 14, 16, 255))
        d.rounded_rectangle((x0 + SS, y0 + SS, x1 - SS, y1 - SS * 2), radius=u * .09, fill=(31, 33, 37, 255))
    caps = mask_of(size, lambda m: [m.rounded_rectangle((x0 + SS, y0 + SS, x1 - SS, y1 - SS * 2), radius=u * .09, fill=255)
                                    for x0, y0, x1, y1, _ in keys])
    relief(base, caps, u * .06, 1.1)
    d = ImageDraw.Draw(base)
    legend = Image.new("L", size, 0)
    ld = ImageDraw.Draw(legend)
    for label, x0, y0, x1, y1 in legend_draws:
        f = small if len(label) <= 2 else tiny
        ld.text((x0 + u * .14, y0 + u * .1), label, fill=255, font=f)
        d.text((x0 + u * .14, y0 + u * .1), label, fill=(120, 126, 134, 255), font=f)
    # Boutons média et molette de volume (en haut à droite)
    mx = kx0 + (units_w - 4) * u
    for i in range(3):
        d.rounded_rectangle((mx + i * u * .62, oy + u * .14, mx + i * u * .62 + u * .48, oy + u * .36), radius=u * .1,
                            fill=(20, 21, 24, 255))
    roller = (mx + u * 2.05, oy + u * .12, mx + u * 3.95, oy + u * .38)
    d.rounded_rectangle(roller, radius=u * .13, fill=(8, 9, 10, 255))
    for i in range(16):
        xx = roller[0] + (roller[2] - roller[0]) * (i + .5) / 16
        d.line((xx, roller[1] + SS * 2, xx, roller[3] - SS * 2), fill=(44, 47, 52, 255), width=SS)

    keyzone = mask_of(size, lambda m: [m.rounded_rectangle((x0, y0, x1, y1), radius=u * .1, fill=255) for x0, y0, x1, y1, _ in keys])
    gaps = ImageChops.subtract(keyzone.filter(ImageFilter.MaxFilter(int(u * .12) | 1)),
                               mask_of(size, lambda m: [m.rounded_rectangle((x0 + SS, y0 + SS, x1 - SS, y1 - SS * 2),
                                                                            radius=u * .09, fill=255)
                                                        for x0, y0, x1, y1, _ in keys]))
    sz = (w, h)
    k = 1 / SS
    return Rendered(base.resize(sz, Image.LANCZOS), {}, {},
                    keys=[(x0 * k, y0 * k, x1 * k, y1 * k, pos) for x0, y0, x1, y1, pos in keys],
                    legend=legend.resize(sz, Image.LANCZOS), gaps=gaps.resize(sz, Image.LANCZOS),
                    key_codes=[code for row in KEY_CODES for code in row])


def render_headset(w, h):
    """Kraken V3 HyperSense vu de trois quarts : coque gauche ovale avec logo éclairé, arceau rembourré
    et fourches en alu, micro amovible à gauche, coque droite en retrait."""
    W, H = w * SS, h * SS
    s = min(W / 300, H / 330)
    cx, cy = W / 2, H / 2
    size = (W, H)
    base = Image.new("RGBA", size, (0, 0, 0, 0))

    def S(x, y):
        return (cx + x * s, cy + y * s)

    metal, metal_dark = (128, 134, 142, 255), (70, 74, 80, 255)
    left_box = (*S(-112, -22), *S(8, 132))     # coque gauche (face extérieure, vers nous)
    right_box = (*S(52, -8), *S(132, 112))     # coque droite (on voit son coussin)

    shadow = mask_of(size, lambda d: [d.ellipse((*S(-104, -6), *S(20, 146)), fill=200),
                                      d.ellipse((*S(56, 6), *S(140, 124)), fill=140)])
    paint(base, (0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(12 * s)))
    d = ImageDraw.Draw(base)

    # Coque droite, en retrait : coussin en simili-cuir vers nous, bord de coque
    d.ellipse(right_box, fill=(22, 23, 26, 255), outline=(52, 56, 62, 255), width=int(2 * s))
    d.ellipse((*S(62, 4), *S(126, 102)), fill=(10, 10, 12, 255))
    d.ellipse((*S(76, 22), *S(114, 86)), fill=(26, 27, 30, 255))  # tissu au centre du coussin
    # Fourche droite
    d.arc((*S(44, -18), *S(140, 122)), start=190, end=350, fill=metal_dark, width=int(5 * s))
    d.line((S(92, -18), S(92, -40)), fill=metal_dark, width=int(6 * s))

    # Arceau : bandeau extérieur + coussin dessous, de la coque gauche à la coque droite
    outer = spline([S(-52, -62), S(-50, -118), S(-14, -152), S(40, -146), S(80, -110), S(92, -48)], closed=False)
    inner = spline([S(-30, -60), S(-28, -104), S(-6, -128), S(36, -124), S(64, -96), S(72, -46)], closed=False)
    band = outer + inner[::-1]
    band_mask = mask_of(size, lambda m: m.polygon(band, fill=255))
    band_img = gradient(size, (44, 47, 52), (18, 19, 22)).convert("RGBA")
    band_img.putalpha(band_mask)
    base.alpha_composite(band_img)
    relief(base, band_mask, 8 * s, 0.8)
    grain(base, band_mask, 6)
    d = ImageDraw.Draw(base)
    cushion = spline([S(-36, -62), S(-34, -106), S(-8, -132), S(37, -128), S(68, -98), S(77, -46)], closed=False)
    d.line(cushion, fill=(12, 12, 14, 255), width=int(9 * s), joint="curve")
    d.line(outer, fill=(70, 74, 81, 255), width=int(2 * s), joint="curve")
    # surpiqûre du bandeau
    stitch = spline([S(-44, -64), S(-42, -114), S(-12, -144), S(39, -138), S(74, -106), S(84, -50)], closed=False)
    for i in range(0, len(stitch) - 1, 2):
        d.line((stitch[i], stitch[i + 1]), fill=(58, 61, 67, 255), width=max(1, int(1.2 * s)))
    # Curseur de taille en alu (gauche)
    d.rounded_rectangle((*S(-56, -66), *S(-44, -30)), radius=3 * s, fill=metal, outline=metal_dark, width=int(s))
    for k in range(4):
        d.line((S(-54, -60 + k * 7), S(-46, -60 + k * 7)), fill=metal_dark, width=max(1, int(s)))

    # Fourche gauche en U autour du haut de la coque
    d.arc((*S(-122, -32), *S(18, 140)), start=185, end=355, fill=metal, width=int(6 * s))
    d.arc((*S(-122, -32), *S(18, 140)), start=185, end=355, fill=(170, 176, 184, 255), width=max(1, int(1.5 * s)))
    for px in (-118, 14):
        d.ellipse((*S(px - 6, 40), *S(px + 6, 52)), fill=metal_dark)  # pivots

    # Coussin gauche (dépasse derrière la coque)
    d.ellipse((*S(-100, -14), *S(18, 136)), fill=(11, 11, 13, 255))
    # Coque gauche
    cup_mask = mask_of(size, lambda m: m.ellipse(left_box, fill=255))
    shell = gradient(size, (46, 49, 55), (17, 18, 21)).convert("RGBA")
    shell.putalpha(cup_mask)
    base.alpha_composite(shell)
    sheen = radial(size, S(-72, 20), (60 * s, 70 * s), 70, 0)
    paint(base, (255, 255, 255), ImageChops.multiply(sheen, cup_mask).point(lambda v: v // 4))
    relief(base, cup_mask, 14 * s, 0.75)
    grain(base, cup_mask, 6)
    d = ImageDraw.Draw(base)
    d.ellipse(left_box, outline=(70, 74, 81, 255), width=int(2 * s))
    plate = (*S(-92, 2), *S(-12, 108))
    d.ellipse(plate, fill=(21, 22, 25, 255), outline=(44, 47, 53, 255), width=int(2 * s))

    # Commandes au dos de la coque gauche : molette de volume et bouton micro
    d.rounded_rectangle((*S(2, 66), *S(12, 92)), radius=4 * s, fill=(26, 28, 31, 255), outline=(8, 8, 9, 255),
                        width=max(1, int(s)))
    for k in range(6):
        d.line((S(3, 69 + k * 4), S(11, 69 + k * 4)), fill=(50, 53, 58, 255), width=max(1, int(s)))
    d.rounded_rectangle((*S(-2, 98), *S(8, 110)), radius=3 * s, fill=(34, 36, 40, 255), outline=(8, 8, 9, 255),
                        width=max(1, int(s)))

    # Micro amovible : prise à l'avant bas de la coque, perche souple, capsule
    boom = spline([S(-100, 104), S(-122, 122), S(-134, 142), S(-128, 158)], closed=False)
    d.line(boom, fill=(14, 15, 17, 255), width=int(7 * s), joint="curve")
    d.line(boom, fill=(48, 51, 56, 255), width=max(1, int(1.5 * s)), joint="curve")
    d.ellipse((*S(-106, 96), *S(-94, 110)), fill=(30, 32, 36, 255), outline=(8, 8, 9, 255), width=max(1, int(s)))
    d.rounded_rectangle((*S(-138, 150), *S(-116, 164)), radius=6 * s, fill=(20, 21, 24, 255),
                        outline=(60, 64, 70, 255), width=max(1, int(s)))

    logo_c = S(-52, 55)
    logo = logo_mask(size, logo_c[0], logo_c[1], 30 * s)
    engrave(base, logo)
    zones = {"Casque": [(logo, 1.0), (logo.filter(ImageFilter.GaussianBlur(8 * s)), 0.9)]}
    return finish(base, zones, {}, w, h)


RENDERERS = {"mouse": render_mouse, "keyboard": render_keyboard, "headset": render_headset}
_cache = {}


def get(kind, w, h):
    key = (kind, w, h)
    if key not in _cache:
        if len(_cache) > 6:
            _cache.clear()
        _cache[key] = RENDERERS[kind](w, h)
    return _cache[key]
