import sys, json, cv2, numpy as np
sys.path.insert(0, "/home/user/razerlite-windows-")
from razerlite.render import KEY_ROWS, TALL_KEYS
S, OUT = sys.argv[1], sys.argv[2]
img = cv2.imread(f"{S}/photos/keyboard.jpg")
src = np.float32([[297, 452], [3569, 437], [3569, 1444], [297, 1512]])
W, H = 3240, 1030
M = cv2.getPerspectiveTransform(src, np.float32([[0, 0], [W, 0], [W, H], [0, H]]))
rect = cv2.warpPerspective(img, M, (W, H), flags=cv2.INTER_CUBIC)
b, g, r = [c.astype(np.float32) for c in cv2.split(rect)]
# lumière violette : rouge et bleu au-dessus du vert
light = np.clip((np.minimum(r, b) - g - 18) * 3.2, 0, 255).astype(np.uint8)
light = cv2.GaussianBlur(light, (0, 0), 1.2)
gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)
gray = cv2.medianBlur(gray, 3)
lf = light.astype(np.float32) / 255
base = gray.astype(np.float32) * (1 - 0.85 * lf)
base = np.clip(255 * (base / 255) ** 1.7 * 0.95 + 3, 0, 255).astype(np.uint8)  # poussière atténuée
# logo Razer gravé sous la barre d'espace : effacé
p = cv2.perspectiveTransform(np.float32([[[1825, 1418]], [[2055, 1446]]]), M).reshape(-1, 2)
x0, y0 = p.min(0) - [20, 25]; x1, y1 = p.max(0) + [20, 25]
zone = np.zeros_like(gray); zone[int(y0):int(y1), int(x0):int(x1)] = 255
base = cv2.inpaint(base, zone, 7, cv2.INPAINT_TELEA)
light[zone > 0] = 0
rgb = cv2.merge([np.clip(base * 1.04, 0, 255).astype(np.uint8), base, np.clip(base * 0.97, 0, 255).astype(np.uint8)])
alpha = np.zeros_like(gray)
cv2.rectangle(alpha, (0, 0), (W - 1, H - 1), 255, -1)
rad = 40
for cx, cy in ((rad, rad), (W - rad, rad), (rad, H - rad), (W - rad, H - rad)):
    alpha[min(cy, H - cy) - rad if False else 0:0, :] = alpha[0:0, :]
corner = np.zeros_like(gray); cv2.rectangle(corner, (0, 0), (W, H), 255, -1)
mask = np.zeros_like(gray)
cv2.rectangle(mask, (rad, 0), (W - rad, H), 255, -1); cv2.rectangle(mask, (0, rad), (W, H - rad), 255, -1)
for cx, cy in ((rad, rad), (W - rad - 1, rad), (rad, H - rad - 1), (W - rad - 1, H - rad - 1)):
    cv2.circle(mask, (cx, cy), rad, 255, -1)
# touches : même grille que le rendu dessiné, calée sur la photo
u, inset = 143.0, 9
row_y = [50, 220, 365, 510, 655, 800]
keys = []
for ri, row in enumerate(KEY_ROWS):
    x = 0.0
    for ci, (label, width) in enumerate(row):
        if label is not None:
            tall = (ri, ci) in TALL_KEYS
            y_bot = row_y[ri + 1] + u - inset if tall else row_y[ri] + u - inset
            keys.append([x * u + inset, row_y[ri] + inset * .3, (x + width) * u - inset, y_bot - inset])
        x += width
k = 1600 / W
size = (1600, round(H * k))
def rs(a): return cv2.resize(a, size, interpolation=cv2.INTER_AREA)
cv2.imwrite(f"{OUT}/keyboard.png", cv2.merge([*cv2.split(rs(rgb)), rs(mask)]))
cv2.imwrite(f"{OUT}/keyboard_light.png", rs(light))
json.dump({"size": list(size), "keys": [[round(v * k, 1) for v in kk] for kk in keys],
           "logo": [round((x0 + x1) / 2 * k), round((y0 + y1) / 2 * k), round((y1 - y0) * k * 0.55)]},
          open(f"{OUT}/keyboard.json", "w"))
vis = rect.copy()
for x0_, y0_, x1_, y1_ in keys: cv2.rectangle(vis, (int(x0_), int(y0_)), (int(x1_), int(y1_)), (0, 255, 0), 3)
cv2.imwrite(f"{S}/proc/kb_keys.jpg", cv2.resize(vis, None, fx=0.4, fy=0.4))
print(len(keys), size)
