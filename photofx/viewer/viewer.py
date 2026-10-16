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
RATIOS = ("original", "4:3", "16:9", "1:1")   # crop-ratio choices


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
        self.ratio_label: str | None = None       # None = free crop, else RATIOS entry
        self.ratio_transposed = False             # True = portrait version of the ratio
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
        self.toolbar = bar
        def btn(text, cmd, icon=None, hint=None):
            return ui.tool_button(bar, text, cmd, icon=icon, hint=hint)
        btn("Prev", lambda: self.navigate(-1), icon="prev", hint="Previous  ←")
        btn("Next", lambda: self.navigate(1), icon="next", hint="Next  →")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        btn("Rotate", lambda: self.rotate(90), icon="rotate", hint="Rotate 90 right  ]")
        self.crop_btn = btn("Crop", self.toggle_crop, icon="crop", hint="Crop overlay")
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
        self._build_crop_bar()

    def _build_crop_bar(self):
        """Crop tools; packed just above the toolbar while crop mode is on."""
        bar = ttk.Frame(self)
        self.crop_bar = bar
        self.ratio_btns = {}
        for label in RATIOS:
            text = "Original" if label == "original" else label
            self.ratio_btns[label] = ui.tool_button(
                bar, text, lambda l=label: self.set_ratio(l),
                hint=f"Crop ratio {label}" if label == "original" else f"Ratio {label}")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        self.orientation_btn = ui.tool_button(
            bar, "Orientation", self.swap_orientation, hint="Swap crop orientation")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        ui.tool_button(bar, "Apply crop", self.apply_crop)
        ui.tool_button(bar, "Clear crop", self.clear_crop)
        self._sync_buttons()

    def _set_crop_bar(self):
        if self.crop_mode:
            self.crop_bar.pack(side="bottom", fill="x", after=self.toolbar)
        else:
            self.crop_bar.pack_forget()

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
            crop_note = self._ratio_note()
        elif self.show_original and photo.crop:
            crop_note = "  [original]"
        elif photo.crop:
            crop_note = "  [cropped]"
        else:
            crop_note = ""
        zoom_note = f"  {round(self.zoom * 100)}%" if self.zoom > 1.005 else ""
        self.info.configure(
            text=f"{self.index + 1}/{len(self.photos)}  {name}{flags}{crop_note}{zoom_note}")
        self._sync_buttons()

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
            self.draft = self._new_rect(start[0], start[1], x, y)
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
            self._enforce_ratio(mode)
        self._show(keep_crop=True)

    # --------------------------------------------------------- crop ratio
    def _ratio_note(self) -> str:
        label = self.ratio_label
        if label is None:
            return ""
        if self.ratio_transposed and ":" in label:
            a, b = label.split(":")
            label = f"{b}:{a}"
        return f"  [{label}]"

    def _effective_ratio(self) -> float | None:
        """Active aspect ratio in *pixel* terms (w/h), or None for free crop."""
        if self.ratio_label is None or self.base is None:
            return None
        if self.ratio_label == "original":
            ratio = self.base.width / self.base.height
        else:
            a, b = self.ratio_label.split(":")
            ratio = float(a) / float(b)
        return 1.0 / ratio if self.ratio_transposed else ratio

    def _fit_ratio(self):
        """Reshape the draft crop to the active ratio, centered inside itself."""
        ratio = self._effective_ratio()
        if ratio is None or self.draft is None or self.base is None:
            return
        bw, bh = self.base.size
        x0, y0, x1, y1 = self.draft
        w, h = (x1 - x0) * bw, (y1 - y0) * bh
        if w <= 0 or h <= 0:
            return
        if w / h > ratio:
            w = h * ratio
        else:
            h = w / ratio
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        nw, nh = w / bw, h / bh
        nx0 = min(max(cx - nw / 2, 0.0), 1.0 - nw)
        ny0 = min(max(cy - nh / 2, 0.0), 1.0 - nh)
        self.draft = [nx0, ny0, nx0 + nw, ny0 + nh]

    def _new_rect(self, sx: float, sy: float, x: float, y: float) -> list[float]:
        """Draft rect from drawing out a new crop; honors the active ratio."""
        ratio = self._effective_ratio()
        if ratio is None or self.base is None:
            return [min(sx, x), min(sy, y), max(sx, x), max(sy, y)]
        bw, bh = self.base.size
        w = max(abs(x - sx) * bw, abs(y - sy) * bh * ratio)
        h = w / ratio
        max_w = (1 - sx if x >= sx else sx) * bw
        max_h = (1 - sy if y >= sy else sy) * bh
        if w > max_w:
            w = max_w
            h = w / ratio
        if h > max_h:
            h = max_h
            w = h * ratio
        ex = sx + (w / bw if x >= sx else -w / bw)
        ey = sy + (h / bh if y >= sy else -h / bh)
        return [min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)]

    def _enforce_ratio(self, mode: str):
        """Keep a drag-resized draft at the active ratio.

        Dragged edges win; the perpendicular dimension follows, anchored to
        the opposite edge (corner drags) or the old center (edge drags).
        """
        ratio = self._effective_ratio()
        if ratio is None or self.base is None or self.draft is None:
            return
        bw, bh = self.base.size
        x0, y0, x1, y1 = self.draft
        horiz = "w" in mode or "e" in mode
        vert = "n" in mode or "s" in mode
        if not (horiz or vert):
            return
        if horiz:
            ax = x0 if "e" in mode else x1          # fixed x edge
            max_w = (1 - ax if "e" in mode else ax) * bw
        if vert:
            ay = y0 if "s" in mode else y1          # fixed y edge
            max_h = (1 - ay if "s" in mode else ay) * bh
        w, h = (x1 - x0) * bw, (y1 - y0) * bh
        if horiz and vert:
            h = w / ratio
            if h > max_h:
                h = max_h
                w = h * ratio
            if w > max_w:
                w = max_w
                h = w / ratio
            if "e" in mode:
                x0, x1 = ax, ax + w / bw
            else:
                x1, x0 = ax, ax - w / bw
            if "s" in mode:
                y0, y1 = ay, ay + h / bh
            else:
                y1, y0 = ay, ay - h / bh
        elif horiz:
            h = w / ratio
            if h > bh:
                h = bh
                w = h * ratio
                if w > max_w:
                    w = max_w
                    h = w / ratio
            cy = (y0 + y1) / 2                      # keep the vertical center
            y0 = cy - h / (2 * bh)
            y1 = y0 + h / bh
            if y0 < 0:
                y0, y1 = 0.0, h / bh
            elif y1 > 1:
                y0, y1 = 1.0 - h / bh, 1.0
            if "e" in mode:
                x0, x1 = ax, ax + w / bw
            else:
                x1, x0 = ax, ax - w / bw
        else:
            w = h * ratio
            if w > bw:
                w = bw
                h = w / ratio
                if h > max_h:
                    h = max_h
                    w = h * ratio
            cx = (x0 + x1) / 2                      # keep the horizontal center
            x0 = cx - w / (2 * bw)
            x1 = x0 + w / bw
            if x0 < 0:
                x0, x1 = 0.0, w / bw
            elif x1 > 1:
                x0, x1 = 1.0 - w / bw, 1.0
            if "s" in mode:
                y0, y1 = ay, ay + h / bh
            else:
                y1, y0 = ay, ay - h / bh
        self.draft = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

    def _crop_release(self, event):
        self._drag = None

    # ------------------------------------------------------------ actions
    def _set_crop_mode(self, on: bool):
        if self.crop_mode == on:
            return
        self.crop_mode = on
        self._set_crop_bar()

    def toggle_crop(self):
        photo = self.photo
        if photo is None:
            return
        self._set_crop_mode(not self.crop_mode)
        if self.crop_mode:
            if self.draft is None:
                photo = self.photo
                self.draft = list(photo.crop) if photo.crop else [0.05, 0.05, 0.95, 0.95]
            self._fit_ratio()
        self._show(keep_crop=True)

    def set_ratio(self, label: str):
        """Select a crop ratio (clicking the active one returns to free crop)."""
        if not self.crop_mode or label not in RATIOS:
            return
        if self.ratio_label == label:
            self.ratio_label = None
            self.ratio_transposed = False
        else:
            self.ratio_label = label
            self.ratio_transposed = False
            self._fit_ratio()
        self._show(keep_crop=True)

    def swap_orientation(self):
        """Flip the active ratio between landscape and portrait."""
        if not self.crop_mode:
            return
        if self.ratio_label is None:
            self.ratio_label = "original"       # free crop: adopt the image aspect first
        self.ratio_transposed = not self.ratio_transposed
        self._fit_ratio()
        self._show(keep_crop=True)

    def _exit_crop(self):
        if self.crop_mode:
            self._set_crop_mode(False)
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
        self._set_crop_mode(False)
        self._reset_view()
        self._changed()
        self._show(keep_crop=True)

    def clear_crop(self):
        photo = self.photo
        if photo is None:
            return
        photo.crop = None
        self.draft = None
        self._set_crop_mode(False)
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
        self._set_crop_mode(False)
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
        self._sync_buttons()
        self._schedule_show()

    def _sync_buttons(self):
        flag = self.photo.flag if self.photo is not None else None
        ui.set_toggled(self.pick_btn, flag == PICK)
        ui.set_toggled(self.reject_btn, flag == REJECT)
        ui.set_toggled(self.original_btn, self.show_original)
        ui.set_toggled(self.crop_btn, self.crop_mode)
        for label, button in self.ratio_btns.items():
            ui.set_toggled(button, self.crop_mode and self.ratio_label == label)
        ui.set_toggled(self.orientation_btn, self.crop_mode and self.ratio_transposed)

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
        self._set_crop_mode(False)
        self._reset_view()
        self._show()

    def _changed(self):
        photo = self.photo
        if photo is not None and self.on_change:
            self.on_change(photo)
