"""Clavier : image produit officielle (QWERTY US) convertie en ISO AZERTY.

Entrée en L, touche « * µ » ajoutée, Maj gauche raccourcie + touche « < > », toutes les légendes
réécrites en français (sauf F1–F12, fn, Windows, menu, flèches, / * - + du pavé, identiques).
"""
import os, sys, json, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from razerlite.render import KEY_ROWS, TALL_KEYS
S, OUT, FONT = sys.argv[1], sys.argv[2], sys.argv[3]
img = cv2.imread(f"{S}/photos/keyboard_off.png")
X0, U, GAP, CAP = 35.0, 85.65, 9, 78
ROW_Y = [723, 827, 915, 1001, 1088, 1175]
ux = lambda a: int(round(X0 + a * U))

# --- 1. légendes US effacées, puis géométrie ISO ----------------------------------------
def rects(rows, tall=(), wide=None):
    out = []
    for ri, row in enumerate(rows):
        x = 0.0
        for ci, (label, width) in enumerate(row):
            if label is not None:
                a = FN_X.get(ci, x) if ri == 0 else x
                bottom = ROW_Y[ri + 1] + CAP if (ri, ci) in tall else ROW_Y[ri] + CAP
                left_x = ux(wide[1]) if wide and (ri, ci) == wide[0] else ux(a)
                out.append([left_x, ROW_Y[ri], ux(a + width) - GAP, bottom])
            x += width
    return out

FN_X = {0: 0, 2: 2, 3: 3, 4: 4, 5: 5, 7: 6.5, 8: 7.5, 9: 8.5, 10: 9.5, 12: 11.18, 13: 12.18, 14: 13.18, 15: 14.18}
ANSI = [list(r) for r in KEY_ROWS]
ANSI[2] = ANSI[2][:13] + [("\\", 1.5)] + ANSI[2][15:]
ANSI[3] = ANSI[3][:12] + [("enter", 2.25)] + ANSI[3][14:]
ANSI[4] = [("shift", 2.25)] + ANSI[4][2:]
ANSI_TALL = {(2, 22), (4, 20)}

# --- 2. touches ISO (rectangles) ------------------------------------------------------
keys = rects(KEY_ROWS, TALL_KEYS, ((2, 14), 13.5))

# --- 3. légendes françaises --------------------------------------------------------------
K = "keep"
LEG = [
    ("echap",), K, K, K, K, K, K, K, K, K, K, K, K, ("arrêt", "défil"), ("impr", "écran syst"), ("pause", "☾"),
    ("²",), ("&", "1"), ("é", "2  ~"), ('"', "3  #"), ("'", "4  {"), ("(", "5  ["), ("-", "6  |"), ("è", "7  `"),
    ("_", "8  \\"), ("ç", "9  ^"), ("à", "0  @"), (")", "°  ]"), ("=", "+  }"), ("⟵",), ("inser",), ("↖",), ("⇞",),
    ("ver", "num"), K, K, K,
    ("↹",), ("A",), ("Z",), ("E", "€"), ("R",), ("T",), ("Y",), ("U",), ("I",), ("O",), ("P",), ("^", "¨"),
    ("$", "£  ¤"), ("entrée",), ("suppr",), ("fin",), ("⇟",), ("7", "↖"), ("8", "↑"), ("9", "⇞"), K,
    ("⇩",), ("Q",), ("S",), ("D",), ("F",), ("G",), ("H",), ("J",), ("K",), ("L",), ("M",), ("ù", "%"), ("*", "µ"),
    ("4", "←"), ("5",), ("6", "→"),
    ("⇧",), ("<  >",), ("W",), ("X",), ("C",), ("V",), ("B",), ("N",), (",", "?"), (";", "."), (":", "/"),
    ("!", "§"), ("⇧",), K, ("1", "fin"), ("2", "↓"), ("3", "⇟"), ("entrée",),
    ("ctrl",), K, ("alt",), K, ("alt gr",), K, K, ("ctrl",), K, K, K, ("0", "inser"), (".", "suppr"),
]
assert len(LEG) == len(keys), (len(LEG), len(keys))

# légende = trait fin et clair sur la face de la touche (le haut-de-forme le repère sans toucher aux reflets)
v = img.max(2)
hat = cv2.morphologyEx(v, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
erase = np.zeros(v.shape, np.uint8)
keep = {tuple(r) for r, leg in zip(keys, LEG) if leg == K}
for x0, y0, x1, y1 in rects(ANSI, ANSI_TALL):
    if (x1 - x0) > 5 * U or (x0, y0, x1, y1) in keep:  # barre d'espace : rien à effacer
        continue
    fy0, fy1, fx0, fx1 = y0 + 9, (y1 if y1 - y0 > CAP * 1.5 else y0 + CAP) - 12, x0 + 11, x1 - 9
    erase[fy0:fy1, fx0:fx1] = np.where(hat[fy0:fy1, fx0:fx1] > 13, 255, 0)
erase = cv2.dilate(erase, np.ones((5, 5), np.uint8))
img = cv2.inpaint(img, erase, 3, cv2.INPAINT_TELEA)
src = img.copy()

def stretch(tile, width, m=26):
    """Agrandit ou rétrécit une touche en largeur sans déformer ses bords (découpe en 3)."""
    mid = cv2.resize(tile[:, m:-m], (width - 2 * m, tile.shape[0]), interpolation=cv2.INTER_AREA)
    return np.concatenate([tile[:, :m], mid, tile[:, -m:]], axis=1)

def put(tile, x, y, mask=None):
    h, w = tile.shape[:2]
    if mask is None:
        img[y:y + h, x:x + w] = tile
    else:
        a = mask[..., None]
        img[y:y + h, x:x + w] = (tile * a + img[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)

M = 5  # marge autour du capuchon (halo de lumière)
def tile_at(a0, a1, r0, r1=None, x0=None):
    r1 = r0 if r1 is None else r1
    xs = ux(a0) if x0 is None else x0
    return src[ROW_Y[r0] - M:ROW_Y[r1] + CAP + M, xs - M:ux(a1) - GAP + M].copy()

# rangée 3 : « * µ » (copie de « ' » à 11,75 u) ; le reste devient le bas de l'entrée ISO
put(tile_at(11.75, 12.75, 3), ux(12.75) - M, ROW_Y[3] - M)
# entrée ISO : partie haute = touche « \ » (1,5 u) ; tige = entrée du pavé numérique élargie à 1,25 u
upper = tile_at(13.5, 15, 2)
stem = stretch(tile_at(21.5, 22.5, 4, 5), ux(15) - ux(13.75) - GAP + 2 * M)
stem = stem[:ROW_Y[3] - ROW_Y[2] + CAP + 2 * M]  # même hauteur que deux rangées du bloc principal
put(stem, ux(13.75) - M, ROW_Y[2] - M)
h, w = upper.shape[:2]
mk = np.zeros((h, w), np.float32)
mk[:M + int(CAP * 0.55)] = 1                             # haut de la touche
mk[:, :ux(13.75) - ux(13.5) + 24] = 1                    # avancée gauche, avec le coin intérieur du L
mk = cv2.GaussianBlur(mk, (0, 0), 3)
put(upper, ux(13.5) - M, ROW_Y[2] - M, mk)
# rangée 4 : Maj 2,25 u -> Maj 1,25 u + « < > » (copie de « Z »)
shift = tile_at(0, 2.25, 4)
put(stretch(shift, ux(1.25) - GAP - ux(0) + 2 * M), ux(0) - M, ROW_Y[4] - M)
put(tile_at(2.25, 3.25, 4), ux(1.25) - M, ROW_Y[4] - M)
# logo « RAZER » du bas : effacé (le logo RazerLite est dessiné à sa place par l'appli)
zone = np.zeros(img.shape[:2], np.uint8); zone[1270:1300, 925:1065] = 255
img = cv2.inpaint(img, zone, 6, cv2.INPAINT_TELEA)


b, g, r = [c.astype(np.float32) for c in cv2.split(img)]
v = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
light = np.clip(np.maximum((v - mn) * 1.5, (v - 110) * 1.3), 0, 255)
lab_src = np.zeros(img.shape[:2], np.uint8)
for i, (x0, y0, x1, y1) in enumerate(keys):
    lab_src[y0:y1, x0:x1] = i + 1
dist, near = cv2.distanceTransformWithLabels((lab_src == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
seed = np.zeros(near.max() + 1, np.uint8)
seed[near[lab_src > 0]] = lab_src[lab_src > 0]
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
lf = cv2.GaussianBlur(light, (0, 0), 1.0) / 255
base = np.clip(gray * (1 - 0.88 * lf), 0, 255)
# faces des touches lissées : plus de taches là où les anciennes légendes ont été effacées
face = np.zeros(base.shape, np.float32)
for (x0, y0, x1, y1), leg in zip(keys, LEG):
    if leg != K and (x1 - x0) < 5 * U:
        face[y0 + 10:(y1 if y1 - y0 > CAP * 1.5 else y0 + CAP) - 13, x0 + 12:x1 - 10] = 1
face = cv2.GaussianBlur(face, (0, 0), 2.5)
base = base * (1 - face) + cv2.GaussianBlur(base, (0, 0), 7) * face
# plaque autour des touches : le reflet de l'éclairage d'origine est ramené au noir mat (sans touches éteintes grises)
plate = np.clip((dist - 6) / 10, 0, 1) * np.clip((80 - dist) / 20, 0, 1)
plate[ROW_Y[3] - 4:ROW_Y[4] - 4, ux(15.25):ux(18.25)] = 0  # voyants C 1 S M G
base = base * (1 - plate) + np.minimum(base, 40) * plate

light *= np.clip((50 - dist) / 25, 0, 1)  # la lumière s'éteint loin des touches

# nouvelles légendes : masque de lumière (blanc) + trace sombre sur la base
font_main = ImageFont.truetype(FONT, 27); font_main.set_variation_by_name("Medium")
font_word = ImageFont.truetype(FONT, 17); font_word.set_variation_by_name("Medium")
font_sub = ImageFont.truetype(FONT, 15); font_sub.set_variation_by_name("Medium")
sym = lambda size: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
SYMBOLS = set("☾↹⇩⇧⟵↖⇞⇟←→↑↓")
leg_img = Image.new("L", (img.shape[1], img.shape[0]), 0)
d = ImageDraw.Draw(leg_img)
def text(xy, s, f, fs):
    if any(c in SYMBOLS for c in s):
        f = sym(fs)
    d.text(xy, s, font=f, fill=255, anchor="mm")
for (x0, y0, x1, y1), leg in zip(keys, LEG):
    if leg == K:
        continue
    cx = (x0 + x1) / 2
    main = leg[0]
    word = len(main) > 2 and not any(c in SYMBOLS for c in main)
    if len(leg) == 1:
        text((cx, y0 + 26), main, font_word if word else font_main, 18 if word else 26)
    else:
        text((cx, y0 + (20 if word else 22)), main, font_word if word else font_main, 18 if word else 24)
        text((cx, y0 + (40 if word else 50)), leg[1], font_sub, 15)
leg = np.array(leg_img).astype(np.float32)
light = np.maximum(light, leg)
base = np.where(leg > 0, np.maximum(base, leg / 255 * 85), base)
base = np.clip(base, 0, 255).astype(np.uint8)

# --- 4. détourage, échelle ---------------------------------------------------------------
solid = (mn < 232).astype(np.uint8) * 255
n, lab, st, _ = cv2.connectedComponentsWithStats(solid)
big = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]); m = np.where(lab == big, 255, 0).astype(np.uint8)
ff = m.copy(); hh, ww = m.shape; cv2.floodFill(ff, np.zeros((hh + 2, ww + 2), np.uint8), (0, 0), 255)
m = m | cv2.bitwise_not(ff)
ys, xs = np.nonzero(m); bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
rgb = cv2.merge([np.clip(base * 1.04, 0, 255).astype(np.uint8), base, np.clip(base * 0.97, 0, 255).astype(np.uint8)])
crop = lambda a: a[by0:by1, bx0:bx1]
k = 1600 / (bx1 - bx0); size = (1600, round((by1 - by0) * k))
rs = lambda a: cv2.resize(a, size, interpolation=cv2.INTER_AREA)
cv2.imwrite(f"{OUT}/keyboard.png", cv2.merge([*cv2.split(rs(crop(rgb))), rs(crop(m))]))
labels = np.where((dist < 60) & (m > 0), seed[near], 0).astype(np.uint8)
cv2.imwrite(f"{OUT}/keyboard_labels.png", cv2.resize(crop(labels), size, interpolation=cv2.INTER_NEAREST))
cv2.imwrite(f"{OUT}/keyboard_light.png", rs(crop(np.clip(light, 0, 255).astype(np.uint8))))
json.dump({"size": list(size),
           "keys": [[round((x0 - bx0) * k, 1), round((y0 - by0) * k, 1), round((x1 - bx0) * k, 1), round((y1 - by0) * k, 1)]
                    for x0, y0, x1, y1 in keys],
           "logo": [round((995 - bx0) * k), round((1285 - by0) * k), round(12 * k)]},
          open(f"{OUT}/keyboard.json", "w"))
vis = cv2.cvtColor(crop(rgb), cv2.COLOR_BGR2RGB)
cv2.imwrite(f"{S}/proc/kb_off_base.png", crop(rgb))
print(size)
