#!/usr/bin/env python3
"""Rebuild `brand/` from the supplied artwork.

Run from anywhere:  python tools/build_brand_assets.py
Needs Pillow and numpy; neither is a runtime dependency of the integration,
so this is not in `tests/requirements.txt` and CI does not run it. The
assets it produces are committed — this script exists so the next person to
change the artwork does not have to re-derive the decisions below, and so
`brand/` can be proven to come from `tools/brand_source.jpg` rather than
from a graphics editor nobody can reproduce.

The source is a JPEG on an off-white ground, so nothing here trusts a colour
key alone:

  * The HOUSE silhouette is the per-row span of saturated-blue pixels. The
    white node glyph REACHES the house's bottom edge (measured: ~28px of the
    final rows are white), so a flood fill inward from the border leaks
    straight up into the glyph and a hole-fill never closes it, because the
    glyph is not an enclosed hole. A row span cannot leak, because the house
    is horizontally convex — every row's outermost pixels are house edge.
  * Edges are RE-RASTERISED, not resampled. Each mask goes to 4x, is blurred
    by a sub-pixel amount at that scale and hard-cut, then is downsampled
    with LANCZOS. Upscaling the JPEG directly keeps its edge ringing, which a
    bare threshold turns into stair-stepping on the roof diagonals.
  * Downsampling runs on PREMULTIPLIED alpha. Without that, transparent black
    bleeds into the antialiased rim and every asset picks up a dark halo that
    only shows on a light background.
  * The WORDMARK is matted on luminance against the measured ground, which
    separates cleanly (ink 118-130, ground 236-249), and its ink colour is
    then unmixed from the ground it sat on.
"""

from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "brand_source.jpg"
OUT = ROOT / "brand"

BLUE = (49, 185, 235)  # measured mode of the mark's fill
SS = 4  # supersample factor
GROUND, INK = 236.0, 150.0  # wordmark matte endpoints, measured
# The tagline is set far darker than the wordmark (measured: median luminance
# 63 against the wordmark's 124). On a dark ground — Home Assistant's own
# integration page under a dark theme, GitHub in dark mode — that is under 2:1
# and disappears while the wordmark above it survives. Floor the ink so the
# darkest type clears a dark ground. The two-tone HOUSEHOLD/STATE relationship
# sits above the floor and is untouched.
FLOOR = 108.0


def _masks(src: np.ndarray):
    """House silhouette and white node glyph, at source resolution."""
    R, G, B = src[..., 0], src[..., 1], src[..., 2]
    blue = (B > 140) & ((B - R) > 45)
    ys, xs = np.nonzero(blue)

    sil = np.zeros_like(blue)
    for y in range(ys.min(), ys.max() + 1):
        row = np.nonzero(blue[y])[0]
        if row.size:
            sil[y, row.min() : row.max() + 1] = True

    bright = (R > 200) & (G > 200) & (B > 200)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    return sil, sil & bright, box


def _crisp(mask: np.ndarray, box, factor: int = SS) -> np.ndarray:
    """Mask -> hard-edged mask at `factor` scale, JPEG ringing averaged out."""
    im = Image.fromarray((mask[box[1] : box[3], box[0] : box[2]] * 255).astype(np.uint8), "L")
    big = im.resize((im.width * factor, im.height * factor), Image.LANCZOS)
    big = big.filter(ImageFilter.GaussianBlur(factor * 0.55))
    return np.asarray(big).astype(np.int16) >= 128


def _compose(sil: np.ndarray, glyph: np.ndarray, colour) -> Image.Image:
    h, w = sil.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for i in range(3):
        rgba[..., i] = np.where(glyph, 255, colour[i])
    rgba[..., 3] = np.where(sil, 255, 0)
    return Image.fromarray(rgba, "RGBA")


def _resize(img: Image.Image, size) -> Image.Image:
    """LANCZOS on premultiplied alpha, then unpremultiply."""
    a = np.asarray(img).astype(np.float64)
    al = a[..., 3:4] / 255.0
    pre = np.concatenate([a[..., :3] * al, a[..., 3:4]], axis=2)
    small = np.asarray(
        Image.fromarray(pre.round().clip(0, 255).astype(np.uint8), "RGBA").resize(size, Image.LANCZOS)
    ).astype(np.float64)
    out_a = small[..., 3:4]
    rgb = np.where(out_a > 0, small[..., :3] * 255.0 / np.maximum(out_a, 1e-6), 0)
    return Image.fromarray(
        np.concatenate([rgb.clip(0, 255), out_a], axis=2).round().astype(np.uint8), "RGBA"
    )


def _wordmark(src: np.ndarray) -> Image.Image:
    lum = src.mean(axis=2)
    wx0, wy0, wx1, wy1 = 195, 468, 830, 640
    alpha = ((GROUND - lum[wy0:wy1, wx0:wx1]) / (GROUND - INK)).clip(0, 1)
    cols = np.nonzero(alpha.max(axis=0) > 0.15)[0]
    rows = np.nonzero(alpha.max(axis=1) > 0.15)[0]
    alpha = alpha[rows.min() : rows.max() + 1, cols.min() : cols.max() + 1]
    rgb = src[wy0 + rows.min() : wy0 + rows.max() + 1, wx0 + cols.min() : wx0 + cols.max() + 1]

    a3 = alpha[..., None]
    ink = np.where(a3 > 0.02, (rgb - GROUND * (1 - a3)) / np.maximum(a3, 1e-6), 0).clip(0, 255)
    lum_ink = ink.mean(axis=2, keepdims=True)
    ink = np.where(lum_ink > 1.0, ink * np.maximum(1.0, FLOOR / np.maximum(lum_ink, 1e-6)), ink)
    return Image.fromarray(
        np.concatenate([ink.clip(0, 255), (alpha * 255)[..., None]], axis=2).round().astype(np.uint8),
        "RGBA",
    )


def _square(mark: Image.Image, edge: int, pad_frac: float = 0.04) -> Image.Image:
    """Mark centred on a square canvas, longest side to (1 - 2*pad) of it."""
    inner = int(round(edge * (1 - 2 * pad_frac)))
    scale = inner / max(mark.size)
    r = _resize(mark, (max(1, round(mark.width * scale)), max(1, round(mark.height * scale))))
    canvas = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
    canvas.paste(r, ((edge - r.width) // 2, (edge - r.height) // 2))
    return canvas


def _lockup(mark: Image.Image, word: Image.Image, width: int, height: int) -> Image.Image:
    """The supplied arrangement: mark above wordmark, both centred."""
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pad, gap = round(width * 0.03), round(height * 0.07)
    wm_w = round(width * 0.88)
    wm_h = round(wm_w * word.height / word.width)
    mk_h = height - wm_h - gap - 2 * pad
    mk_w = round(mk_h * mark.width / mark.height)
    if mk_w > width * 0.5:
        mk_w = round(width * 0.5)
        mk_h = round(mk_w * mark.height / mark.width)
    mk, wm = _resize(mark, (mk_w, mk_h)), _resize(word, (wm_w, wm_h))
    top = (height - (mk_h + gap + wm_h)) // 2
    canvas.paste(mk, ((width - mk_w) // 2, top), mk)
    canvas.paste(wm, ((width - wm_w) // 2, top + mk_h + gap), wm)
    return canvas


def main() -> None:
    src = np.asarray(Image.open(SRC).convert("RGB")).astype(np.int16)
    sil, glyph, box = _masks(src)
    mark = _compose(_crisp(sil, box), _crisp(glyph, box), BLUE)
    word = _wordmark(src)

    # Sizes are home-assistant/brands': the icon square at 256 and 512, the
    # logo no taller than 256 and no wider than 512, doubled for the @2x.
    written = {
        "icon.png": _square(mark, 256),
        "icon@2x.png": _square(mark, 512),
        "logo.png": _lockup(mark, word, 512, 256),
        "logo@2x.png": _lockup(mark, word, 1024, 512),
    }
    OUT.mkdir(exist_ok=True)
    for name, img in written.items():
        img.save(OUT / name)
        print(f"{name}: {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
