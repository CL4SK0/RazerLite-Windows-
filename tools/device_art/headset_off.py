import sys, json, cv2, numpy as np
S, OUT = sys.argv[1], sys.argv[2]
img = cv2.imread(f"{S}/photos/headset_off.png", cv2.IMREAD_UNCHANGED)
bgr, a = img[..., :3].copy(), img[..., 3]
b, g, r = [c.astype(np.float32) for c in cv2.split(bgr)]
# fond blanc : tout ce qui n'est pas quasi blanc, plus grande pièce, trous bouchés
solid = ((np.minimum(np.minimum(r, g), b) < 225) & (a > 0)).astype(np.uint8) * 255
n, lab, st, _ = cv2.connectedComponentsWithStats(solid)
keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 300]
m = np.isin(lab, keep).astype(np.uint8) * 255
ff = m.copy(); hh, ww = m.shape; cv2.floodFill(ff, np.zeros((hh + 2, ww + 2), np.uint8), (0, 0), 255)
m = m | cv2.bitwise_not(ff)
m = cv2.GaussianBlur(m, (0, 0), 1.2); m = np.where(m > 127, 255, 0).astype(np.uint8); m = cv2.GaussianBlur(m, (0, 0), 0.6)
a = cv2.min(a, m)
# l'image officielle fond l'arceau et le câble dans le blanc : on les fond dans la transparence
fade = np.clip((235 - np.minimum(np.minimum(r, g), b)) / 90, 0, 1)
a = (a.astype(np.float32) * fade).astype(np.uint8)
green = np.clip((g - np.maximum(r, b) - 12) * 3, 0, 255).astype(np.uint8)
green[a < 200] = 0
ys, xs = np.nonzero(green > 120); lc = (int(np.median(xs)), int(np.median(ys)))
# le serpent : vert très lumineux au centre du disque ; l'anneau lumineux autour reste
v = np.maximum(np.maximum(r, g), b)
core = np.zeros_like(a); cv2.circle(core, lc, 30, 255, -1)
snake = cv2.dilate((((green > 60) & (v > 120)) & (core > 0)).astype(np.uint8) * 255, np.ones((5, 5), np.uint8))
zone = snake.copy()
clean = cv2.inpaint(bgr, zone, 5, cv2.INPAINT_TELEA)
clean[2:48, 322:372] = clean[60:61, 322:372]  # lettres « RA » du logo Razer sur l'arceau : recouvertes
ring = green.copy(); ring[snake > 0] = 0
gray = cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
lf = cv2.GaussianBlur(ring, (0, 0), 1.5).astype(np.float32) / 255
gray = np.minimum(gray.astype(np.float32) * (1 - 0.7 * lf), 110).astype(np.uint8)
clean = cv2.merge([np.clip(gray * 1.04, 0, 255).astype(np.uint8), gray, np.clip(gray * 0.97, 0, 255).astype(np.uint8)])
cv2.imwrite(f"{OUT}/headset.png", cv2.merge([*cv2.split(clean), a]))
cv2.imwrite(f"{OUT}/headset_light.png", ring)
h, w = a.shape
json.dump({"size": [w, h], "logo": [lc[0], lc[1], 22]}, open(f"{OUT}/headset.json", "w"))
print(lc)
