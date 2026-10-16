"""Viewer window: composes the image view, crop session and toolbars.

:class:`Viewer` owns the photo list and the current index, and wires the
collaborators together:

- :class:`~photofx.viewer.view.ImageView` — canvas, rendering, zoom and pan
- :class:`~photofx.viewer.crop.CropSession` — crop overlay state and geometry
- :class:`~photofx.viewer.bars.Toolbar` / :class:`~photofx.viewer.bars.CropToolbar`

Everything user-visible (actions, keyboard bindings, the info line,
redraw scheduling) is coordinated here; the collaborators never talk to
each other directly.
"""

from __future__ import annotations

import tkinter as tk

from photofx.lib.catalog import PICK, REJECT, Photo
from photofx.lib import ui
from photofx.lib.ops import apply_rotation
from photofx.viewer.bars import CropToolbar, Toolbar
from photofx.viewer.crop import CropSession
from photofx.viewer.view import DARK, ImageView, ZOOM_STEP

REDRAW_DELAY = 30     # ms debounce: bursts of Configure events coalesce into one


class Viewer(tk.Toplevel):
    """The single-photo window: large view, crop overlay, flags, zoom."""

    def __init__(self, master, photos: list[Photo], index: int,
                 on_change=None, on_delete=None):
        super().__init__(master)
        self.photos = photos
        self.index = index
        self.on_change = on_change      # called with photo after any edit
        self.on_delete = on_delete      # called with photo; viewer closes/advances

        self.view = ImageView(self)
        self.crop = CropSession()
        self.show_original = False
        self._pan: tuple[int, int] | None = None   # last pan press position
        self._show_job = None          # pending debounced redraw
        self._last_size = None         # canvas size the image was last rendered for

        self.title("photofx viewer")
        self.geometry("1100x780")
        self.configure(bg=DARK)
        ui.dark_style(self)
        self.toolbar = Toolbar(self)
        self.crop_toolbar = CropToolbar(self, self.toolbar)

        self._bind_events()
        self.focus_force()
        self._schedule_show()

    # ------------------------------------------------------------ state out
    @property
    def photo(self) -> Photo | None:
        if 0 <= self.index < len(self.photos):
            return self.photos[self.index]
        return None

    @property
    def crop_mode(self) -> bool:
        return self.crop.active

    @property
    def draft(self) -> list[float] | None:
        return self.crop.draft

    @draft.setter
    def draft(self, rect: list[float] | None):
        self.crop.draft = list(rect) if rect is not None else None

    # --------------------------------------------------------------- events
    def _bind_events(self):
        canvas = self.view.canvas
        canvas.bind("<Button-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Left>", lambda e: self.navigate(-1))
        self.bind("<Right>", lambda e: self.navigate(1))
        self.bind("<Escape>", self._exit_crop)
        self.bind("<Return>",
                  lambda e: self.apply_crop() if self.crop.active else None)
        self.bind("p", lambda e: self.set_flag(PICK))
        self.bind("x", lambda e: self.set_flag(REJECT))
        self.bind("u", lambda e: self.set_flag(None))
        self.bind("bracketleft", lambda e: self.rotate(-90))
        self.bind("bracketright", lambda e: self.rotate(90))
        self.bind("<plus>", self.zoom_in)
        self.bind("<equal>", self.zoom_in)
        self.bind("<minus>", self.zoom_out)
        self.bind("<Key-0>", self.zoom_reset)
        self.bind("<Delete>", self.delete_current)

    def _on_configure(self, event):
        size = (self.view.canvas.winfo_width(), self.view.canvas.winfo_height())
        if size == self._last_size:
            return
        self._schedule_show()

    def _on_press(self, event):
        if self.crop.active:
            self.crop.press(self.view.rel(event), self.view.img_box)
        else:
            self._pan = (event.x, event.y)      # start panning

    def _on_motion(self, event):
        if self.crop.active:
            x, y = self.view.rel(event)
            self.crop.motion(x, y, self.view.size)
            self._show(keep_crop=True)
        elif self._pan is not None:             # panning while zoomed in
            dx = event.x - self._pan[0]
            dy = event.y - self._pan[1]
            self._pan = (event.x, event.y)
            self._cancel_show_job()             # move items; no need to re-render
            self.view.pan_by(dx, dy)

    def _on_release(self, event):
        self._pan = None
        self.crop.release()

    def _on_wheel(self, event):
        if self.photo is None:
            return
        factor = ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP
        if self.view.zoom_by(factor, event.x, event.y):
            self._schedule_show()

    # ------------------------------------------------------------ rendering
    def _schedule_show(self):
        if self._show_job is None:
            self._show_job = self.after(REDRAW_DELAY, self._show_scheduled)

    def _show_scheduled(self):
        self._show_job = None
        try:
            if self.winfo_exists():
                self._show(keep_crop=True)
        except tk.TclError:
            pass

    def _cancel_show_job(self):
        if self._show_job is not None:
            try:
                self.after_cancel(self._show_job)
            except tk.TclError:
                pass
            self._show_job = None

    def _show(self, keep_crop=False):
        """Render the current photo, overlay, info line and button states."""
        photo = self.photo
        self.view.clear()
        if photo is None:
            self.view.show_empty()
            return
        if not keep_crop or not self.view.matches(photo):
            self.view.load(photo)
            self.crop.seed(photo)
        sub_rect = None
        if photo.crop is not None and not self.crop.active and not self.show_original:
            sub_rect = photo.crop
        self._last_size = (self.view.canvas.winfo_width(),
                           self.view.canvas.winfo_height())
        self.view.draw(sub_rect)
        if self.crop.active and self.crop.draft is not None:
            self.crop.draw(self.view.canvas, self.view.img_box)
        self._update_info(photo)
        self._sync_buttons()

    def _update_info(self, photo: Photo):
        flags = {"pick": "  PICK", "reject": "  REJECT"}.get(photo.flag, "")
        if self.crop.active:
            crop_note = self.crop.ratio.note()
        elif self.show_original and photo.crop:
            crop_note = "  [original]"
        elif photo.crop:
            crop_note = "  [cropped]"
        else:
            crop_note = ""
        zoom_note = f"  {round(self.view.zoom * 100)}%" if self.view.zoom > 1.005 else ""
        self.toolbar.set_info(
            f"{self.index + 1}/{len(self.photos)}  {photo.name}"
            f"{flags}{crop_note}{zoom_note}")

    def _sync_buttons(self):
        self.toolbar.sync(self.photo, self.show_original, self.crop.active)
        self.crop_toolbar.sync(self.crop.active, self.crop.ratio)

    # ----------------------------------------------------------------- zoom
    def zoom_in(self):
        if self.view.zoom_by(ZOOM_STEP):
            self._schedule_show()

    def zoom_out(self):
        if self.view.zoom_by(1 / ZOOM_STEP):
            self._schedule_show()

    def zoom_reset(self):
        """Fit to window."""
        self.view.zoom_reset()
        self._schedule_show()

    # ------------------------------------------------------------ crop mode
    def _end_crop(self):
        self.crop.exit()
        self.crop_toolbar.set_visible(False)

    def toggle_crop(self):
        photo = self.photo
        if photo is None:
            return
        if self.crop.active:
            self._end_crop()
        else:
            self.crop.enter(photo, self.view.size)
            self.crop_toolbar.set_visible(True)
        self._show(keep_crop=True)

    def _exit_crop(self):
        if self.crop.active:
            self._end_crop()
            self._show(keep_crop=True)
            return "break"

    def set_ratio(self, label: str):
        """Select a crop ratio (clicking the active one returns to free crop)."""
        if not self.crop.active:
            return
        self.crop.select_ratio(label, self.view.size)
        self._show(keep_crop=True)

    def swap_orientation(self):
        """Flip the crop ratio between landscape and portrait."""
        if not self.crop.active:
            return
        self.crop.swap_orientation(self.view.size)
        self._show(keep_crop=True)

    def apply_crop(self):
        value = self.crop.value() if self.crop.active else None
        photo = self.photo
        if photo is None or value is None:
            return
        photo.crop = value
        self._end_crop()
        self.view.zoom_reset()
        self._changed()
        self._show(keep_crop=True)

    def clear_crop(self):
        photo = self.photo
        if photo is None:
            return
        photo.crop = None
        self.crop.draft = None
        self._end_crop()
        self.view.zoom_reset()
        self._changed()
        self._show(keep_crop=True)

    # ------------------------------------------------------------- actions
    def rotate(self, degrees: int):
        photo = self.photo
        if photo is None:
            return
        apply_rotation(photo, degrees)
        self.crop.draft = None
        self.view.invalidate()
        self.view.zoom_reset()
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
        self._photo_changed()

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

    def delete_current(self):
        photo = self.photo
        if photo is None:
            return
        if self.on_delete:
            self.on_delete(photo)

    def navigate(self, delta: int):
        if not self.photos:
            return
        self.index = (self.index + delta) % len(self.photos)
        self._photo_changed()

    # -------------------------------------------------------------- helpers
    def _photo_changed(self):
        """New photo on screen: reset crop, view state and redraw."""
        self.crop.draft = None
        self._end_crop()
        self.view.invalidate()
        self.view.zoom_reset()
        self._show()

    def _changed(self):
        photo = self.photo
        if photo is not None and self.on_change:
            self.on_change(photo)
