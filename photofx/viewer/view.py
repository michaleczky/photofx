"""Image canvas for the viewer: display geometry, zoom and pan.

:class:`ImageView` owns everything about *how* the current photo is shown
on its canvas: the fitted size, the zoom multiplier, the pan offset and the
canvas-space box of the displayed image. It knows nothing about crop
overlays or toolbars; its owner tells it which photo (or sub-rectangle of
a photo) to draw.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageTk

from photofx.lib.catalog import Photo
from photofx.lib.edits import apply_edits
from photofx.lib.render import open_rotated

MARGIN = 30          # px around the image in the viewer
DARK = "#101010"     # window and canvas background
ZOOM_STEP = 1.25     # wheel / key zoom factor per step
ZOOM_MAX = 8.0       # zoom is at least 1.0 (fit to window)


class ImageView:
    """The photo canvas: renders the base image fitted, zoomed and panned.

    ``base`` is the rotated, uncropped render of the current photo;
    ``img_box`` is where it ended up on the canvas, in canvas coordinates.
    """

    def __init__(self, master: tk.Misc):
        self.master = master
        self.canvas = tk.Canvas(master, bg=DARK, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.base: Image.Image | None = None
        self.base_key: tuple[str, int] | None = None
        self.edits: dict[str, float] = {}    # sliders shown right now
        self.disp: ImageTk.PhotoImage | None = None
        self.img_box = (0, 0, 0, 0)
        self.zoom = 1.0            # multiplier on the fit-to-window scale
        self.pan_x = 0             # image offset from centered, in canvas px
        self.pan_y = 0

    # ------------------------------------------------------------- loading
    @property
    def size(self) -> tuple[int, int] | None:
        """Size of the loaded base image, or None before one is loaded."""
        return self.base.size if self.base is not None else None

    def matches(self, photo: Photo) -> bool:
        """True when the loaded base is this photo at this rotation."""
        return (self.base is not None
                and self.base_key == (str(photo.path), photo.rotation))

    def load(self, photo: Photo):
        """(Re)render the photo: rotated, uncropped, full resolution.

        The base stays unedited; edits are applied at display size in
        :meth:`draw`, so moving a slider never re-decodes the file and
        the edit math runs on a small image.
        """
        self.base = open_rotated(photo)
        self.base_key = (str(photo.path), photo.rotation)
        self.edits = dict(photo.edits)

    def invalidate(self):
        """Drop the cached render so the next draw reloads the photo."""
        self.base = None
        self.base_key = None

    # -------------------------------------------------------------- drawing
    def clear(self):
        self.canvas.delete("all")

    def show_empty(self):
        self.canvas.create_text(200, 200, text="No photo", fill="#888")

    def draw(self, sub_rect: tuple[float, float, float, float] | None = None):
        """Render the base — or a sub-rectangle of it — fitted to the canvas.

        ``sub_rect`` is [x0, y0, x1, y1] in fractions of the base image,
        used to show the applied crop. Zoom and pan stay in effect; the
        position is clamped so a panned image stays reachable.
        """
        if self.base is None:
            return
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        avail_w, avail_h = cw - 2 * MARGIN, ch - 2 * MARGIN
        bw, bh = self.base.size
        disp_img = self.base
        if sub_rect is not None:
            x0, y0, x1, y1 = sub_rect
            disp_img = self.base.crop(
                (int(x0 * bw), int(y0 * bh), int(x1 * bw), int(y1 * bh)))
        scale = min(avail_w / disp_img.width, avail_h / disp_img.height) * self.zoom
        dw = max(1, int(disp_img.width * scale))
        dh = max(1, int(disp_img.height * scale))

        # centered position plus pan, clamped so the image stays reachable
        ox = (cw - dw) // 2 + self.pan_x
        oy = (ch - dh) // 2 + self.pan_y
        if dw > cw:
            ox = min(0, max(cw - dw, ox))
        else:
            self.pan_x = 0
            ox = (cw - dw) // 2
        if dh > ch:
            oy = min(0, max(ch - dh, oy))
        else:
            self.pan_y = 0
            oy = (ch - dh) // 2
        self.img_box = (ox, oy, ox + dw, oy + dh)

        disp_img = disp_img.resize((dw, dh), Image.LANCZOS)
        disp_img = apply_edits(disp_img, self.edits)
        self.disp = ImageTk.PhotoImage(disp_img)
        self.canvas.create_image(ox, oy, image=self.disp, anchor="nw")

    # ----------------------------------------------------------------- zoom
    def zoom_by(self, factor: float, cx: int | None = None,
                cy: int | None = None) -> bool:
        """Zoom by ``factor``, keeping the (cx, cy) canvas point stationary.

        Returns True when the zoom changed (it is clamped to
        [1.0, ZOOM_MAX]).
        """
        new_zoom = max(1.0, min(ZOOM_MAX, self.zoom * factor))
        if new_zoom == self.zoom:
            return False
        if cx is not None:      # keep the point under the cursor stationary
            ox, oy, ox2, oy2 = self.img_box
            dw, dh = ox2 - ox, oy2 - oy
            cw = max(self.canvas.winfo_width(), 100)
            ch = max(self.canvas.winfo_height(), 100)
            ratio = new_zoom / self.zoom
            rx = (cx - ox) / dw if dw else 0.5
            ry = (cy - oy) / dh if dh else 0.5
            self.pan_x = cx - rx * dw * ratio - (cw - dw * ratio) / 2
            self.pan_y = cy - ry * dh * ratio - (ch - dh * ratio) / 2
        self.zoom = new_zoom
        return True

    def zoom_reset(self):
        """Back to fit-to-window, centered."""
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0

    def pan_by(self, dx: int, dy: int):
        """Shift the displayed image by (dx, dy), clamped to reachable edges."""
        ox, oy, ox2, oy2 = self.img_box
        dw, dh = ox2 - ox, oy2 - oy
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        nx = ox + dx
        ny = oy + dy
        if dw > cw:
            nx = min(0, max(cw - dw, nx))
        else:
            nx = (cw - dw) // 2
        if dh > ch:
            ny = min(0, max(ch - dh, ny))
        else:
            ny = (ch - dh) // 2
        if nx == ox and ny == oy:
            return
        self.canvas.move("all", nx - ox, ny - oy)
        self.img_box = (nx, ny, nx + dw, ny + dh)
        self.pan_x += nx - ox
        self.pan_y += ny - oy

    def rel(self, event) -> tuple[float, float]:
        """Event position as fractions of the displayed image."""
        ox, oy, ox2, oy2 = self.img_box
        dw, dh = ox2 - ox, oy2 - oy
        x = (self.canvas.canvasx(event.x) - ox) / dw
        y = (self.canvas.canvasy(event.y) - oy) / dh
        return x, y
