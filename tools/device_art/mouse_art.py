import sys, json, cv2, numpy as np
S = sys.argv[1]; OUT = sys.argv[2]
crop = cv2.imread(f"{S}/proc/mouse.png"); m = cv2.imread(f"{S}/proc/mouse_mask.png", 0)
m[:95, :] = 0
# contour lissé (le grip pointillé donne un bord dentelé)
m = cv2.GaussianBlur(m, (0, 0), 9); m = np.where(m > 127, 255, 0).astype(np.uint8); m = cv2.GaussianBlur(m, (0, 0), 1.5)
b, g, r = [c.astype(np.float32) for c in cv2.split(crop)]
# lumière verte : vert nettement au-dessus du rouge et du bleu
light = np.clip((g - np.maximum(r, b) - 12) * 4, 0, 255).astype(np.uint8)
light = cv2.bitwise_and(light, m)
# Logo Razer : zone verte autour du centre du logo
lc, lr = (543, 1314), 150
logo_zone = np.zeros_like(m); cv2.circle(logo_zone, lc, lr, 255, -1)
logo_px = cv2.dilate(cv2.bitwise_and((light > 20).astype(np.uint8) * 255, logo_zone), np.ones((15, 15), np.uint8))
# base : nettoyage léger, logo effacé, reflets verts neutralisés
gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
gray = cv2.bilateralFilter(gray, 7, 18, 7)
base = cv2.inpaint(gray, logo_px, 9, cv2.INPAINT_TELEA)
# la lumière (molette, reflets) : on assombrit ce qui était éclairé
lf = cv2.GaussianBlur(light, (0, 0), 3).astype(np.float32) / 255
lf[logo_zone > 0] = 0
base = (base.astype(np.float32) * (1 - 0.75 * lf)).astype(np.uint8)
base = np.clip(255 * (base / 255.0) ** 1.35 * 0.85 + 2, 0, 255).astype(np.uint8)
# teinte froide légère (plastique noir)
rgb = cv2.merge([np.clip(base * 1.04, 0, 255).astype(np.uint8), base, np.clip(base * 0.97, 0, 255).astype(np.uint8)])
# zones
wheel = np.zeros_like(m); wheel_box = (471, 300, 600, 590)
wheel[wheel_box[1]:wheel_box[3], wheel_box[0]:wheel_box[2]] = light[wheel_box[1]:wheel_box[3], wheel_box[0]:wheel_box[2]]
# mise à l'échelle finale
H = 720
k = H / crop.shape[0]
def rs(a, inter=cv2.INTER_AREA): return cv2.resize(a, (round(crop.shape[1] * k), H), interpolation=inter)
rgba = cv2.merge([*cv2.split(rs(rgb)), rs(m)])
cv2.imwrite(f"{OUT}/mouse.png", rgba)
cv2.imwrite(f"{OUT}/mouse_wheel.png", rs(cv2.bitwise_and(wheel, m)))
def poly(pts): return [[round(x * k), round(y * k)] for x, y in pts]
meta = {
    "size": [round(crop.shape[1] * k), H],
    "logo": [round(lc[0] * k), round(lc[1] * k), round(115 * k)],
    "buttons": {
        "left": poly([[200, 150], [470, 100], [470, 600], [500, 840], [214, 986], [170, 700]]),
        "right": poly([[600, 95], [780, 130], [860, 330], [857, 586], [590, 760], [600, 590]]),
        "middle": poly([[480, 305], [590, 305], [590, 585], [480, 585]]),
        "mode": poly([[500, 623], [586, 623], [586, 700], [500, 700]]),
        "dpi": poly([[509, 729], [586, 729], [586, 814], [509, 814]]),
    },
}
json.dump(meta, open(f"{OUT}/mouse.json", "w"), indent=1)
print(meta["size"])
