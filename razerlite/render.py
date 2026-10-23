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


def dots(base, mask, step, radius, color):
    """Texture pointillée (grips en caoutchouc, grille de haut-parleur) limitée à un masque."""
    layer = Image.new("L", base.size, 0)
    d = ImageDraw.Draw(layer)
    W, H = base.size
    y, row = 0.0, 0
    while y < H:
        x = (step / 2) if row % 2 else 0.0
        while x < W:
            d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
            x += step
        y += step * 0.87
        row += 1
    paint(base, color, ImageChops.multiply(layer, mask))


def render_mouse(w, h):
    """Basilisk V3 Pro vue de dessus, d'après photo : avant anguleux, coupe en diagonale sur le dos,
    large repose-pouce à gauche avec grip pointillé, grip sur le flanc droit, molette éclairée
    suivie de deux petits boutons, logo sur la paume et bande lumineuse tout autour du bas."""
    W, H = w * SS, h * SS
    mw = min(W * 0.68, H * 0.55)
    mh = mw * 1.60
    ox, oy = (W - mw) / 2, (H - mh) / 2

    def P(x, y):
        return (ox + x * mw, oy + y * mh)

    outline = [P(*p) for p in [
        (0.50, 0.000), (0.70, 0.006), (0.84, 0.040), (0.92, 0.130), (0.96, 0.270), (0.98, 0.420), (0.97, 0.580),
        (0.92, 0.730), (0.83, 0.860), (0.70, 0.950), (0.55, 0.990), (0.40, 0.970), (0.27, 0.900), (0.15, 0.820),
        (0.04, 0.760), (0.00, 0.640), (0.01, 0.520), (0.05, 0.440), (0.08, 0.360), (0.09, 0.220), (0.13, 0.090),
        (0.25, 0.020)]]
    body = spline(outline)
    size = (W, H)
    base = Image.new("RGBA", size, (0, 0, 0, 0))

    shadow = mask_of(size, lambda d: d.polygon([(x + mw * 0.015, y + mh * 0.02) for x, y in body], fill=200))
    paint(base, (0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(mw * 0.05)))
    body_mask = mask_of(size, lambda d: d.polygon(body, fill=255))
    shell = gradient(size, (38, 41, 46), (18, 20, 23)).convert("RGBA")
    shell.putalpha(body_mask)
    base.alpha_composite(shell)
    sheen = radial(size, P(0.48, 0.42), (mw * 0.40, mh * 0.30), 60, 0)
    paint(base, (255, 255, 255), ImageChops.multiply(sheen, body_mask).point(lambda v: v // 5))
    relief(base, body_mask, mw * 0.10, 0.65)
    grain(base, body_mask, 7)

    # Grips en caoutchouc pointillé : repose-pouce à gauche, flanc droit
    thumb = mask_of(size, lambda m: m.polygon(spline([P(0.02, 0.47), P(0.15, 0.44), P(0.21, 0.60), P(0.18, 0.78),
                                                      P(0.06, 0.76), P(0.00, 0.62)]), fill=255))
    thumb = ImageChops.multiply(thumb, body_mask)
    paint(base, (10, 11, 13), thumb)
    dots(base, thumb, mw * 0.022, mw * 0.006, (44, 47, 52))
    right = mask_of(size, lambda m: m.polygon(spline([P(0.90, 0.40), P(0.985, 0.42), P(0.96, 0.66), P(0.90, 0.74),
                                                      P(0.86, 0.66)]), fill=255))
    right = ImageChops.multiply(right, body_mask)
    paint(base, (10, 11, 13), right)
    dots(base, right, mw * 0.022, mw * 0.006, (44, 47, 52))

    d = ImageDraw.Draw(base)
    rim = (58, 63, 70, 255)
    d.line(body + [body[0]], fill=rim, width=int(SS * 1.2), joint="curve")
    seam = (10, 11, 13, 255)
    # Séparation des clics gauche/droit, puis coupe en diagonale qui sépare les boutons de la paume
    d.line(spline([P(0.53, 0.0), P(0.535, 0.05)], closed=False), fill=seam, width=int(SS * 1.6))
    diag = [P(0.97, 0.36), P(0.60, 0.48), P(0.17, 0.70)]
    d.line(diag, fill=seam, width=int(SS * 2))
    d.line([(x, y + SS * 2) for x, y in diag], fill=(52, 56, 62, 255), width=SS)  # arête éclairée de la paume
    # Facettes de l'avant (bords biseautés des clics)
    d.line([P(0.13, 0.09), P(0.30, 0.16), P(0.36, 0.40)], fill=(26, 28, 32, 255), width=SS)
    d.line([P(0.86, 0.05), P(0.74, 0.14), P(0.70, 0.40)], fill=(26, 28, 32, 255), width=SS)
    # Boutons latéraux et palette multifonction (côté pouce)
    for y0, y1 in ((0.30, 0.37), (0.38, 0.45)):
        d.rounded_rectangle((*P(0.07, y0), *P(0.11, y1)), radius=mw * 0.02, fill=(46, 50, 56, 255),
                            outline=(14, 15, 17, 255), width=SS)
    d.rounded_rectangle((*P(0.0, 0.47), *P(0.04, 0.52)), radius=mw * 0.015, fill=(46, 50, 56, 255))

    # Molette : long logement, roue crantée éclairée
    slot = (*P(0.485, 0.055), *P(0.585, 0.30))
    d.rounded_rectangle(slot, radius=mw * 0.03, fill=(8, 9, 10, 255))
    wheel_box = (*P(0.505, 0.075), *P(0.565, 0.255))
    d.rounded_rectangle(wheel_box, radius=mw * 0.03, fill=(30, 33, 37, 255))
    for i in range(18):
        y = wheel_box[1] + (wheel_box[3] - wheel_box[1]) * (i + 0.5) / 18
        d.line((wheel_box[0] + SS * 2, y, wheel_box[2] - SS * 2, y), fill=(16, 18, 20, 255), width=SS)
    # Deux boutons derrière la molette (mode de défilement, palier DPI)
    b1 = (*P(0.5, 0.31), *P(0.57, 0.355))
    b2 = (*P(0.5, 0.365), *P(0.57, 0.41))
    d.rounded_rectangle((*P(0.485, 0.30), *P(0.585, 0.42)), radius=mw * 0.025, fill=(8, 9, 10, 255))
    for bb in (b1, b2):
        d.rounded_rectangle(bb, radius=mw * 0.015, fill=(40, 44, 49, 255), outline=(12, 13, 15, 255), width=SS)

    small_parts = mask_of(size, lambda m: [m.rounded_rectangle(b, radius=mw * 0.02, fill=255) for b in (
        (*P(0.07, 0.30), *P(0.11, 0.37)), (*P(0.07, 0.38), *P(0.11, 0.45)), b1, b2, wheel_box)])
    relief(base, small_parts, mw * 0.012, 0.8)

    # Zones des boutons (pour afficher les appuis)
    split_x = P(0.535, 0)[0]
    above = mask_of(size, lambda m: m.polygon([P(-0.1, -0.1), P(1.1, -0.1), P(1.1, 0.33), *diag, P(0.17, 0.70),
                                               P(0.17, 0.0)], fill=255))
    front = ImageChops.multiply(body_mask, above)
    holes = mask_of(size, lambda m: m.rounded_rectangle((*P(0.485, 0.055), *P(0.585, 0.42)), radius=mw * 0.03, fill=255))
    front = ImageChops.subtract(front, holes)
    left_btn = ImageChops.multiply(front, mask_of(size, lambda m: m.rectangle((0, 0, split_x, H), fill=255)))
    right_btn = ImageChops.subtract(front, left_btn)
    btn_masks = {
        "left": left_btn, "right": right_btn,
        "middle": mask_of(size, lambda m: m.rounded_rectangle(wheel_box, radius=mw * 0.03, fill=255)),
        "forward": mask_of(size, lambda m: m.rounded_rectangle((*P(0.07, 0.30), *P(0.11, 0.37)), radius=mw * 0.02, fill=255)),
        "back": mask_of(size, lambda m: m.rounded_rectangle((*P(0.07, 0.38), *P(0.11, 0.45)), radius=mw * 0.02, fill=255)),
        "mode": mask_of(size, lambda m: m.rounded_rectangle(b1, radius=mw * 0.015, fill=255)),
        "dpi": mask_of(size, lambda m: m.rounded_rectangle(b2, radius=mw * 0.015, fill=255)),
    }

    # Masques de lumière
    wheel_light = mask_of(size, lambda m: m.rounded_rectangle(wheel_box, radius=mw * 0.03, outline=255,
                                                              width=int(SS * 2.2)))
    wheel_core = mask_of(size, lambda m: [m.line((wheel_box[0] + SS * 3, y, wheel_box[2] - SS * 3, y), fill=120, width=SS)
                                          for y in (wheel_box[1] + (wheel_box[3] - wheel_box[1]) * (i + 0.5) / 9
                                                    for i in range(9))])
    logo_c, logo_r = P(0.57, 0.80), mw * 0.10
    logo = logo_mask(size, logo_c[0], logo_c[1], logo_r)
    engrave(base, logo)
    strip_pts = [p for p in body if p[1] > oy + mh * 0.40]
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
    # (étiquette, largeur en unités) ; None = espace vide. Légendes du DeathStalker V2 Pro français.
    [("echap", 1), (None, 1), ("F1", 1), ("F2", 1), ("F3", 1), ("F4", 1), (None, .5), ("F5", 1), ("F6", 1), ("F7", 1),
     ("F8", 1), (None, .5), ("F9", 1), ("F10", 1), ("F11", 1), ("F12", 1), (None, .25), ("arrêt", 1), ("impr", 1),
     ("pause", 1)],
    [("²", 1), ("&", 1), ("é", 1), ('"', 1), ("'", 1), ("(", 1), ("-", 1), ("è", 1), ("_", 1), ("ç", 1), ("à", 1),
     (")", 1), ("=", 1), ("⟵", 2), (None, .25), ("inser", 1), ("début", 1), ("pg↑", 1), (None, .25), ("ver num", 1),
     ("/", 1), ("*", 1), ("-", 1)],
    [("↹", 1.5), ("A", 1), ("Z", 1), ("E", 1), ("R", 1), ("T", 1), ("Y", 1), ("U", 1), ("I", 1), ("O", 1), ("P", 1),
     ("^", 1), ("$", 1), (None, .25), ("entrée", 1.25), (None, .25), ("suppr", 1), ("fin", 1), ("pg↓", 1), (None, .25),
     ("7", 1), ("8", 1), ("9", 1), ("+", 1)],
    [("⇩", 1.75), ("Q", 1), ("S", 1), ("D", 1), ("F", 1), ("G", 1), ("H", 1), ("J", 1), ("K", 1), ("L", 1), ("M", 1),
     ("ù", 1), ("*", 1), (None, 1.25), (None, .25), (None, 3), (None, .25), ("4", 1), ("5", 1), ("6", 1), (None, 1)],
    [("⇧", 1.25), ("<", 1), ("W", 1), ("X", 1), ("C", 1), ("V", 1), ("B", 1), ("N", 1), (",", 1), (";", 1), (":", 1),
     ("!", 1), ("⇧", 2.75), (None, .25), (None, 1), ("↑", 1), (None, 1), (None, .25), ("1", 1), ("2", 1), ("3", 1),
     ("entrée", 1)],
    [("ctrl", 1.25), ("⊞", 1.25), ("alt", 1.25), ("", 6.25), ("alt", 1.25), ("fn", 1.25), ("☰", 1.25), ("ctrl", 1.25),
     (None, .25), ("<", 1), ("v", 1), (">", 1), (None, .25), ("0", 2), (".", 1), (None, 1)],
]
TALL_KEYS = {(2, 14), (2, 23), (4, 21)}  # entrée (ISO, sur deux rangées), « + » et « entrée » du pavé


def _sc(*codes):
    return [("sc", c) for c in codes]


def _vk(*codes):
    return [("vk", c) for c in codes]


# Un code par touche étiquetée de KEY_ROWS, dans le même ordre
KEY_CODES = [
    _sc(0x01, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x57, 0x58, 0x46) + _vk(0x2C, 0x13),
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
        # légende centrée sur le dessus de la touche (la touche « entrée » ISO : dans sa moitié haute)
        cy = (y0 + min(y1, y0 + u * .9)) / 2 - SS
        ld.text(((x0 + x1) / 2, cy), label, fill=255, font=f, anchor="mm")
        d.text(((x0 + x1) / 2, cy), label, fill=(120, 126, 134, 255), font=f, anchor="mm")
    # Bouton multimédia rond et molette de volume, au-dessus du pavé numérique
    mx = kx0 + (units_w - 4) * u
    top = ky0 + u * .07
    bc = (mx + u * .5, top + u * .42)
    d.ellipse((bc[0] - u * .36, bc[1] - u * .36, bc[0] + u * .36, bc[1] + u * .36), fill=(6, 6, 7, 255),
              outline=(70, 74, 80, 255), width=SS)
    d.ellipse((bc[0] - u * .26, bc[1] - u * .26, bc[0] + u * .26, bc[1] + u * .26), fill=(26, 28, 31, 255))
    roller = (mx + u * 1.05, top + u * .12, mx + u * 3.95, top + u * .72)
    d.rounded_rectangle(roller, radius=u * .28, fill=(8, 9, 10, 255))
    d.rounded_rectangle((roller[0] + u * .25, roller[1] + SS * 2, roller[2] - u * .05, roller[3] - SS * 2),
                        radius=u * .22, fill=(34, 36, 40, 255))
    for i in range(30):
        xx = roller[0] + u * .35 + (roller[2] - roller[0] - u * .5) * (i + .5) / 30
        d.line((xx, roller[1] + SS * 3, xx, roller[3] - SS * 3), fill=(18, 19, 21, 255), width=SS)
    # Voyants d'état au-dessus de la flèche haut
    ledx, ledy = kx0 + 15.25 * u, ky0 + (3 + .35) * u + u * .25
    for i in range(5):
        x = ledx + u * (.45 + i * .5)
        d.ellipse((x - SS * 1.5, ledy - SS * 1.5, x + SS * 1.5, ledy + SS * 1.5), fill=(150, 156, 164, 255))
    # Logo RazerLite gravé sur le bord avant, sous la barre d'espace
    from . import logo
    mark_h = max(6, int(u * .32))
    wm = logo.wordmark(mark_h).getchannel("A")
    wx = int(kx0 + 6.6 * u - wm.size[0] / 2)
    wy = int(oy + kb_h - u * .36 - mark_h / 2)
    engr = Image.new("L", size, 0)
    engr.paste(wm, (wx, wy))
    paint(base, (70, 74, 80), engr)
    d = ImageDraw.Draw(base)

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
    """Kraken V3 HyperSense de trois quarts, d'après photo : coques rondes à grille perforée, disque central
    lumineux avec logo et anneau, bloc de réglage « HYPERSENSE » en bout d'arceau, fourche fine autour de la coque,
    micro amovible à bonnette mousse et câble sous la coque gauche."""
    W, H = w * SS, h * SS
    s = min(W / 300, H / 330) * 0.88
    cx, cy = W / 2 + 4 * s, H / 2 - 4 * s
    size = (W, H)
    base = Image.new("RGBA", size, (0, 0, 0, 0))

    def S(x, y):
        return (cx + x * s, cy + y * s)

    metal_dark = (40, 43, 48, 255)
    cc, cr = (-46, 58), 70                      # coque gauche, ronde, vers nous
    left_box = (*S(cc[0] - cr, cc[1] - cr), *S(cc[0] + cr, cc[1] + cr))
    right_box = (*S(56, -2), *S(132, 112))      # coque droite vue de biais (coussin visible)

    shadow = mask_of(size, lambda d: [d.ellipse((*S(cc[0] - cr + 6, cc[1] - cr + 12), *S(cc[0] + cr + 10, cc[1] + cr + 14)),
                                                fill=200), d.ellipse((*S(60, 10), *S(140, 124)), fill=140)])
    paint(base, (0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(12 * s)))
    d = ImageDraw.Draw(base)

    # Coque droite en retrait : coussin épais vers nous
    d.ellipse(right_box, fill=(20, 21, 24, 255), outline=(50, 54, 60, 255), width=int(2 * s))
    d.ellipse((*S(64, 8), *S(126, 104)), fill=(9, 9, 11, 255))
    d.ellipse((*S(78, 26), *S(114, 86)), fill=(24, 25, 28, 255))
    d.arc((*S(48, -12), *S(140, 120)), start=195, end=345, fill=metal_dark, width=int(5 * s))
    d.rounded_rectangle((*S(80, -50), *S(106, -14)), radius=3 * s, fill=(22, 23, 26, 255))

    # Arceau : bandeau large et plat, coussin dessous
    outer = spline([S(-58, -78), S(-56, -124), S(-18, -156), S(40, -150), S(84, -114), S(96, -52)], closed=False)
    inner = spline([S(-34, -78), S(-32, -110), S(-8, -132), S(36, -128), S(68, -100), S(76, -50)], closed=False)
    band_mask = mask_of(size, lambda m: m.polygon(outer + inner[::-1], fill=255))
    band_img = gradient(size, (40, 43, 48), (16, 17, 20)).convert("RGBA")
    band_img.putalpha(band_mask)
    base.alpha_composite(band_img)
    relief(base, band_mask, 8 * s, 0.8)
    grain(base, band_mask, 6)
    d = ImageDraw.Draw(base)
    d.line(spline([S(-40, -78), S(-38, -112), S(-10, -138), S(37, -134), S(72, -104), S(81, -50)], closed=False),
           fill=(10, 10, 12, 255), width=int(8 * s), joint="curve")
    d.line(outer, fill=(66, 70, 77, 255), width=int(2 * s), joint="curve")

    # Bloc de réglage en bout d'arceau, avec la plaque « HYPERSENSE »
    blk = (*S(-74, -84), *S(-18, -40))
    d.rounded_rectangle(blk, radius=4 * s, fill=(22, 23, 26, 255), outline=(60, 64, 70, 255), width=max(1, int(s)))
    plaque = (*S(-70, -62), *S(-22, -48))
    d.rounded_rectangle(plaque, radius=6 * s, fill=(12, 13, 15, 255), outline=(70, 74, 80, 255), width=max(1, int(s)))
    f = find_font(max(5, int(5.2 * s)), bold=True)
    d.text(((plaque[0] + plaque[2]) / 2 + 5 * s, (plaque[1] + plaque[3]) / 2), "HYPERSENSE", font=f,
           fill=(150, 155, 162, 255), anchor="mm")
    d.ellipse((plaque[0] + 3 * s, plaque[1] + 3.5 * s, plaque[0] + 10 * s, plaque[3] - 3.5 * s), outline=(150, 155, 162, 255),
              width=max(1, int(s)))
    # graduations de taille sous le bloc
    for k, x in enumerate((-54, -46, -38)):
        d.line((S(x, -34), S(x + 5, -34)), fill=(120, 125, 132, 255), width=max(1, int(s)))

    # Fourche fine qui entoure le haut de la coque
    d.arc((*S(cc[0] - cr - 8, cc[1] - cr - 8), *S(cc[0] + cr + 8, cc[1] + cr + 8)), start=180, end=360,
          fill=(26, 28, 31, 255), width=int(7 * s))
    d.arc((*S(cc[0] - cr - 8, cc[1] - cr - 8), *S(cc[0] + cr + 8, cc[1] + cr + 8)), start=180, end=360,
          fill=(70, 74, 80, 255), width=max(1, int(s)))
    d.line((S(-46, -40), S(-46, cc[1] - cr - 8)), fill=(26, 28, 31, 255), width=int(10 * s))

    # Coussin (dépasse derrière la coque)
    d.ellipse((*S(cc[0] - cr + 10, cc[1] - cr - 4), *S(cc[0] + cr + 12, cc[1] + cr + 4)), fill=(10, 10, 12, 255))
    # Coque : bord lisse, grille perforée
    cup_mask = mask_of(size, lambda m: m.ellipse(left_box, fill=255))
    shell = gradient(size, (40, 43, 48), (16, 17, 20)).convert("RGBA")
    shell.putalpha(cup_mask)
    base.alpha_composite(shell)
    relief(base, cup_mask, 12 * s, 0.75)
    grille = mask_of(size, lambda m: m.ellipse((*S(cc[0] - cr + 9, cc[1] - cr + 9), *S(cc[0] + cr - 9, cc[1] + cr - 9)),
                                               fill=255))
    paint(base, (14, 15, 17), grille)
    dots(base, grille, 4.2 * s, 0.9 * s, (52, 55, 60))
    sheen = radial(size, S(cc[0] - 25, cc[1] - 30), (60 * s, 50 * s), 70, 0)
    paint(base, (255, 255, 255), ImageChops.multiply(sheen, cup_mask).point(lambda v: v // 5))
    d = ImageDraw.Draw(base)
    d.ellipse(left_box, outline=(70, 74, 81, 255), width=int(2 * s))
    # Disque central brillant
    dr = 30
    disc = (*S(cc[0] - dr, cc[1] - dr), *S(cc[0] + dr, cc[1] + dr))
    disc_mask = mask_of(size, lambda m: m.ellipse(disc, fill=255))
    disc_img = gradient(size, (30, 32, 36), (8, 8, 10)).convert("RGBA")
    disc_img.putalpha(disc_mask)
    base.alpha_composite(disc_img)
    paint(base, (255, 255, 255), ImageChops.multiply(radial(size, S(cc[0] - 10, cc[1] - 14), (22 * s, 14 * s), 60, 0),
                                                     disc_mask).point(lambda v: v // 3))

    # Micro amovible : prise à l'avant bas, perche souple, bonnette mousse
    boom = spline([S(-96, 104), S(-116, 120), S(-128, 136), S(-132, 150)], closed=False)
    d.line(boom, fill=(14, 15, 17, 255), width=int(6 * s), joint="curve")
    d.ellipse((*S(-102, 98), *S(-90, 110)), fill=(30, 32, 36, 255), outline=(8, 8, 9, 255), width=max(1, int(s)))
    foam = mask_of(size, lambda m: m.ellipse((*S(-146, 140), *S(-120, 164)), fill=255))
    paint(base, (16, 17, 19), foam)
    grain(base, foam, 14)
    # Câble sous la coque
    d.line(spline([S(-40, cc[1] + cr - 2), S(-38, 150), S(-34, 166)], closed=False), fill=(12, 12, 14, 255),
           width=int(5 * s), joint="curve")

    logo = logo_mask(size, S(*cc)[0], S(*cc)[1], 21 * s)
    engrave(base, logo)
    ring = mask_of(size, lambda m: m.ellipse(disc, outline=255, width=int(3 * s)))
    zones = {"Casque": [(logo, 1.0), (logo.filter(ImageFilter.GaussianBlur(6 * s)), 0.8),
                        (ring, 1.0), (ring.filter(ImageFilter.GaussianBlur(6 * s)), 0.8)]}
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
