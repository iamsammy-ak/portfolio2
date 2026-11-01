"""Fits a rendered machine head (tools/machine-source.webp) to the portrait's face mesh.

    python tools/fit_machine.py

The source render was made for a different face: its eyes and chin sit at SRC_EYES / SRC_CHIN (fractions of the
image). An affine transform maps those three points onto the same landmarks in assets/hero/hero-data.js, so the
machine's eyes land under the portrait's eyes and the jaw under its jaw. Writes assets/hero/machine.webp, cut off
89.6% of the way down as the shader expects. Run tools/prepare_hero.py first (for the mesh); run this after it.
"""
import json, os, re
import numpy as np
import cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, 'machine-source.webp')
OUT = os.path.join(ROOT, 'assets', 'hero', 'machine.webp')
W, H = 1186, 1600
# Where the source render's right iris, left iris and chin sit (fractions of its 1186x1600 canvas).
SRC_EYES = ((0.41129, 0.41443), (0.57253, 0.41323))
SRC_CHIN = (0.48683, 0.63375)

mesh = json.loads(re.search(r'const MESH = (\{.*\});', open(os.path.join(ROOT, 'assets', 'hero', 'hero-data.js'), encoding='utf-8').read()).group(1))
pts = mesh['pts']
dst = np.float32([[pts[468][0] * W, pts[468][1] * H], [pts[473][0] * W, pts[473][1] * H], [pts[152][0] * W, pts[152][1] * H]])
src = np.float32([[SRC_EYES[0][0] * W, SRC_EYES[0][1] * H], [SRC_EYES[1][0] * W, SRC_EYES[1][1] * H], [SRC_CHIN[0] * W, SRC_CHIN[1] * H]])
# A similarity (scale, rotation, shift) keeps the render's proportions; three points would also shear it.
M, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.LMEDS)
print('scale %.3f  shift %.0f,%.0f' % (np.hypot(M[0, 0], M[0, 1]), M[0, 2], M[1, 2]))

img = np.array(Image.open(SRC).convert('RGBA'))
if img.shape[1] != W or img.shape[0] != H:
    img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
# Beyond the render's edges the torso carries on: replicate the border so a scale above 1 leaves no gap at the sides.
warped = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
# Replicated border above the head or beside it would smear the transparent background, which is fine (alpha 0),
# but at the bottom the torso must stay opaque down to the cut.
warped[int(H * 0.896):, :, 3] = 0
Image.fromarray(warped, 'RGBA').save(OUT, quality=92, method=6)
print('wrote', OUT)
