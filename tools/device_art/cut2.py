import sys, json, cv2, numpy as np
src, out, poly_json, band = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
img = cv2.imread(src)
poly = np.array(json.loads(poly_json), np.int32)
x0, y0 = poly.min(0) - band - 20; x1, y1 = poly.max(0) + band + 20
x0, y0 = max(0, x0), max(0, y0)
crop = img[y0:y1, x0:x1].copy()
poly = poly - [x0, y0]
P = np.zeros(crop.shape[:2], np.uint8); cv2.fillPoly(P, [poly], 255)
k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*band+1, 2*band+1))
fg = cv2.erode(P, k); bgz = cv2.dilate(P, k)
mask = np.full(P.shape, cv2.GC_BGD, np.uint8)
mask[bgz > 0] = cv2.GC_PR_BGD; mask[P > 0] = cv2.GC_PR_FGD; mask[fg > 0] = cv2.GC_FGD
sc = 0.5
sm = cv2.resize(crop, None, fx=sc, fy=sc); mm = cv2.resize(mask, (sm.shape[1], sm.shape[0]), interpolation=cv2.INTER_NEAREST)
cv2.grabCut(sm, mm, None, np.zeros((1,65)), np.zeros((1,65)), 6, cv2.GC_INIT_WITH_MASK)
m = np.where((mm==1)|(mm==3), 255, 0).astype(np.uint8)
m = cv2.resize(m, (crop.shape[1], crop.shape[0]))
m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9,9)))
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25,25)))
# garder la plus grande composante
n, lab, st, _ = cv2.connectedComponentsWithStats(m)
if n > 1:
    big = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]); m = np.where(lab == big, 255, 0).astype(np.uint8)
m = cv2.GaussianBlur(m, (5,5), 0)
cv2.imwrite(out, crop); cv2.imwrite(out.replace('.png','_mask.png'), m)
vis = crop.copy(); vis = (vis * (m[..., None] / 255.0) + 255 * (1 - m[..., None] / 255.0)).astype(np.uint8)
cv2.polylines(vis, [poly], True, (0,0,255), 3)
cv2.imwrite(out.replace('.png','_vis.jpg'), cv2.resize(vis, None, fx=0.35, fy=0.35))
print(x0, y0, crop.shape)
