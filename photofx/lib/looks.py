"""Named color looks ("filters"): recipes applied on top of the edit sliders.

A look is a fixed, named color transformation. The tone recipes are
per-channel 256-entry LUTs — the same mechanism the exposure and
white-balance sliders use — so they are cheap and apply in a single
:meth:`PIL.Image.Image.point` pass. The monochrome recipes convert to
gray and tint from there.

Everything is a global operation, so looks are scale-independent: they
apply to the viewer's display-sized preview and to thumbnails alike.
Looks are stored non-destructively — the sidecar holds the look's name
(``filter`` key, see :class:`photofx.lib.catalog.Photo`), never a pixel.
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageOps

# name -> caption; the names are the sidecar values, the captions the UI.
# "" is not a look: an empty/absent value means "no filter".
LOOKS: dict[str, str] = {
    "mono": "Mono",
    "sepia": "Sepia",
    "noir": "Noir",
    "vivid": "Vivid",
    "fade": "Fade",
    "golden": "Golden",
    "arctic": "Arctic",
}

SEPIA_DARK = (40, 30, 20)      # shadows: dark brown
SEPIA_LIGHT = (245, 226, 185)  # highlights: cream


# ------------------------------------------------------------- helpers
def _clamp(v: float) -> int:
    return min(255, max(0, int(v + 0.5)))


def _lut(img: Image.Image, curves) -> Image.Image:
    """Apply one 256-entry table per channel in a single point() pass."""
    lut: list[int] = []
    for curve in curves:
        lut.extend(_clamp(curve(v)) for v in range(256))
    return img.point(lut)


def _contrast(factor: float, pivot: float = 128.0):
    """Stretch the values around ``pivot``; factor > 1 hardens."""
    return lambda v: pivot + (v - pivot) * factor


def _gain(*gains: float):
    """Per-channel gain curves (one callable per channel)."""
    return [lambda v, g=g: v * g for g in gains]


# ------------------------------------------------------------- recipes
def _mono(img: Image.Image) -> Image.Image:
    return ImageOps.grayscale(img).convert("RGB")


def _sepia(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    return ImageOps.colorize(gray, black=SEPIA_DARK, white=SEPIA_LIGHT)


def _noir(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img).convert("RGB")
    curve = _contrast(1.5)
    return _lut(gray, (curve, curve, curve))


def _vivid(img: Image.Image) -> Image.Image:
    curve = _contrast(1.3)
    img = _lut(img, (curve, curve, curve))
    return ImageEnhance.Color(img).enhance(1.35)


def _fade(img: Image.Image) -> Image.Image:
    lift = 22.0
    compress = 0.82
    curve = lambda v: lift + v * compress        # noqa: E731
    img = _lut(img, (curve, curve, curve))
    return ImageEnhance.Color(img).enhance(0.85)


def _golden(img: Image.Image) -> Image.Image:
    img = _lut(img, _gain(1.10, 1.02, 0.86))
    return ImageEnhance.Color(img).enhance(1.05)


def _arctic(img: Image.Image) -> Image.Image:
    img = _lut(img, _gain(0.88, 0.97, 1.12))
    return ImageEnhance.Color(img).enhance(0.95)


_RECIPES = {
    "mono": _mono,
    "sepia": _sepia,
    "noir": _noir,
    "vivid": _vivid,
    "fade": _fade,
    "golden": _golden,
    "arctic": _arctic,
}


# ----------------------------------------------------------------- api
def apply_look(img: Image.Image, name: str | None) -> Image.Image:
    """Apply the named look; returns the input when no look is selected.

    Applied after the edit sliders (see
    :func:`photofx.lib.edits.apply_edits`), so a look colors the corrected
    image. Unknown names are ignored, keeping sidecars from newer
    versions harmless.
    """
    if not name or name not in _RECIPES:
        return img
    if img.mode != "RGB":
        img = img.convert("RGB")
    return _RECIPES[name](img)
