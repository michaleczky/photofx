"""PhotoGrid: the scrollable thumbnail grid.

:class:`PhotoGrid` is the canvas widget that lays cells out, routes mouse
events and patches thumbnails into cells. The actual work lives in its
collaborators:

- :class:`~photofx.app.selection.Selection` — what is selected
- :class:`~photofx.app.thumbs.ThumbnailStore` — where thumbnails come from
- :class:`~photofx.app.cells.CellRenderer` — how a cell is painted
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from photofx.lib.catalog import Photo
from photofx.lib.render import ThumbCache, ThumbWorker
from photofx.app.cells import CellRenderer
from photofx.app.selection import Selection
from photofx.app.thumbs import ThumbnailStore

PAD = 10
BG = "#1e1e1e"
CAPTION_H = 34       # caption strip below the thumbnail


class PhotoGrid(tk.Canvas):
    """Scrollable grid of photo cells with click / ctrl-click / shift-click."""

    def __init__(self, master, thumb_size: int = 170, on_select=None, on_open=None):
        super().__init__(master, background=BG, highlightthickness=0)
        self.photos: list[Photo] = []     # photos set by the app
        self.filtered: list[Photo] = []   # photos actually laid out
        self.thumb_size = thumb_size
        self.cell_w = thumb_size + 2 * PAD
        self.cell_h = thumb_size + 2 * PAD + CAPTION_H
        self.columns = 1
        self.cache = ThumbCache()
        self.tk_images: dict[str, ImageTk.PhotoImage] = {}
        self.selection = Selection()
        self.thumbs = ThumbnailStore(self, self.cache, thumb_size,
                                      on_ready=self._thumbnail_ready)
        self.renderer = CellRenderer(self, thumb_size)
        self._cell_origins: dict[str, tuple[int, int]] = {}
        self.on_select = on_select
        self.on_open = on_open

        self._scroll = ttk.Scrollbar(master, orient="vertical", command=self.yview)
        self.configure(yscrollcommand=self._scroll.set)

        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-Button-1>", self._on_double)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Destroy>", lambda e: self.thumbs.cancel_poll(), add="+")
        self.bind("<MouseWheel>",
                  lambda e: self.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.bind("<B1-Motion>", self._on_drag)

    @property
    def scroll(self):
        return self._scroll

    # ---------------------------------------------------------------- layout
    def _on_resize(self, event):
        self.columns = max(1, (event.width - PAD) // self.cell_w)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        self._cell_origins = {}
        rows = (len(self.filtered) + self.columns - 1) // self.columns if self.filtered else 1
        height = rows * self.cell_h + PAD
        self.configure(scrollregion=(
            0, 0, max(self.winfo_width(), self.columns * self.cell_w + PAD), height))
        paths = [str(p.path) for p in self.filtered]
        ranks = self.selection.ranks(paths)
        show_ranks = len(self.selection.paths) > 1
        for i, photo in enumerate(self.filtered):
            col, row = i % self.columns, i // self.columns
            x = PAD + col * self.cell_w
            y = PAD + row * self.cell_h
            s = paths[i]
            self._cell_origins[s] = (x, y)
            self.renderer.draw(
                photo, (x, y, x + self.cell_w - PAD, y + self.cell_h - PAD),
                self.tk_images.get(s), s in self.selection.paths,
                ranks.get(s) if show_ranks else None)
        self._notify_selection()

    # --------------------------------------------------------------- contents
    def set_photos(self, photos: list[Photo], keep_selection=True):
        self.photos = photos
        paths = {str(p.path) for p in photos}
        if keep_selection:
            self.selection.retain(paths)
        else:
            self.selection.clear()
        self.selection.anchor = None
        for p in list(self.tk_images):   # drop images of photos no longer shown
            if p not in paths:
                del self.tk_images[p]
        self._layout()

    def _layout(self):
        """Lay out the current photos, queuing thumbnails for empty cells."""
        self.filtered = list(self.photos)
        self.thumbs.set_photos(self.filtered)
        for photo in self.filtered:      # enqueue only what is not displayed yet
            if str(photo.path) not in self.tk_images:
                self.thumbs.request(photo)
        self._redraw()
        if self.thumbs.worker is None and self.thumbs.pending:
            self.after_idle(self.thumbs.pump_idle)

    def set_worker(self, worker: ThumbWorker):
        """Install a background thumbnail worker for this grid."""
        self.thumbs.set_worker(worker)

    def shutdown(self):
        """Stop the thumbnail machinery (called when the app closes)."""
        self.thumbs.shutdown()

    def purge_thumbnail(self, photo: Photo):
        self.thumbs.purge(photo)

    def refresh_cell(self, photo: Photo):
        self.refresh_cells([photo])

    def refresh_cells(self, photos: list[Photo]):
        """Metadata changed: invalidate cached thumbs, re-render, redraw badges."""
        for photo in photos:
            self.tk_images.pop(str(photo.path), None)
            self.thumbs.refresh(photo)
        self._redraw()

    def remove_paths(self, paths: list[str]):
        gone = set(paths)
        self.selection.remove(gone)
        self.photos = [p for p in self.photos if str(p.path) not in gone]
        for p in paths:
            self.tk_images.pop(p, None)
        self._layout()

    # ------------------------------------------------------------- thumbnails
    def update_thumbnail(self, path: str, tkimg: ImageTk.PhotoImage) -> None:
        """Show a rendered thumbnail in its cell without redrawing the grid."""
        self.tk_images[path] = tkimg
        tag = "img:" + path
        origin = self._cell_origins.get(path)
        if origin is None:
            items = self.find_withtag(tag) or self.find_withtag("ph:" + path)
            if not items:
                return  # no cell for this path right now
            origin = self.coords(items[0])[:2]
        x = origin[0] + (self.thumb_size - tkimg.width()) // 2
        y = origin[1] + (self.thumb_size - tkimg.height()) // 2
        self.delete(tag, "ph:" + path)
        self.create_image(x, y, image=tkimg, anchor="nw", tags=(tag,))
        self.tag_raise("ov:" + path)  # badges must stay above the image

    def _thumbnail_ready(self, path: str, img: Image.Image):
        """A thumbnail arrived from the store: show it if the cell is empty."""
        if path in self.thumbs.visible and path not in self.tk_images:
            self.update_thumbnail(path, ImageTk.PhotoImage(img))

    # ------------------------------------------------------------ interaction
    def _photo_at_event(self, event) -> tuple[int, Photo] | None:
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)
        col = int((x - PAD) // self.cell_w)
        row = int((y - PAD) // self.cell_h)
        if x < PAD or col >= self.columns:
            return None
        idx = row * self.columns + col
        if 0 <= idx < len(self.filtered):
            return idx, self.filtered[idx]
        return None

    def _on_click(self, event):
        hit = self._photo_at_event(event)
        if hit is None:
            if not (event.state & 0x0004):  # ctrl
                self.selection.clear()
                self._redraw()
            return
        idx, photo = hit
        self.selection.click(idx, str(photo.path),
                             [str(p.path) for p in self.filtered], event.state)
        self._redraw()

    def _on_drag(self, event):
        # extend a shift-drag from the anchor over cells
        hit = self._photo_at_event(event)
        if hit is None:
            return
        if event.state & 0x0001:
            self.selection.drag_to(hit[0], [str(p.path) for p in self.filtered])
            self._redraw()

    def _on_double(self, event):
        hit = self._photo_at_event(event)
        if hit and self.on_open:
            self.on_open(hit[1])

    def _on_right_click(self, event):
        hit = self._photo_at_event(event)
        if hit is None:
            return
        idx, photo = hit
        if str(photo.path) not in self.selection.paths:
            self.select_one(idx)

    def select_one(self, idx: int):
        """Select exactly the photo at filtered index ``idx``."""
        self.selection.click(idx, str(self.filtered[idx].path), [])
        self._redraw()

    # -------------------------------------------------------------- selection
    def selected_photos(self) -> list[Photo]:
        return [p for p in self.filtered if str(p.path) in self.selection.paths]

    def select(self, paths):
        """Replace the selection outright, keeping the current anchor."""
        self.selection.paths = set(paths)

    def select_all(self):
        self.selection.select_all([str(p.path) for p in self.filtered])
        self._redraw()

    def clear_selection(self):
        self.selection.clear()
        self._redraw()

    def move_selection(self, delta: int):
        idx = self.selection.move(delta, [str(p.path) for p in self.filtered])
        if idx is not None:
            self._redraw()
            self._scroll_to_index(idx)

    def _notify_selection(self):
        if self.on_select:
            self.on_select(self.selected_photos())

    # ---------------------------------------------------------------- scrolling
    def _scroll_to_index(self, idx: int):
        row = idx // self.columns
        top = row * self.cell_h
        bottom = top + self.cell_h
        visible_top = self.canvasy(0)
        visible_bottom = self.canvasy(self.winfo_height())
        if top < visible_top:
            self.yview_moveto(top / self._total_height())
        elif bottom > visible_bottom:
            self.yview_moveto((bottom - self.winfo_height()) / self._total_height())

    def _total_height(self) -> float:
        region = self.cget("scrollregion")
        parts = self.tk.splitlist(region)
        return float(parts[3]) if len(parts) == 4 else 1.0
