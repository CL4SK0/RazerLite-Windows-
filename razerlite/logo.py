"""Logo RazerLite : les trois serpents de Razer, redessinés en version « lite ».

Le symbole est un PNG (assets/mark.png, exporté depuis le SVG assets/mark.svg).
Le texte utilise Michroma (pour « RAZER ») et Exo 2 ExtraLight (pour « lite »), polices libres (OFL).
"""

import os

from PIL import Image, ImageDraw, ImageFont

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
GREEN_LIGHT = (125, 255, 90)
WHITE = (233, 238, 243)

_mark_cache = None


def _mark_source():
    global _mark_cache
    if _mark_cache is None:
        _mark_cache = Image.open(os.path.join(ASSETS, "mark.png")).convert("RGBA")
    return _mark_cache


def mark(size=256, glow=True):
    """Le symbole seul, en RGBA carré (le halo est inclus dans le PNG)."""
    return _mark_source().resize((size, size), Image.LANCZOS)


def _font(name, size):
    try:
        return ImageFont.truetype(os.path.join(ASSETS, name), size)
    except OSError:
        return ImageFont.load_default()


def wordmark(height=40):
    """Symbole + « RAZER » (Michroma) + « lite » (Exo 2 ExtraLight, vert)."""
    S = 4
    H = height * S
    sym = mark(H)
    bold = _font("Michroma-Regular.ttf", int(H * 0.40))
    light = _font("Exo2-ExtraLight.ttf", int(H * 0.56))
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    w1 = tmp.textlength("RAZER", font=bold)
    w2 = tmp.textlength("lite", font=light)
    gap, inner = H * 0.22, H * 0.10
    W = int(H + gap + w1 + inner + w2 + H * 0.08)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(sym, (0, 0))
    d = ImageDraw.Draw(out)
    mid = H * 0.53
    d.text((H + gap, mid), "RAZER", font=bold, fill=WHITE + (255,), anchor="lm")
    d.text((H + gap + w1 + inner, mid - H * 0.03), "lite", font=light, fill=GREEN_LIGHT + (255,), anchor="lm")
    return out.resize((W // S, height), Image.LANCZOS)


def app_icon(size=256):
    """Icône d'application : symbole sur pastille sombre arrondie."""
    S = size * 4
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((S * .03, S * .03, S * .97, S * .97), radius=S * .24, fill=(16, 19, 23, 255),
                        outline=(40, 46, 54, 255), width=int(S * .015))
    sym = mark(int(S * .86))
    out.alpha_composite(sym, (int(S * .07), int(S * .07)))
    return out.resize((size, size), Image.LANCZOS)


def small_icon(size):
    """Petites tailles (barre des tâches, titre) : le symbole seul, agrandi au maximum pour rester lisible."""
    src = _mark_source()
    sym = src.crop(src.getbbox())
    S = size * 4
    sym.thumbnail((S, S), Image.LANCZOS)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.alpha_composite(sym, ((S - sym.width) // 2, (S - sym.height) // 2))
    return out.resize((size, size), Image.LANCZOS)


ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def save_ico(path):
    # Images au format BMP (et non PNG) : l'Explorateur et la barre des tâches les affichent partout.
    frames = [small_icon(s) if s <= 32 else app_icon(s) for s in ICO_SIZES]
    frames[-1].save(path, sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1], bitmap_format="bmp")


def ico_path():
    """Icône .ico livrée avec le programme (créée à la volée si elle manque)."""
    path = os.path.join(ASSETS, "RazerLite.ico")
    if not os.path.exists(path):
        try:
            save_ico(path)
        except OSError:
            return None
    return path
