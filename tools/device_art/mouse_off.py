import sys, json, cv2, numpy as np
S, OUT = sys.argv[1], sys.argv[2]
img = cv2.imread(f"{S}/photos/mouse_off.png")
b, g, r = [c.astype(np.float32) for c in cv2.split(img)]
v = np.maximum(np.maximum(r, g), b)
dark = (v < 125).astype(np.uint8) * 255
n, lab, st, _ = cv2.connectedComponentsWithStats(dark)
big = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]); m = np.where(lab == big, 255, 0).astype(np.uint8)
# boucher les trous (molette et logo éclairés)
ff = m.copy(); h, w = m.shape; cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 255)
m = m | cv2.bitwise_not(ff)
m = cv2.GaussianBlur(m, (0, 0), 2.5); m = np.where(m > 127, 255, 0).astype(np.uint8); m = cv2.GaussianBlur(m, (0, 0), 0.8)
green = np.clip((g - np.maximum(r, b) - 20) * 3, 0, 255).astype(np.uint8)
green = cv2.bitwise_and(green, cv2.erode(m, np.ones((5, 5), np.uint8)))
ys, xs = np.nonzero(green[600:] > 60); lc = (int(xs.mean()), int(ys.mean()) + 600)
logo_zone = np.zeros_like(m); cv2.circle(logo_zone, lc, 95, 255, -1)
logo_px = cv2.dilate(((green > 25) & (logo_zone > 0)).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
clean = cv2.inpaint(img, logo_px, 7, cv2.INPAINT_TELEA)
wheel = green.copy(); wheel[logo_zone > 0] = 0
# la molette éteinte : on enlève la teinte verte
gray = cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
wf = cv2.GaussianBlur(wheel, (0, 0), 2).astype(np.float32)[..., None] / 255
neutral = cv2.merge([gray, gray, gray]).astype(np.float32) * 0.45
clean = (clean.astype(np.float32) * (1 - wf) + neutral * wf).astype(np.uint8)
# l'appareil est noir : toute couleur vient de ses lumières (reflets du halo arc-en-ciel sur les bords, logo effacé)
gray = cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
clean = cv2.merge([np.clip(gray * 1.04, 0, 255).astype(np.uint8), gray, np.clip(gray * 0.97, 0, 255).astype(np.uint8)])
cv2.imwrite(f"{OUT}/mouse.png", cv2.merge([*cv2.split(clean), m]))
cv2.imwrite(f"{OUT}/mouse_wheel.png", wheel)
ys, xs = np.nonzero(m)
print("bbox", xs.min(), ys.min(), xs.max(), ys.max(), "logo", lc)
json.dump({"size": [w, h], "logo": [lc[0], lc[1], 62], "buttons": {
    "left": [[180, 150], [360, 45], [365, 490], [230, 555], [180, 300]],
    "right": [[440, 10], [590, 95], [615, 320], [445, 480], [440, 60]],
    "middle": [[368, 155], [432, 155], [432, 330], [368, 330]],
    "mode": [[378, 350], [428, 350], [428, 405], [378, 405]],
    "dpi": [[378, 412], [428, 412], [428, 468], [378, 468]]}}, open(f"{OUT}/mouse.json", "w"))
