"""PhotoGrid: scrollable thumbnail grid with click / ctrl-click / shift-click."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from photofx.lib.catalog import PICK, REJECT, Photo
from photofx.lib.render import ThumbCache, load_thumb

PAD = 10
STAR_FILL = "#ffcc00"
FLAG_FILL = "#d95040"
BADGE_OUTLINE = "#111111"


class PhotoGrid(tk.Canvas):
    def __init__(self, master, thumb_size: int = 170, on_select=None, on_open=None):
        super().__init__(master, background="#1e1e1e", highlightthickness=0)
        self.photos: list[Photo] = []
        self.filtered: list[Photo] = []
        self.selection: set[str] = set()
        self._sel_order: list[str] = []  # paths in click order (pruned on redraw)
        self.anchor: int | None = None
        self.thumb_size = thumb_size
        self.cell_w = thumb_size + 2 * PAD
        self.cell_h = thumb_size + 2 * PAD + 34
        self.columns = 1
        self.cache = ThumbCache()
        self.tk_images: dict[str, ImageTk.PhotoImage] = {}
        self.pending: list[str] = []  # paths awaiting thumbnail generation (no worker)
        self._pumping = False
        self.worker = None             # set to a ThumbWorker to render off-thread
        self._poll_job = None
        self._paths: dict[str, Photo] = {}
        self._cell_origins: dict[str, tuple[int, int]] = {}
        self.on_select = on_select
        self.on_open = on_open

        self._scroll = ttk.Scrollbar(master, orient="vertical", command=self.yview)
        self.configure(yscrollcommand=self._scroll.set)

        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-Button-1>", self._on_double)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Destroy>", lambda e: self._cancel_poll(), add="+")
        self.bind("<MouseWheel>", lambda e: self.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        # drag-select and scroll while dragging near edges
        self.bind("<B1-Motion>", self._on_drag)
        self._autoscroll_job = None

    @property
    def scroll(self):
        return self._scroll

    # ---------------------------------------------------------------- layout
    def _on_resize(self, event):
        self.columns = max(1, (event.width - PAD) // self.cell_w)
        self._redraw()

    def set_photos(self, photos: list[Photo], keep_selection=True):
        self.photos = photos
        paths = {str(p.path) for p in photos}
        if keep_selection:
            self.selection &= paths
        else:
            self.selection = set()
        self.anchor = None
        for p in list(self.tk_images):   # drop images of photos no longer shown
            if p not in paths:
                del self.tk_images[p]
        self._apply_filter_and_redraw()

    def _apply_filter_and_redraw(self):
        self.filtered = list(self.photos)
        self._paths = {str(p.path): p for p in self.filtered}
        for photo in self.filtered:      # enqueue only what is not displayed yet
            if str(photo.path) not in self.tk_images:
                self._enqueue(photo, self.thumb_size)
        self._redraw()
        if self.worker is None and self.pending:
            self.after_idle(self._pump_idle)

    def _redraw(self):
        self.delete("all")
        self._cell_origins = {}
        rows = (len(self.filtered) + self.columns - 1) // self.columns if self.filtered else 1
        height = rows * self.cell_h + PAD
        self.configure(scrollregion=(0, 0, max(self.winfo_width(), self.columns * self.cell_w + PAD), height))
        width = self.winfo_width()
        order = self._selection_order()
        for i, photo in enumerate(self.filtered):
            col, row = i % self.columns, i // self.columns
            x = PAD + col * self.cell_w
            y = PAD + row * self.cell_h
            self._draw_cell(photo, x, y, width, order)
        self._notify_selection()

    def _selection_order(self) -> dict[str, int]:
        """1-based click order per selected path, in the order they were picked."""
        ordered = [s for s in self._sel_order if s in self.selection]
        known = set(ordered)
        ordered += [str(p.path) for p in self.filtered
                    if str(p.path) in self.selection and str(p.path) not in known]
        self._sel_order = ordered
        return {s: i + 1 for i, s in enumerate(ordered)}

    def _draw_cell(self, photo: Photo, x: int, y: int, width: int, order: dict[str, int]):
        s = str(photo.path)
        self._cell_origins[s] = (x, y)
        selected = s in self.selection
        cell = (x, y, x + self.cell_w - PAD, y + self.cell_h - PAD)
        if selected:
            self.create_rectangle(cell[0] - 2, cell[1] - 2, cell[2] + 2, cell[3] + 2,
                                  outline="#4a9eff", width=3)
        img = self.tk_images.get(s)
        if img is not None:
            cx = x + (self.thumb_size - img.width()) // 2
            cy = y + (self.thumb_size - img.height()) // 2
            self.create_image(cx, cy, image=img, anchor="nw", tags=("img:" + s,))
        else:
            self.create_rectangle(cell[0], cell[1], cell[0] + self.thumb_size, cell[1] + self.thumb_size,
                                  fill="#2a2a2a", outline="", tags=("ph:" + s,))
            self.create_text(cell[0] + self.thumb_size // 2, cell[1] + self.thumb_size // 2,
                              text="...", fill="#777", tags=("ph:" + s,))
        # flag badge
        if photo.flag == PICK:
            self._draw_pick_star(cell[2], cell[1], "ov:" + s)
        elif photo.flag == REJECT:
            self._draw_reject_x(cell[2], cell[1], "ov:" + s)
        if photo.crop is not None:
            self.create_text(cell[0] + 8, cell[1] + 10, text="⌗", fill="#4a9eff",
                              font=("TkDefaultFont", 12), tags=("ov:" + s,))
        # caption
        self.create_text(cell[0] + self.thumb_size // 2, cell[1] + self.thumb_size + 8,
                         width=self.thumb_size, text=photo.name, anchor="n",
                         fill="#cccccc" if selected else "#999999",
                         font=("TkDefaultFont", 8))
        # selected order marker
        if selected and len(self.selection) > 1:
            self.create_rectangle(cell[0], cell[1], cell[0] + 18, cell[1] + 16,
                                  fill="#4a9eff", outline="", tags=("ov:" + s,))
            self.create_text(cell[0] + 9, cell[1] + 8, text=str(order[s]),
                             fill="white", font=("TkDefaultFont", 7), tags=("ov:" + s,))

    def _draw_pick_star(self, right: int, top: int, tag: str) -> None:
        """Yellow five-pointed star in the top-right corner of the cell."""
        cx, cy, r = right - 10, top + 10, 9
        points: list[float] = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = r if i % 2 == 0 else r * 0.42
            points += [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
        self.create_polygon(*points, fill=STAR_FILL, outline=BADGE_OUTLINE, tags=(tag,))

    def _draw_reject_x(self, right: int, top: int, tag: str) -> None:
        """Red X in the top-right corner of the cell."""
        cx, cy, r = right - 10, top + 10, 6
        for x0, y0, x1, y1 in ((cx - r, cy - r, cx + r, cy + r),
                               (cx - r, cy + r, cx + r, cy - r)):
            self.create_line(x0, y0, x1, y1, fill=FLAG_FILL, width=3,
                             capstyle="round", tags=(tag,))

    # ------------------------------------------------------------- thumbnails
    def set_worker(self, worker) -> None:
        """Install a background ThumbWorker and start polling for results."""
        self.worker = worker
        if worker is not None:
            self.pending.clear()
            self._cancel_poll()
            self._poll_job = self.after(50, self._poll)

    def _cancel_poll(self) -> None:
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None

    def _enqueue(self, photo: Photo, size: int) -> None:
        if self.worker is not None:
            self.worker.submit(photo, size)
        else:
            s = str(photo.path)
            if s not in self.pending:
                self.pending.append(s)

    def _poll(self):
        """UI thread: drain finished worker thumbnails and patch cells."""
        if self.worker is None or not self.winfo_exists():
            return
        for path, _size, img in self.worker.collect(24):
            if path in self._paths and path not in self.tk_images:
                self.update_thumbnail(path, ImageTk.PhotoImage(img))
        self._poll_job = self.after(50, self._poll)

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

    def _pump_idle(self):
        """Fallback thumbnail generation without a worker (idle-time)."""
        if self._pumping:
            return
        self._pumping = True
        try:
            for _ in range(8):
                if not self.pending:
                    break
                path = self.pending.pop(0)
                photo = self._paths.get(path)
                if photo is None:
                    continue
                img = self.cache.get(photo, self.thumb_size)
                if img is None:
                    img = load_thumb(photo, self.thumb_size)
                    if img is not None:
                        self.cache.put(photo, self.thumb_size, img)
                if img is not None:
                    self.update_thumbnail(path, ImageTk.PhotoImage(img))
            if self.pending:
                self.after_idle(self._pump_idle)
        finally:
            self._pumping = False

    def refresh_cell(self, photo: Photo):
        self.refresh_cells([photo])

    def refresh_cells(self, photos: list[Photo]):
        """Metadata changed: invalidate cached thumbs, re-render, redraw badges."""
        for photo in photos:
            self.cache.drop(photo.path)
            self.tk_images.pop(str(photo.path), None)
            if self.worker is not None:
                self.worker.submit(photo, self.thumb_size)
            elif str(photo.path) not in self.pending:
                self.pending.append(str(photo.path))
                self.after_idle(self._pump_idle)
        self._redraw()

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
                self._sel_order.clear()
                self.anchor = None
                self._redraw()
            return
        idx, photo = hit
        s = str(photo.path)
        if event.state & 0x0001:  # shift
            if self.anchor is not None:
                lo, hi = sorted((self.anchor, idx))
                paths = [str(p.path) for p in self.filtered[lo:hi + 1]]
                self.selection = set(paths)
                self._sel_order = paths
            else:
                self.selection = {s}
                self._sel_order = [s]
        elif event.state & 0x0004:  # ctrl
            if s in self.selection:
                self.selection.discard(s)
            else:
                self.selection.add(s)
                if s not in self._sel_order:
                    self._sel_order.append(s)
        else:
            self.selection = {s}
            self._sel_order = [s]
        self.anchor = idx
        self._redraw()

    def _on_drag(self, event):
        # begin rubber-band selection on empty space or extend over cells
        hit = self._photo_at_event(event)
        if hit is None:
            return
        idx, photo = hit
        if self.anchor is not None and event.state & 0x0001:
            lo, hi = sorted((self.anchor, idx))
            paths = [str(p.path) for p in self.filtered[lo:hi + 1]]
            self.selection = set(paths)
            self._sel_order = paths
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
        if str(photo.path) not in self.selection:
            self.selection = {str(photo.path)}
            self._sel_order = [str(photo.path)]
            self.anchor = idx
            self._redraw()
        if self.on_open:
            pass  # context menu is built by the app; forwarded via callback below

    # -------------------------------------------------------------- selection
    def _notify_selection(self):
        if self.on_select:
            self.on_select(self.selected_photos())

    def selected_photos(self) -> list[Photo]:
        return [p for p in self.filtered if str(p.path) in self.selection]

    def select_all(self):
        self.selection = {str(p.path) for p in self.filtered}
        self._sel_order = [str(p.path) for p in self.filtered]
        self._redraw()

    def clear_selection(self):
        self.selection.clear()
        self._sel_order.clear()
        self._redraw()

    def move_selection(self, delta: int):
        if not self.filtered:
            return
        cur = self.anchor if self.anchor is not None else -1
        idx = max(0, min(len(self.filtered) - 1, cur + delta))
        s = str(self.filtered[idx].path)
        self.selection = {s}
        self._sel_order = [s]
        self.anchor = idx
        self._redraw()
        self._scroll_to_index(idx)

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

    def remove_paths(self, paths: list[str]):
        gone = set(paths)
        self.selection -= gone
        self.photos = [p for p in self.photos if str(p.path) not in gone]
        for p in paths:
            self.tk_images.pop(p, None)
        self._apply_filter_and_redraw()
