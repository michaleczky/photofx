"""Viewer: large single-photo window with rotate, crop overlay, flags."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from photofx.lib.catalog import PICK, REJECT, Photo
from photofx.lib import ui
from photofx.lib.ops import apply_rotation
from photofx.lib.render import open_rotated

MARGIN = 30          # px around the image in the viewer
HANDLE = 12           # px hit zone for crop borders/corners
DARK = "#101010"
ZOOM_STEP = 1.25      # wheel / key zoom factor per step
ZOOM_MAX = 8.0        # zoom is at least 1.0 (fit to window)


class Viewer(tk.Toplevel):
    def __init__(self, master, photos: list[Photo], index: int, on_change=None, on_delete=None):
        super().__init__(master)
        self.photos = photos
        self.index = index
        self.on_change = on_change      # called with photo after any edit
        self.on_delete = on_delete      # called with photo; viewer closes/advances

        self.base: Image.Image | None = None      # rotated, uncropped render
        self.disp: ImageTk.PhotoImage | None = None
        self.img_box = (0, 0, 0, 0)               # canvas coords of displayed image
        self.crop_mode = False
        self.draft: list[float] | None = None     # [x0,y0,x1,y1] rel to rotated image
        self._drag: tuple | None = None
        self._show_job = None      # pending debounced redraw
        self._last_size = None     # canvas size the image was last rendered for
        self.zoom = 1.0            # multiplier on the fit-to-window scale
        self.pan_x = 0             # image offset from centered, in canvas px
        self.pan_y = 0
        self.show_original = False

        self.title("photofx viewer")
        self.geometry("1100x780")
        self.configure(bg=DARK)
        ui.dark_style(self)
        self.canvas = tk.Canvas(self, bg=DARK, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._build_toolbar()

        self.canvas.bind("<Button-1>", self._crop_press)
        self.canvas.bind("<B1-Motion>", self._crop_motion)
        self.canvas.bind("<ButtonRelease-1>", self._crop_release)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Left>", lambda e: self.navigate(-1))
        self.bind("<Right>", lambda e: self.navigate(1))
        self.bind("<Escape>", self._exit_crop)
        self.bind("<Return>", lambda e: self.apply_crop() if self.crop_mode else None)
        self.bind("p", lambda e: self.set_flag(PICK))
        self.bind("x", lambda e: self.set_flag(REJECT))
        self.bind("u", lambda e: self.set_flag(None))
        self.bind("bracketleft", lambda e: self.rotate(-90))
        self.bind("bracketright", lambda e: self.rotate(90))
        self.bind("<plus>", lambda e: self._zoom_by(ZOOM_STEP))
        self.bind("<equal>", lambda e: self._zoom_by(ZOOM_STEP))
        self.bind("<minus>", lambda e: self._zoom_by(1 / ZOOM_STEP))
        self.bind("<Key-0>", lambda e: self._zoom_reset())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Delete>", self._delete_current)
        self.focus_force()
        self._schedule_show()

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x")
        def btn(text, cmd, icon=None, hint=None):
            return ui.tool_button(bar, text, cmd, icon=icon, hint=hint)
        btn("Prev", lambda: self.navigate(-1), icon="prev", hint="Previous  ←")
        btn("Next", lambda: self.navigate(1), icon="next", hint="Next  →")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        btn("Rotate", lambda: self.rotate(90), icon="rotate", hint="Rotate 90 right  ]")
        btn("Crop", self.toggle_crop, icon="crop", hint="Crop overlay")
        btn("Apply crop", self.apply_crop)
        btn("Clear crop", self.clear_crop)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        btn("Zoom in", self.zoom_in, icon="zoom-in", hint="Zoom in  + / wheel up")
        btn("Zoom out", self.zoom_out, icon="zoom-out", hint="Zoom out  - / wheel down")
        btn("Fit", self._zoom_reset, hint="Fit to window  0")
        self.original_btn = btn("Original", self.toggle_original,
                                hint="Show original (ignore crop)")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        self.pick_btn = btn("Pick", self.toggle_pick, icon="star", hint="Pick  P")
        self.reject_btn = btn("Reject", self.toggle_reject, icon="close", hint="Reject  X")
        btn("Delete", self._delete_current, icon="trash", hint="Delete  Del")
        self.info = tk.Label(bar, fg="#aaa", bg=ui.PANEL, anchor="e")
        self.info.pack(side="right", padx=8)

    # ------------------------------------------------------------ rendering
    def _on_configure(self, event):
        size = (self.canvas.winfo_width(), self.canvas.winfo_height())
        if size == self._last_size:
            return
        self._schedule_show()

    def _schedule_show(self):
        """Debounced redraw: bursts of Configure events coalesce into one."""
        if self._show_job is None:
            self._show_job = self.after(30, self._show_scheduled)

    def _show_scheduled(self):
        self._show_job = None
        try:
            if self.winfo_exists():
                self._show(keep_crop=True)
        except tk.TclError:
            pass

    @property
    def photo(self) -> Photo | None:
        if 0 <= self.index < len(self.photos):
            return self.photos[self.index]
        return None

    def _show(self, keep_crop=False):
        photo = self.photo
        self.canvas.delete("all")
        if photo is None:
            self.canvas.create_text(200, 200, text="No photo", fill="#888")
            return
        if not keep_crop or self.base is None or getattr(self, "_base_key", None) != (str(photo.path), photo.rotation):
            self.base = open_rotated(photo)
            self._base_key = (str(photo.path), photo.rotation)
            self.draft = list(photo.crop) if photo.crop else [0.05, 0.05, 0.95, 0.95]

        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        self._last_size = (self.canvas.winfo_width(), self.canvas.winfo_height())
        avail_w, avail_h = cw - 2 * MARGIN, ch - 2 * MARGIN
        bw, bh = self.base.size

        disp_img = self.base
        if photo.crop is not None and not self.crop_mode and not self.show_original:
            x0, y0, x1, y1 = photo.crop
            disp_img = self.base.crop((int(x0 * bw), int(y0 * bh), int(x1 * bw), int(y1 * bh)))
            scale = min(avail_w / disp_img.width, avail_h / disp_img.height) * self.zoom
            dw, dh = max(1, int(disp_img.width * scale)), max(1, int(disp_img.height * scale))
        else:
            scale = min(avail_w / bw, avail_h / bh) * self.zoom
            dw, dh = max(1, int(bw * scale)), max(1, int(bh * scale))

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

        self.disp = ImageTk.PhotoImage(disp_img.resize((dw, dh), Image.LANCZOS))
        self.canvas.create_image(ox, oy, image=self.disp, anchor="nw")

        if self.crop_mode and self.draft is not None:
            self._draw_overlay()
        name = photo.name
        flags = {"pick": "  PICK", "reject": "  REJECT"}.get(photo.flag, "")
        if self.crop_mode:
            crop_note = ""
        elif self.show_original and photo.crop:
            crop_note = "  [original]"
        elif photo.crop:
            crop_note = "  [cropped]"
        else:
            crop_note = ""
        zoom_note = f"  {round(self.zoom * 100)}%" if self.zoom > 1.005 else ""
        self.info.configure(
            text=f"{self.index + 1}/{len(self.photos)}  {name}{flags}{crop_note}{zoom_note}")
        self._sync_flag_buttons()

    # ----------------------------------------------------------------- zoom
    def zoom_in(self):
        self._zoom_by(ZOOM_STEP)

    def zoom_out(self):
        self._zoom_by(1 / ZOOM_STEP)

    def _zoom_reset(self):
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0
        self._schedule_show()

    def _reset_view(self):
        """New photo or changed view: back to fit-to-window."""
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0

    def _on_wheel(self, event):
        self._zoom_by(ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP,
                      event.x, event.y)

    def _zoom_by(self, factor, cx=None, cy=None):
        if self.photo is None:
            return
        new_zoom = max(1.0, min(ZOOM_MAX, self.zoom * factor))
        if new_zoom == self.zoom:
            return
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
        self._schedule_show()

    def _cancel_show_job(self):
        if self._show_job is not None:
            try:
                self.after_cancel(self._show_job)
            except tk.TclError:
                pass
            self._show_job = None

    def _pan_by(self, dx, dy):
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
        self._cancel_show_job()  # move items; no need to re-render
        self.canvas.move("all", nx - ox, ny - oy)
        self.img_box = (nx, ny, nx + dw, ny + dh)
        self.pan_x += nx - ox
        self.pan_y += ny - oy

    # -------------------------------------------------------- crop overlay
    def _draw_overlay(self):
        ox, oy, ox2, oy2 = self.img_box
        dw, dh = ox2 - ox, oy2 - oy
        x0, y0, x1, y1 = self.draft
        px = (ox + x0 * dw, oy + y0 * dh, ox + x1 * dw, oy + y1 * dh)
        px0, py0, px1, py1 = px
        outside = (
            (ox, oy, px1, py0),      # top
            (ox, py1, px1, oy2),     # bottom
            (ox, oy, px0, oy2),      # left
            (px1, oy, ox2, oy2),    # right
        )
        for rect in outside:
            self.canvas.create_rectangle(*rect, fill="#000000", stipple="gray50", outline="")
        self.canvas.create_rectangle(*px, outline="#4a9eff", width=2)
        # rule-of-thirds guides
        gx = [(px[0] + px[2]) / 3, 2 * (px[0] + px[2]) / 3]
        gy = [(px[1] + px[3]) / 3, 2 * (px[1] + px[3]) / 3]
        for x in gx:
            self.canvas.create_line(x, px[1], x, px[3], fill="#4a9eff", dash=(3, 5))
        for y in gy:
            self.canvas.create_line(px[0], y, px[2], y, fill="#4a9eff", dash=(3, 5))

    def _rel(self, event) -> tuple[float, float]:
        ox, oy, ox2, oy2 = self.img_box
        dw, dh = ox2 - ox, oy2 - oy
        x = (self.canvas.canvasx(event.x) - ox) / dw
        y = (self.canvas.canvasy(event.y) - oy) / dh
        return x, y

    def _hit_zone(self, x: float, y: float) -> str:
        x0, y0, x1, y1 = self.draft
        bw, bh = self.img_box[2] - self.img_box[0], self.img_box[3] - self.img_box[1]
        hx, hy = HANDLE / bw, HANDLE / bh
        left = abs(x - x0) < hx and y0 - hy <= y <= y1 + hy
        right = abs(x - x1) < hx and y0 - hy <= y <= y1 + hy
        top = abs(y - y0) < hy and x0 - hx <= x <= x1 + hx
        bottom = abs(y - y1) < hy and x0 - hx <= x <= x1 + hx
        zone = ""
        if left:
            zone += "w"
        if right:
            zone += "e"
        if top:
            zone += "n"
        if bottom:
            zone += "s"
        if zone:
            return zone
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return "new"

    def _crop_press(self, event):
        if not self.crop_mode:
            self._drag = (event.x, event.y)     # start panning
            return
        x, y = self._rel(event)
        ox, oy, ox2, oy2 = self.img_box
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return
        zone = self._hit_zone(x, y)
        if zone == "new":
            self.draft = [x, y, x, y]
            self._drag = ("new", x, y)
        elif zone == "move":
            self._drag = ("move", x, y)
        else:
            self._drag = (zone, x, y)

    def _crop_motion(self, event):
        if self._drag is None:
            return
        if not self.crop_mode:                 # panning while zoomed in
            dx = event.x - self._drag[0]
            dy = event.y - self._drag[1]
            self._drag = (event.x, event.y)
            self._pan_by(dx, dy)
            return
        x, y = self._rel(event)
        ox, oy, ox2, oy2 = self.img_box
        x = min(max(x, 0.0), 1.0)
        y = min(max(y, 0.0), 1.0)
        mode, *start = self._drag
        x0, y0, x1, y1 = self.draft
        if mode == "new":
            self.draft = [min(start[0], x), min(start[1], y), max(start[0], x), max(start[1], y)]
        elif mode == "move":
            w, h = x1 - x0, y1 - y0
            nx0 = min(max(x0 + x - start[0], 0.0), 1.0 - w)
            ny0 = min(max(y0 + y - start[1], 0.0), 1.0 - h)
            self.draft = [nx0, ny0, nx0 + w, ny0 + h]
        else:
            if "w" in mode:
                x0 = min(x, x1 - 0.02)
            if "e" in mode:
                x1 = max(x, x0 + 0.02)
            if "n" in mode:
                y0 = min(y, y1 - 0.02)
            if "s" in mode:
                y1 = max(y, y0 + 0.02)
            self.draft = [x0, y0, x1, y1]
        self._show(keep_crop=True)

    def _crop_release(self, event):
        self._drag = None

    # ------------------------------------------------------------ actions
    def toggle_crop(self):
        photo = self.photo
        if photo is None:
            return
        self.crop_mode = not self.crop_mode
        if self.crop_mode and self.draft is None:
            self.draft = list(photo.crop) if photo.crop else [0.05, 0.05, 0.95, 0.95]
        self._show(keep_crop=True)

    def _exit_crop(self):
        if self.crop_mode:
            self.crop_mode = False
            self._show(keep_crop=True)
            return "break"

    def apply_crop(self):
        photo = self.photo
        if photo is None or not self.crop_mode or self.draft is None:
            return
        x0, y0, x1, y1 = self.draft
        if (x1 - x0) < 0.02 or (y1 - y0) < 0.02:
            return
        photo.crop = (x0, y0, x1, y1)
        self.crop_mode = False
        self._reset_view()
        self._changed()
        self._show(keep_crop=True)

    def clear_crop(self):
        photo = self.photo
        if photo is None:
            return
        photo.crop = None
        self.draft = None
        self.crop_mode = False
        self._reset_view()
        self._changed()
        self._show(keep_crop=True)

    def rotate(self, degrees: int):
        photo = self.photo
        if photo is None:
            return
        apply_rotation(photo, degrees)
        self.draft = None
        self._base_key = None
        self._reset_view()
        self._changed()
        self._show(keep_crop=True)

    def remove_current(self):
        """Drop the current photo from the list and land on a valid index."""
        photo = self.photo
        if photo is None:
            return
        self.photos = [p for p in self.photos if p is not photo]
        if self.index >= len(self.photos):
            self.index = max(0, len(self.photos) - 1)
        self.draft = None
        self.crop_mode = False
        self._base_key = None
        self._reset_view()
        self._show()

    def set_flag(self, flag: str | None):
        photo = self.photo
        if photo is None:
            return
        photo.flag = flag
        self._changed()
        self._show(keep_crop=True)

    def toggle_pick(self):
        self._toggle_flag(PICK)

    def toggle_reject(self):
        self._toggle_flag(REJECT)

    def _toggle_flag(self, flag: str):
        """Clicking Pick/Reject: set it (dropping the other), or clear when already set."""
        photo = self.photo
        if photo is None:
            return
        photo.flag = None if photo.flag == flag else flag
        self._changed()
        self._show(keep_crop=True)

    def toggle_original(self):
        self.show_original = not self.show_original
        self._sync_flag_buttons()
        self._schedule_show()

    def _sync_flag_buttons(self):
        flag = self.photo.flag if self.photo is not None else None
        ui.set_toggled(self.pick_btn, flag == PICK)
        ui.set_toggled(self.reject_btn, flag == REJECT)
        ui.set_toggled(self.original_btn, self.show_original)

    def _delete_current(self):
        photo = self.photo
        if photo is None:
            return
        if self.on_delete:
            self.on_delete(photo)

    def navigate(self, delta: int):
        if not self.photos:
            return
        self.index = (self.index + delta) % len(self.photos)
        self.draft = None
        self._base_key = None
        self.crop_mode = False
        self._reset_view()
        self._show()

    def _changed(self):
        photo = self.photo
        if photo is not None and self.on_change:
            self.on_change(photo)
