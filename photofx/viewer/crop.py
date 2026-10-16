"""Interactive crop: ratio presets, the draft rectangle and drag geometry.

:class:`CropSession` is the state of the crop overlay for the photo being
viewed: whether it is active, the draft rectangle (fractions of the
rotated, uncropped image) and the in-progress drag. All rectangle math —
ratio fitting, hit zones, resize enforcement — lives here; the window
only feeds it pointer positions and the base image size.
"""

from __future__ import annotations

import tkinter as tk

from photofx.lib.catalog import Photo

RATIOS = ("original", "4:3", "16:9", "1:1")   # crop-ratio choices
HANDLE = 12           # px hit zone for crop borders/corners
MIN_SIZE = 0.02       # smallest crop fraction per axis
DEFAULT_DRAFT = (0.05, 0.05, 0.95, 0.95)
ACCENT = "#4a9eff"


class AspectRatio:
    """A crop-ratio choice; ``label`` is None for a free-form crop.

    Immutable: picking a different preset or swapping orientation returns
    a new instance.
    """

    def __init__(self, label: str | None = None, transposed: bool = False):
        self.label = label
        self.transposed = transposed

    def effective(self, base_size: tuple[int, int] | None) -> float | None:
        """The ratio in *pixel* terms (w/h), or None for a free crop."""
        if self.label is None or base_size is None:
            return None
        bw, bh = base_size
        if self.label == "original":
            ratio = bw / bh
        else:
            a, b = self.label.split(":")
            ratio = float(a) / float(b)
        return 1.0 / ratio if self.transposed else ratio

    def flipped(self) -> AspectRatio:
        """The same ratio in the other orientation."""
        return AspectRatio(self.label, not self.transposed)

    def note(self) -> str:
        """Short info-line form, e.g. ``'  [3:4]'``; empty for a free crop."""
        if self.label is None:
            return ""
        label = self.label
        if self.transposed and ":" in label:
            a, b = label.split(":")
            label = f"{b}:{a}"
        return f"  [{label}]"


class CropSession:
    """State of the crop overlay: draft rect, chosen ratio, active drag."""

    def __init__(self):
        self.active = False
        self.draft: list[float] | None = None     # [x0,y0,x1,y1] rel to image
        self.ratio = AspectRatio()
        self._drag: tuple | None = None

    # -------------------------------------------------------------- session
    def enter(self, photo: Photo, base_size: tuple[int, int] | None):
        """Show the overlay; seed the draft from the photo's crop if any."""
        self.active = True
        if self.draft is None:
            self.seed(photo)
        self.fit_ratio(base_size)

    def exit(self):
        self.active = False

    def seed(self, photo: Photo):
        """Reset the draft: the photo's crop, or most of the image."""
        self.draft = list(photo.crop) if photo.crop else list(DEFAULT_DRAFT)

    def value(self) -> tuple[float, float, float, float] | None:
        """The draft as an applyable crop tuple, or None if too small."""
        if self.draft is None:
            return None
        x0, y0, x1, y1 = self.draft
        if (x1 - x0) < MIN_SIZE or (y1 - y0) < MIN_SIZE:
            return None
        return (x0, y0, x1, y1)

    # ---------------------------------------------------------------- ratio
    def select_ratio(self, label: str, base_size: tuple[int, int] | None):
        """Select a preset; clicking the active one returns to free crop."""
        if label not in RATIOS:
            return
        if label == self.ratio.label:
            self.ratio = AspectRatio()
        else:
            self.ratio = AspectRatio(label)
            self.fit_ratio(base_size)

    def swap_orientation(self, base_size: tuple[int, int] | None):
        """Flip the ratio between landscape and portrait.

        A free crop adopts the image's own aspect first.
        """
        if self.ratio.label is None:
            self.ratio = AspectRatio("original")
        self.ratio = self.ratio.flipped()
        self.fit_ratio(base_size)

    def fit_ratio(self, base_size: tuple[int, int] | None):
        """Reshape the draft to the active ratio, centered inside itself."""
        ratio = self.ratio.effective(base_size)
        if ratio is None or self.draft is None or base_size is None:
            return
        bw, bh = base_size
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

    # ---------------------------------------------------------------- drags
    def hit_zone(self, x: float, y: float, img_box) -> str:
        """Which part of the overlay (x, y) grabs: n/s/e/w edges, 'move' or 'new'."""
        x0, y0, x1, y1 = self.draft
        bw = img_box[2] - img_box[0]
        bh = img_box[3] - img_box[1]
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

    def press(self, rel: tuple[float, float], img_box):
        """Button pressed at image-relative ``rel``: start a drag if it hits."""
        x, y = rel
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return
        zone = self.hit_zone(x, y, img_box)
        if zone == "new":
            self.draft = [x, y, x, y]
        self._drag = (zone, x, y)

    def start_drag(self, mode: str, x: float, y: float):
        """Begin a drag in a given mode ('new', 'move', or an n/s/e/w combo)."""
        self._drag = (mode, x, y)

    def motion(self, x: float, y: float,
                base_size: tuple[int, int] | None):
        """Continue the drag at clamped image-relative (x, y)."""
        if self._drag is None or self.draft is None:
            return
        x = min(max(x, 0.0), 1.0)
        y = min(max(y, 0.0), 1.0)
        mode, *start = self._drag
        x0, y0, x1, y1 = self.draft
        if mode == "new":
            self.draft = self.new_rect(start[0], start[1], x, y, base_size)
        elif mode == "move":
            w, h = x1 - x0, y1 - y0
            nx0 = min(max(x0 + x - start[0], 0.0), 1.0 - w)
            ny0 = min(max(y0 + y - start[1], 0.0), 1.0 - h)
            self.draft = [nx0, ny0, nx0 + w, ny0 + h]
        else:
            if "w" in mode:
                x0 = min(x, x1 - MIN_SIZE)
            if "e" in mode:
                x1 = max(x, x0 + MIN_SIZE)
            if "n" in mode:
                y0 = min(y, y1 - MIN_SIZE)
            if "s" in mode:
                y1 = max(y, y0 + MIN_SIZE)
            self.draft = [x0, y0, x1, y1]
            self._enforce_ratio(mode, base_size)

    def release(self):
        self._drag = None

    def new_rect(self, sx: float, sy: float, x: float, y: float,
                 base_size: tuple[int, int] | None) -> list[float]:
        """Draft rect from drawing out a new crop; honors the active ratio."""
        ratio = self.ratio.effective(base_size)
        if ratio is None or base_size is None:
            return [min(sx, x), min(sy, y), max(sx, x), max(sy, y)]
        bw, bh = base_size
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

    def _enforce_ratio(self, mode: str, base_size: tuple[int, int] | None):
        """Keep a drag-resized draft at the active ratio.

        Dragged edges win; the perpendicular dimension follows, anchored to
        the opposite edge (corner drags) or the old center (edge drags).
        """
        ratio = self.ratio.effective(base_size)
        if ratio is None or self.draft is None or base_size is None:
            return
        bw, bh = base_size
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

    # --------------------------------------------------------------- drawing
    def draw(self, canvas: tk.Canvas, img_box):
        """Paint the overlay: dimmed outside, border, rule-of-thirds guides."""
        ox, oy, ox2, oy2 = img_box
        dw, dh = ox2 - ox, oy2 - oy
        x0, y0, x1, y1 = self.draft
        px = (ox + x0 * dw, oy + y0 * dh, ox + x1 * dw, oy + y1 * dh)
        px0, py0, px1, py1 = px
        outside = (
            (ox, oy, px1, py0),      # top
            (ox, py1, px1, oy2),     # bottom
            (ox, oy, px0, oy2),      # left
            (px1, oy, ox2, oy2),     # right
        )
        for rect in outside:
            canvas.create_rectangle(*rect, fill="#000000", stipple="gray50",
                                    outline="")
        canvas.create_rectangle(*px, outline=ACCENT, width=2)
        gx = [(px[0] + px[2]) / 3, 2 * (px[0] + px[2]) / 3]
        gy = [(px[1] + px[3]) / 3, 2 * (px[1] + px[3]) / 3]
        for x in gx:
            canvas.create_line(x, px[1], x, px[3], fill=ACCENT, dash=(3, 5))
        for y in gy:
            canvas.create_line(px[0], y, px[2], y, fill=ACCENT, dash=(3, 5))
