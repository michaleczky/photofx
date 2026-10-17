"""Toolbars of the viewer window.

:class:`Toolbar` is the always-visible bottom bar; :class:`CropToolbar`
holds the crop tools and is packed just above the main toolbar while
crop mode is on. Each bar builds its own widgets and keeps them in sync
with the state its owner passes in.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from photofx.lib import ui
from photofx.lib.catalog import PICK, REJECT, Photo
from photofx.viewer.crop import RATIOS


class Toolbar:
    """Bottom toolbar: navigation, rotate/crop, zoom, flags, delete."""

    def __init__(self, viewer):
        self.viewer = viewer
        self.frame = ttk.Frame(viewer)
        self.frame.pack(side="bottom", fill="x")

        def btn(text, cmd, icon=None, hint=None):
            return ui.tool_button(self.frame, text, cmd, icon=icon, hint=hint)

        btn("Prev", lambda: viewer.navigate(-1), icon="prev", hint="Previous  ←")
        btn("Next", lambda: viewer.navigate(1), icon="next", hint="Next  →")
        self._separator()
        btn("Rotate", lambda: viewer.rotate(90), icon="rotate",
            hint="Rotate 90 right  ]")
        self.crop_btn = btn("Crop", viewer.toggle_crop, icon="crop",
                            hint="Crop overlay")
        self.enhance_btn = btn("Enhance", viewer.toggle_enhance,
                               hint="Enhance pane  e")
        self.info_btn = btn("Info", viewer.toggle_info, hint="Info pane  i")
        self._separator()
        btn("Zoom in", viewer.zoom_in, icon="zoom-in", hint="Zoom in  + / wheel up")
        btn("Zoom out", viewer.zoom_out, icon="zoom-out",
            hint="Zoom out  - / wheel down")
        btn("Fit", viewer.zoom_reset, hint="Fit to window  0")
        self.original_btn = btn("Original", viewer.toggle_original,
                                hint="Show original (ignore crop)")
        self._separator()
        self.pick_btn = btn("Pick", viewer.toggle_pick, icon="star", hint="Pick  P")
        self.reject_btn = btn("Reject", viewer.toggle_reject, icon="close",
                              hint="Reject  X")
        btn("Delete", viewer.delete_current, icon="trash", hint="Delete  Del")
        self.info = tk.Label(self.frame, fg="#aaa", bg=ui.PANEL, anchor="e")
        self.info.pack(side="right", padx=8)

    def _separator(self):
        ttk.Separator(self.frame, orient="vertical").pack(
            side="left", fill="y", padx=4)

    def set_info(self, text: str):
        self.info.configure(text=text)

    def sync(self, photo: Photo | None, show_original: bool, crop_active: bool,
             enhance_visible: bool = False, info_visible: bool = False):
        """Show the pressed/unpressed state of the toggle buttons."""
        flag = photo.flag if photo is not None else None
        ui.set_toggled(self.pick_btn, flag == PICK)
        ui.set_toggled(self.reject_btn, flag == REJECT)
        ui.set_toggled(self.original_btn, show_original)
        ui.set_toggled(self.crop_btn, crop_active)
        ui.set_toggled(self.enhance_btn, enhance_visible)
        ui.set_toggled(self.info_btn, info_visible)


class CropToolbar:
    """Crop tools; packed just above the main toolbar while cropping."""

    def __init__(self, viewer, main: Toolbar):
        self.frame = ttk.Frame(viewer)      # not packed until crop mode starts
        self.ratio_buttons = {}
        for label in RATIOS:
            text = "Original" if label == "original" else label
            hint = "Crop ratio original" if label == "original" else f"Ratio {label}"
            self.ratio_buttons[label] = ui.tool_button(
                self.frame, text, lambda l=label: viewer.set_ratio(l), hint=hint)
        self._separator()
        self.orientation_btn = ui.tool_button(
            self.frame, "Orientation", viewer.swap_orientation,
            hint="Swap crop orientation")
        self._separator()
        ui.tool_button(self.frame, "Apply crop", viewer.apply_crop)
        ui.tool_button(self.frame, "Clear crop", viewer.clear_crop)
        self._main = main

    def _separator(self):
        ttk.Separator(self.frame, orient="vertical").pack(
            side="left", fill="y", padx=4)

    def set_visible(self, on: bool):
        if on:
            self.frame.pack(side="bottom", fill="x", after=self._main.frame)
        else:
            self.frame.pack_forget()

    def sync(self, active: bool, ratio):
        """Highlight the active ratio button and the swapped orientation."""
        for label, button in self.ratio_buttons.items():
            ui.set_toggled(button, active and ratio.label == label)
        ui.set_toggled(self.orientation_btn, active and ratio.transposed)
