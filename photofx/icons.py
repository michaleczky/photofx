"""Toolbar icons loaded from photofx/icons, scaled for display.

Credits:
  folder, arrow-left, arrow-right, star, star-off, close, pencil:
    "wefunction woofunction" icon set — GPL (via iconarchive.com)
  trash:
    "Koloria" icon set by GraphicRating — free for commercial use
    (via iconarchive.com)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageTk

ICON_DIR = Path(__file__).parent / "icons"
_cache: dict[tuple[str, int], ImageTk.PhotoImage] = {}


def load(name: str, size: int = 18) -> ImageTk.PhotoImage | None:
    """Return a scaled PhotoImage for the named icon, or None if missing."""
    key = (name, size)
    if key in _cache:
        return _cache[key]
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _cache[key] = photo
    return photo
