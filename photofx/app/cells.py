"""Painting of a single grid cell: thumbnail, badges, caption, order mark.

:class:`CellRenderer` only draws; the grid tells it *where* (the cell
rectangle), *what* (the photo and its thumbnail, if loaded) and *how
selected* it is. Tag naming (``img:``/``ph:``/``ov:`` + path) is part of
the contract with the grid, which patches cells by tag.
"""

from __future__ import annotations

import math
import tkinter as tk

from photofx.lib.catalog import PICK, REJECT, Photo
from PIL import ImageTk

ACCENT = "#4a9eff"
PLACEHOLDER = "#2a2a2a"
STAR_FILL = "#ffcc00"
FLAG_FILL = "#d95040"
BADGE_OUTLINE = "#111111"


class CellRenderer:
    """Draws one thumbnail cell onto a canvas."""

    def __init__(self, canvas: tk.Canvas, thumb_size: int):
        self.canvas = canvas
        self.thumb_size = thumb_size

    def draw(self, photo: Photo, cell: tuple[int, int, int, int],
             img: ImageTk.PhotoImage | None, selected: bool,
             rank: int | None):
        """Paint the cell: frame, thumbnail or placeholder, badges, caption.

        ``rank`` is the 1-based selection order; None suppresses the
        order marker.
        """
        x0, y0, x1, y1 = cell
        s = str(photo.path)
        if selected:
            self.canvas.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2,
                                         outline=ACCENT, width=3)
        if img is not None:
            cx = x0 + (self.thumb_size - img.width()) // 2
            cy = y0 + (self.thumb_size - img.height()) // 2
            self.canvas.create_image(cx, cy, image=img, anchor="nw",
                                     tags=("img:" + s,))
        else:
            self.canvas.create_rectangle(
                x0, y0, x0 + self.thumb_size, y0 + self.thumb_size,
                fill=PLACEHOLDER, outline="", tags=("ph:" + s,))
            self.canvas.create_text(x0 + self.thumb_size // 2,
                                    y0 + self.thumb_size // 2,
                                    text="...", fill="#777", tags=("ph:" + s,))
        # flag badge
        if photo.flag == PICK:
            self._pick_star(x1, y0, "ov:" + s)
        elif photo.flag == REJECT:
            self._reject_x(x1, y0, "ov:" + s)
        if photo.crop is not None:
            self.canvas.create_text(x0 + 8, y0 + 10, text="⌗", fill=ACCENT,
                                    font=("TkDefaultFont", 12), tags=("ov:" + s,))
        # caption
        self.canvas.create_text(x0 + self.thumb_size // 2,
                                y0 + self.thumb_size + 8,
                                width=self.thumb_size, text=photo.name, anchor="n",
                                fill="#cccccc" if selected else "#999999",
                                font=("TkDefaultFont", 8))
        # selected order marker
        if selected and rank is not None:
            self.canvas.create_rectangle(x0, y0, x0 + 18, y0 + 16,
                                         fill=ACCENT, outline="",
                                         tags=("ov:" + s,))
            self.canvas.create_text(x0 + 9, y0 + 8, text=str(rank),
                                    fill="white", font=("TkDefaultFont", 7),
                                    tags=("ov:" + s,))

    def _pick_star(self, right: int, top: int, tag: str) -> None:
        """Yellow five-pointed star in the top-right corner of the cell."""
        cx, cy, r = right - 10, top + 10, 9
        points: list[float] = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = r if i % 2 == 0 else r * 0.42
            points += [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
        self.canvas.create_polygon(*points, fill=STAR_FILL,
                                   outline=BADGE_OUTLINE, tags=(tag,))

    def _reject_x(self, right: int, top: int, tag: str) -> None:
        """Red X in the top-right corner of the cell."""
        cx, cy, r = right - 10, top + 10, 6
        for x0, y0, x1, y1 in ((cx - r, cy - r, cx + r, cy + r),
                               (cx - r, cy + r, cx + r, cy - r)):
            self.canvas.create_line(x0, y0, x1, y1, fill=FLAG_FILL, width=3,
                                    capstyle="round", tags=(tag,))
