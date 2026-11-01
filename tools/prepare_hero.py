"""Builds the hero assets from one portrait photo.

    python tools/prepare_hero.py [tools/source-portrait.jpg]

Writes to assets/hero/:
  face.webp      the portrait cut out from its background (RGBA, 1186x1600), framed like the reference:
                 face about 36% of the width, eyes about 41% down, shirt running off the bottom
  depth.webp     a smooth relief (white = near) that the vertex shader pushes the portrait plane with
  machine.webp   the "machine view": the same head as dark brushed metal with the face-mesh wireframe,
                 lens eyes and a speaker grille for a mouth (RGBA, cut off 89.6% of the way down like the reference)
  hero-data.js   const MESH = { pts: [[x, y] x 478], hairTop }  (MediaPipe face mesh, as fractions of the image)

Needs: pillow numpy scipy mediapipe (1.x, Tasks API; the face_landmarker.task model is fetched to tools/models on first run) rembg onnxruntime opencv-python-headless
Swap the source photo for a sharper one (front-on, even light, plain background) and run again.
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
from scipy.interpolate import griddata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'source-portrait.jpg')
OUT = os.path.join(ROOT, 'assets', 'hero')
os.makedirs(OUT, exist_ok=True)
W, H = 1186, 1600            # same canvas as the reference, so every framing constant in index.html holds
FACE_W, EYES_Y = 0.355, 0.414  # reference: face width (cheek to cheek) over image width, eye line down the image


MODEL = os.path.join(HERE, 'models', 'face_landmarker.task')
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'


def landmarks(rgb):
    """478 face-mesh points (x, y in pixels, z) for an RGB uint8 image, or None. MediaPipe Tasks API."""
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    if not os.path.exists(MODEL):
        import urllib.request
        os.makedirs(os.path.dirname(MODEL), exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    h, w = rgb.shape[:2]
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=MODEL), num_faces=1, min_face_detection_confidence=0.3, output_face_blendshapes=False)
    with vision.FaceLandmarker.create_from_options(opts) as fl:
        res = fl.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    if not res.face_landmarks:
        return None
    lm = res.face_landmarks[0]
    return np.array([[p.x * w, p.y * h, p.z * w] for p in lm], dtype=np.float64)


def connections(name):
    from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections as C
    return [(c.start, c.end) for c in getattr(C, name)]


def main():
    src = Image.open(SRC).convert('RGB')
    sw, sh = src.size
    print('source', src.size)

    # 1. Find the face in the full photo and frame the crop like the reference.
    lm = landmarks(np.array(src))
    if lm is None:
        sys.exit('No face found in ' + SRC)
    face_w = lm[454, 0] - lm[234, 0]
    eyes = (lm[468, :2] + lm[473, :2]) / 2
    crop_w = face_w / FACE_W
    crop_h = crop_w * H / W
    left = eyes[0] - crop_w / 2
    top = eyes[1] - crop_h * EYES_Y
    # Keep inside the photo (pad with edge pixels if the crop runs past the bottom).
    left = min(max(0, left), sw - crop_w)
    box = (int(round(left)), int(round(top)), int(round(left + crop_w)), int(round(top + crop_h)))
    print('crop', box, 'scale x%.2f' % (W / crop_w))
    pad = max(0, box[3] - sh, -box[1])
    if pad:
        padded = Image.new('RGB', (sw, sh + 2 * pad))
        padded.paste(src, (0, pad))
        # stretch the edge rows instead of leaving black
        padded.paste(src.crop((0, 0, sw, 1)).resize((sw, pad)), (0, 0))
        padded.paste(src.crop((0, sh - 1, sw, sh)).resize((sw, pad)), (0, sh + pad))
        src = padded
        box = (box[0], box[1] + pad, box[2], box[3] + pad)
    crop = src.crop(box).resize((W, H), Image.LANCZOS)
    crop = crop.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2))  # the upscale softens it a little

    # 2. Cut the figure from its background.
    from rembg import remove, new_session
    session = new_session('isnet-general-use')
    cut = remove(crop, session=session, alpha_matting=True, alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=10, alpha_matting_erode_size=8)
    cut = cut.convert('RGBA')
    rgba = np.array(cut).astype(np.float64)
    a = rgba[:, :, 3] / 255.0
    # The figure should run off the bottom edge (shirt), never be cut by the mask there: fill the mask below the chest.
    a = ndimage.gaussian_filter(a, 0.8)
    a[a < 0.03] = 0
    cols = np.where(a.max(axis=0) > 0.5)[0]
    rows = np.where(a.max(axis=1) > 0.5)[0]
    hair_top = rows.min() / H
    print('silhouette cols %d..%d rows %d..%d  hairTop %.3f' % (cols.min(), cols.max(), rows.min(), rows.max(), hair_top))
    rgba[:, :, 3] = a * 255
    # Premultiplied-looking edges: pull the colour in from inside the figure so the fringe isn't background-coloured.
    rgb = rgba[:, :, :3]
    for _ in range(2):
        for c in range(3):
            blurred = ndimage.gaussian_filter(rgb[:, :, c] * a, 3) / np.maximum(ndimage.gaussian_filter(a, 3), 1e-3)
            rgb[:, :, c] = np.where(a < 0.9, blurred, rgb[:, :, c])
    face = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')
    face.save(os.path.join(OUT, 'face.webp'), quality=92, method=6)

    # 3. Face mesh on the framed portrait.
    lm = landmarks(np.array(crop))
    if lm is None:
        sys.exit('No face found after cropping')
    pts = [[round(float(x) / W, 5), round(float(y) / H, 5)] for x, y, z in lm]
    with open(os.path.join(OUT, 'hero-data.js'), 'w', encoding='utf-8') as f:
        f.write('// Generated by tools/prepare_hero.py: MediaPipe face mesh of assets/hero/face.webp, 478 points as [x, y] fractions of the image.\n')
        f.write('const MESH = ' + json.dumps({'pts': pts, 'hairTop': round(hair_top, 4)}, separators=(',', ':')) + ';\n')
    print('mesh: eyes', pts[468], pts[473], 'chin', pts[152])

    # 4. Depth: a rounded body from the silhouette, the face's own relief from the mesh on top.
    mask = a > 0.5
    body = np.zeros((H, W))
    ys, xs = np.mgrid[0:H, 0:W]
    for y in range(H):
        row = np.where(mask[y])[0]
        if row.size < 4:
            continue
        lo, hi = row.min(), row.max()
        # the widest span on the row (ignores stray pixels off to one side)
        cx, hw = (lo + hi) / 2, max((hi - lo) / 2, 1)
        t = np.clip((xs[y, lo:hi + 1] - cx) / hw, -1, 1)
        body[y, lo:hi + 1] = np.sqrt(1 - t * t)
    body = ndimage.gaussian_filter(body, 14)
    # Face relief: MediaPipe z (negative = nearer the camera), interpolated across the face, zero at its rim.
    fx, fy, fz = lm[:, 0], lm[:, 1], -lm[:, 2]
    fz = (fz - fz.min()) / max(fz.max() - fz.min(), 1e-6)
    relief = griddata(np.c_[fx, fy], fz, (xs, ys), method='linear', fill_value=np.nan)
    inside = ~np.isnan(relief)
    relief = np.nan_to_num(relief)
    feather = ndimage.gaussian_filter(inside.astype(float), 18)
    relief = ndimage.gaussian_filter(relief, 6) * feather
    # Shoulders a touch nearer than the face centre, as in the reference, and the head slightly proud of the neck.
    tilt = 0.10 * (ys / H)
    depth = body * 0.72 + relief * 0.30 + tilt
    depth *= ndimage.gaussian_filter(a, 4)
    depth = ndimage.gaussian_filter(depth, 5)
    depth = np.clip(depth / depth.max(), 0, 1)
    Image.fromarray((depth * 253).astype(np.uint8), 'L').convert('RGB').save(os.path.join(OUT, 'depth.webp'), quality=90, method=6)

    # 5. The machine view.
    machine = render_machine(np.array(crop).astype(np.float64) / 255, a, depth, lm)
    Image.fromarray(machine, 'RGBA').save(os.path.join(OUT, 'machine.webp'), quality=92, method=6)
    print('wrote', os.listdir(OUT))


def render_machine(rgb, a, depth, lm):
    import cv2
    gray = rgb @ np.array([0.299, 0.587, 0.114])
    # Lit metal from the depth relief: a key light top-left, a cool rim from the right.
    gy, gx = np.gradient(ndimage.gaussian_filter(depth, 2) * 60)
    n = np.dstack([-gx, -gy, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    key = np.array([-0.45, -0.55, 0.7]); key /= np.linalg.norm(key)
    rim = np.array([0.9, -0.1, 0.4]); rim /= np.linalg.norm(rim)
    view = np.array([0, 0, 1.0])
    diff = np.clip(n @ key, 0, 1)
    hk = (key + view); hk /= np.linalg.norm(hk)
    spec = np.clip(n @ hk, 0, 1) ** 28
    rimL = np.clip(n @ rim, 0, 1) ** 3
    base = np.clip((gray - 0.15) * 1.3, 0, 1) ** 1.1          # the photo's own light and shade, pushed darker
    lum = 0.05 + 0.22 * base + 0.30 * diff * (0.4 + 0.6 * base) + 0.45 * spec + 0.18 * rimL
    tint = np.array([0.80, 0.88, 0.94])                        # cool graphite
    col = np.clip(lum[..., None] * tint, 0, 1)
    # Brushed texture: fine horizontal noise lines.
    rng = np.random.default_rng(7)
    brush = ndimage.gaussian_filter1d(rng.normal(0, 1, (H, W)), 9, axis=1)
    brush = ndimage.gaussian_filter1d(brush, 0.6, axis=0)
    col *= 1 + 0.08 * brush[..., None]

    img = (np.clip(col, 0, 1) * 255).astype(np.uint8)
    img = np.ascontiguousarray(img)
    pts = lm[:, :2]
    P = lambda i: (int(round(pts[i, 0])), int(round(pts[i, 1])))

    # Panels: the face-mesh wireframe as etched seams, the contours as brighter welds.
    seam = (120, 150, 165)
    for i, j in connections('FACE_LANDMARKS_TESSELATION'):
        cv2.line(img, P(i), P(j), seam, 1, cv2.LINE_AA)
    img = cv2.addWeighted(img, 0.72, (np.clip(col, 0, 1) * 255).astype(np.uint8), 0.28, 0)
    for i, j in connections('FACE_LANDMARKS_CONTOURS'):
        cv2.line(img, P(i), P(j), (190, 225, 235), 2, cv2.LINE_AA)
    # Skull and body plates: a hex grid outside the face, horizontal plate seams across the chest.
    hull = cv2.convexHull(pts.astype(np.int32))
    facemask = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(facemask, hull, 255)
    facemask = cv2.dilate(facemask, np.ones((25, 25), np.uint8))
    plates = np.zeros((H, W, 3), np.uint8)
    s = 46
    for row, y in enumerate(range(0, H + s, int(s * 0.87))):
        off = (s // 2) if row % 2 else 0
        for x in range(-s, W + s, s):
            cx, cy = x + off, y
            hexpts = np.array([[cx + s / 2 * np.cos(np.pi / 6 + k * np.pi / 3), cy + s / 2 * np.sin(np.pi / 6 + k * np.pi / 3)] for k in range(6)], np.int32)
            cv2.polylines(plates, [hexpts], True, (70, 95, 105), 1, cv2.LINE_AA)
    chin_y = int(pts[152, 1])
    for y in range(chin_y + 60, H, 110):
        cv2.line(plates, (0, y), (W, y), (140, 175, 185), 2, cv2.LINE_AA)
        cv2.line(plates, (0, y + 6), (W, y + 6), (30, 40, 45), 2, cv2.LINE_AA)
    cx = int((pts[468, 0] + pts[473, 0]) / 2)
    cv2.line(plates, (cx, chin_y + 30), (cx, H), (140, 175, 185), 2, cv2.LINE_AA)
    outside = (facemask == 0)[..., None]
    img = np.where(outside, cv2.addWeighted(img, 1.0, plates, 0.55, 0), img).astype(np.uint8)

    # Mouth: a dark grille between the lips.
    lips = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
    lip_poly = pts[lips].astype(np.int32)
    cv2.fillPoly(img, [lip_poly], (14, 18, 20), cv2.LINE_AA)
    x0, x1 = lip_poly[:, 0].min(), lip_poly[:, 0].max()
    grille = np.zeros_like(img)
    for x in range(x0 + 6, x1, 9):
        cv2.line(grille, (x, 0), (x, H), (120, 160, 170), 2, cv2.LINE_AA)
    lipmask = np.zeros((H, W), np.uint8); cv2.fillPoly(lipmask, [lip_poly], 255)
    lipmask = cv2.erode(lipmask, np.ones((5, 5), np.uint8))
    img = np.where(lipmask[..., None] > 0, cv2.addWeighted(img, 1.0, grille, 0.8, 0), img).astype(np.uint8)

    # Eyes: lenses. Socket, housing ring, iris glow, pupil.
    for c, ring in ((468, [469, 470, 471, 472]), (473, [474, 475, 476, 477])):
        ex, ey = P(c)
        r = int(np.mean([np.hypot(*(pts[k] - pts[c])) for k in ring]))
        cv2.circle(img, (ex, ey), int(r * 2.1), (10, 12, 14), -1, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), int(r * 2.1), (150, 185, 195), 2, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), int(r * 1.45), (60, 80, 90), 3, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), int(r * 1.1), (40, 180, 205), -1, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), int(r * 0.75), (120, 235, 250), -1, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), int(r * 0.36), (8, 10, 12), -1, cv2.LINE_AA)
        cv2.circle(img, (ex - int(r * 0.35), ey - int(r * 0.35)), int(r * 0.18), (230, 250, 255), -1, cv2.LINE_AA)
        for k in range(12):
            ang = k * np.pi / 6
            cv2.line(img, (int(ex + r * 1.5 * np.cos(ang)), int(ey + r * 1.5 * np.sin(ang))), (int(ex + r * 2.0 * np.cos(ang)), int(ey + r * 2.0 * np.sin(ang))), (90, 120, 130), 1, cv2.LINE_AA)

    # Alpha: the figure, but ending in a straight cut 89.6% of the way down, as the shader expects (machineFade).
    alpha = (a * 255).astype(np.uint8).copy()
    alpha[int(H * 0.896):, :] = 0
    out = np.dstack([img, alpha])
    return out


if __name__ == '__main__':
    main()
