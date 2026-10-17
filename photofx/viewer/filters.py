"""Filters pane: named looks with live previews, shown beside the photo.

:class:`FiltersPane` builds the middle part of the viewer's right pane:
one tile per look (:data:`photofx.lib.looks.LOOKS`) plus an Original
tile that clears the filter. Each tile carries a small preview of the
current photo with that look applied on top of its edits, so the looks
are picked by eye. Hovering a tile previews the look on the big image
(:meth:`viewer.live_filter`); clicking stores it in the sidecar
(:meth:`viewer.commit_filter`).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from photofx.lib import ui
from photofx.lib.edits import apply_edits
from photofx.lib.looks import LOOKS, apply_look
from photofx.lib.render import open_rotated

THUMB = (84, 56)    # preview size, longest side each
COLUMNS = 2         # tiles per row; the pane is as wide as the sliders


class FiltersPane:
    """The viewer's filter looks: tiles with live previews, Original first."""

    def __init__(self, viewer):
        self.viewer = viewer
        # no outer padding: the side pane provides it
        self.frame = ttk.Frame(viewer.side_pane, style="TFrame")   # packed by viewer._layout_side_pane
        header = ttk.Label(self.frame, text="FILTERS", foreground=ui.ACCENT)
        header.pack(anchor="w", pady=(8, 2))
        ttk.Separator(self.frame).pack(fill="x")
        self.body = ttk.Frame(self.frame)
        self.body.pack(fill="x")
        self._previews: dict[str, ImageTk.PhotoImage] = {}  # keep refs alive
        self.sync(None)

    # ----------------------------------------------------------------- api
    def sync(self, photo):
        """Rebuild the tiles for ``photo`` (nothing shown when None)."""
        for child in self.body.winfo_children():
            child.destroy()
        self._previews.clear()
        if photo is None:
            return
        base = self._base(photo)
        row = None
        for column, name in enumerate([""] + list(LOOKS)):
            if column % COLUMNS == 0:
                row = ttk.Frame(self.body)
                row.pack(fill="x", pady=(6, 0))
            self._tile(row, base, photo, name)

    # ------------------------------------------------------------ helpers
    def _tile(self, row, base: Image.Image, photo, name: str):
        """One preview tile: image on top, caption below, hover to preview."""
        caption = LOOKS.get(name, "Original")
        active = (name or None) == photo.filter
        image = self._preview(base, photo, name)
        color = ui.ACCENT if active else ui.FG
        tile = ttk.Frame(row)
        tile.pack(side="left", padx=(0, 12))
        preview = tk.Label(tile, image=image, bg=ui.PANEL,
                           highlightthickness=1,
                           highlightbackground=color)
        preview.pack(anchor="w")
        label = ttk.Label(tile, text=caption, foreground=color)
        label.pack(anchor="w")
        for widget in (tile, preview, label):
            widget.bind("<Enter>", lambda _e, n=name: self.viewer.live_filter(n))
            widget.bind("<Leave>", lambda _e: self.viewer.cancel_filter())
            widget.bind("<Button-1>",
                        lambda _e, n=name: self.viewer.commit_filter(n))
        self._previews[name] = image

    def _base(self, photo) -> Image.Image:
        """A small copy of the photo the previews render from."""
        img = self.viewer.view.base
        if img is None or not self.viewer.view.matches(photo):
            img = open_rotated(photo)
        img = img.copy()
        img.thumbnail(THUMB, Image.LANCZOS)
        return img

    def _preview(self, base: Image.Image, photo, name: str) -> ImageTk.PhotoImage:
        """The photo with its edits and the given look applied."""
        img = base
        if photo.edits:
            img = apply_edits(img, photo.edits)
        img = apply_look(img, name)
        return ImageTk.PhotoImage(img)
