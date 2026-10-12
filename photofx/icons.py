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

import tkinter as tk

from PIL import Image, ImageTk

ICON_DIR = Path(__file__).parent / "icons"

# PhotoImages are bound to one Tk interpreter, so the cache key includes it.
_cache: dict[tuple, ImageTk.PhotoImage] = {}


def load(name: str, size: int = 18, master: tk.Misc | None = None) -> ImageTk.PhotoImage | None:
    """Return a scaled PhotoImage for the named icon, or None if missing.

    ``master`` (any widget of the window the icon will be shown in) selects
    the Tk interpreter the image is created for; defaults to the root window.
    """
    if master is None:
        master = tk._get_default_root()  # same rule ImageTk applies anyway
    key = (master.tk, name, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _cache[key] = photo
    return photo
