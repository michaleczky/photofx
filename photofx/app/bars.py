"""Toolbar and status bar of the grid application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from photofx.lib import ui
from photofx.lib.catalog import PICK, REJECT, Photo
from photofx.app.filters import PhotoFilter


class Toolbar:
    """Top toolbar: folder open, rotate, flags, delete, and the filter box."""

    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app)
        self.frame.pack(side="top", fill="x", padx=6, pady=4)

        def btn(text, cmd, icon=None, hint=None):
            return ui.tool_button(self.frame, text, cmd, icon=icon, hint=hint)

        btn("Open folder...", app.open_folder, icon="folder")
        btn("Rotate", lambda: app.rotate_selection(90), icon="rotate",
            hint="Rotate 90 right  ]")
        self.pick_btn = btn("Pick", app.toggle_pick, icon="star", hint="Pick  P")
        self.reject_btn = btn("Reject", app.toggle_reject, icon="close",
                              hint="Reject  X")
        btn("Delete", app.delete_selection, icon="trash", hint="Delete  Del")

        ttk.Label(self.frame, text="Filter:").pack(side="left", padx=(12, 2))
        self.filter_box = ttk.Combobox(self.frame, state="readonly",
                                       values=PhotoFilter.NAMES, width=16)
        self.filter_box.current(0)
        self.filter_box.pack(side="left")
        self.filter_box.bind("<<ComboboxSelected>>", app._filter_changed)

    def current_filter(self) -> str:
        return self.filter_box.get()

    def sync_flags(self, photos: list[Photo]):
        """Press Pick/Reject when the whole selection carries that flag."""
        ui.set_toggled(self.pick_btn,
                       bool(photos) and all(p.flag == PICK for p in photos))
        ui.set_toggled(self.reject_btn,
                       bool(photos) and all(p.flag == REJECT for p in photos))


class StatusBar:
    """One-line status at the bottom of the window."""

    def __init__(self, app, bg: str):
        self.label = tk.Label(app, anchor="w", fg="#aaa", bg=bg, padx=8)
        self.label.pack(side="bottom", fill="x")

    def set(self, text: str):
        self.label.configure(text=text)
