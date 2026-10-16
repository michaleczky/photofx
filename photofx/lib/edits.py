"""Non-destructive tone and color edits: exposure, contrast, WB, saturation.

Values live in the sidecar (see :data:`photofx.lib.catalog.EDIT_KEYS`);
this module turns them into pixels. Everything is a global operation, so
it is scale-independent and can be applied to thumbnails and full-size
renders alike.

- exposure: EV, linear gain (2 ** ev) on all channels
- contrast: -100..100, stretch around the image's mean gray (Pillow)
- temp:     -100..100, cool->warm (blue -> yellow)
- tint:     -100..100, green -> magenta
- saturation: -100..100, -100 turns the image grayscale
"""

from __future__ import annotations

import math

from PIL import Image, ImageEnhance, ImageOps

from .catalog import EDIT_KEYS

TEMP_GAIN = 0.4     # red/blue gain at temp = +/-100
TINT_GAIN = 0.15    # red/blue gain at tint = +/-100
TINT_GREEN = 0.3    # green gain reduction at tint = +100

LUMA_TARGET = 118    # mean luma the Auto exposure aims for (18% sRGB gray)
EXPOSURE_EPS = 0.05  # Auto drops exposure suggestions smaller than this
AUTO_SAMPLE = 256    # longest side of the sample Auto computes from


def is_default(edits: dict[str, float]) -> bool:
    """True when no slider is moved (every value zero or missing)."""
    return not any(v for v in edits.values())


def apply_edits(img: Image.Image, edits: dict[str, float]) -> Image.Image:
    """Apply the edit sliders to an image; returns the input when untouched."""
    if is_default(edits):
        return img
    exposure = edits.get("exposure", 0.0)
    contrast = edits.get("contrast", 0.0)
    temp = edits.get("temp", 0.0) / 100.0
    tint = edits.get("tint", 0.0) / 100.0
    saturation = edits.get("saturation", 0.0)

    if img.mode != "RGB":
        img = img.convert("RGB")

    # exposure + white balance are per-channel gains: one LUT pass
    gains = (
        (2.0 ** exposure) * (1 + TEMP_GAIN * temp) * (1 + TINT_GAIN * tint),
        (2.0 ** exposure) * (1 - TINT_GREEN * tint),
        (2.0 ** exposure) * (1 - TEMP_GAIN * temp) * (1 + TINT_GAIN * tint),
    )
    lut: list[int] = []
    for gain in gains:
        lut.extend(min(255, int(v * gain + 0.5)) for v in range(256))
    img = img.point(lut)

    if contrast:
        img = ImageEnhance.Contrast(img).enhance(1 + contrast / 100.0)
    if saturation:
        img = ImageEnhance.Color(img).enhance(1 + saturation / 100.0)
    return img


def auto_edits(img: Image.Image) -> dict[str, float]:
    """Suggest edits from the image itself: gray-world WB, exposure, contrast.

    Computed from a small sample, so it is cheap to call on the full-size
    render. Only nonzero values are returned.
    """
    sample = img.convert("RGB")
    sample.thumbnail((AUTO_SAMPLE, AUTO_SAMPLE), Image.BILINEAR)

    # --- white balance: gray-world gains, inverted into temp/tint ------
    means = []
    for channel in sample.split():
        hist = channel.histogram()
        total = sum(count * value for count, value in enumerate(hist))
        means.append(total / (sample.width * sample.height))
    mr, mg, mb = means
    avg = (mr + mg + mb) / 3
    gains = tuple(min(2.0, max(0.5, avg / m)) if m > 1 else 1.0 for m in means)

    # Solve E*(1+Tt)(1+Ts) = gr, E*(1-Ts') = gg, E*(1-Tt)(1+Ts) = gb up to
    # a common factor E (absorbed by exposure): with
    # A = (1 + TINT_GAIN*s) / (1 - TINT_GREEN*s), dividing the red and
    # blue equations by the green one gives A = (gr + gb) / (2*gg).
    gr, gg, gb = gains
    denom = 2 * gg
    A = (gr + gb) / denom if denom > 0 else 1.0
    s = (A - 1) / (TINT_GAIN + TINT_GREEN * A)
    t = ((gr / gg) / A - 1) / TEMP_GAIN if A > 0 else 0.0
    temp = min(100.0, max(-100.0, t * 100.0))
    tint = min(100.0, max(-100.0, s * 100.0))

    # --- exposure: bring the post-WB mean luma near LUMA_TARGET ---------
    luma_gain = 0.299 * gr + 0.587 * gg + 0.114 * gb
    luma = avg * luma_gain
    exposure = min(1.5, max(-1.5, math.log2(LUMA_TARGET / max(1.0, luma))))
    if abs(exposure) < EXPOSURE_EPS:
        exposure = 0.0

    # --- contrast: stretch the luma range toward ~20..235 ---------------
    # Pillow's Contrast pivots at the image's mean gray:
    # out = mean + (v - mean) * factor.
    gray = ImageOps.grayscale(sample)
    hist = gray.histogram()
    total = sample.width * sample.height
    mean = sum(v * count for v, count in enumerate(hist)) / total
    low = _percentile(hist, total, 0.005)
    high = _percentile(hist, total, 0.995)
    factor = 1.0
    if high < 235 or low > 20:
        f_high = (235 - mean) / max(1.0, high - mean) if high > mean else 1.0
        f_low = (20 - mean) / min(-1.0, low - mean) if low < mean else 1.0
        factor = min(1.6, max(0.8, (min(2.0, f_high) + min(2.0, f_low)) / 2))
    contrast = (factor - 1.0) * 100.0

    out = {"exposure": round(exposure, 2),
           "contrast": int(round(contrast)),
           "temp": int(round(temp)),
           "tint": int(round(tint))}
    return {k: v for k, v in out.items() if k in EDIT_KEYS and v != 0}


def _percentile(hist: list[int], total: int, fraction: float) -> int:
    """Value below which ``fraction`` of the pixels fall."""
    target = total * fraction
    cumulative = 0
    for value, count in enumerate(hist):
        cumulative += count
        if cumulative >= target:
            return value
    return 255
