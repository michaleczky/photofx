"""Shared dark theme, tool buttons and tooltips for both applications.

The toolbars are the only ttk surfaces in either app; ``dark_style``
re-skins the clam theme so they match the dark windows instead of
rendering as light-gray default widgets.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from photofx.lib import icons

PANEL = "#252526"          # toolbar / panel background
BUTTON = "#2d2d30"         # idle button
BUTTON_HOVER = "#3d3d44"   # hovered button
BUTTON_PRESSED = "#222226"
FIELD = "#333337"          # entry and combobox fields
FG = "#cccccc"
FG_PLACEHOLDER = "#888888"
FG_ENTRY = "#dddddd"
SEPARATOR = "#3a3a3d"
ACCENT = "#4a9eff"


def dark_style(widget: tk.Misc) -> ttk.Style:
    """Configure the clam theme dark, app-wide (styles are per interpreter)."""
    style = ttk.Style(widget)
    style.theme_use("clam")
    style.configure("TFrame", background=PANEL)
    style.configure("TLabel", background=PANEL, foreground=FG)
    style.configure("TSeparator", background=SEPARATOR)
    style.configure("TButton", background=BUTTON, foreground=FG, borderwidth=0,
                    lightcolor=BUTTON, darkcolor=BUTTON, bordercolor=BUTTON,
                    focusthickness=0, padding=(10, 5))
    style.map("TButton",
              background=[("disabled", BUTTON), ("pressed", BUTTON_PRESSED),
                          ("active", BUTTON_HOVER)],
              lightcolor=[("pressed", BUTTON_PRESSED), ("active", BUTTON_HOVER)],
              darkcolor=[("pressed", BUTTON_PRESSED), ("active", BUTTON_HOVER)],
              bordercolor=[("pressed", BUTTON_PRESSED), ("active", BUTTON_HOVER)],
              foreground=[("disabled", "#666666")])
    style.configure("TEntry", fieldbackground=FIELD, foreground=FG_ENTRY,
                    bordercolor=SEPARATOR, lightcolor=SEPARATOR, darkcolor=SEPARATOR,
                    insertcolor=FG_ENTRY, padding=4)
    style.configure("TCombobox", fieldbackground=FIELD, background=BUTTON,
                    foreground=FG_ENTRY, arrowcolor=FG, bordercolor=SEPARATOR,
                    lightcolor=SEPARATOR, darkcolor=SEPARATOR, padding=4)
    style.map("TCombobox",
              fieldbackground=[("readonly", FIELD)],
              selectbackground=[("readonly", FIELD)],
              selectforeground=[("readonly", FG_ENTRY)])
    # the combobox popdown is a plain Tk listbox styled via the option DB
    widget.option_add("*TCombobox*Listbox.background", FIELD)
    widget.option_add("*TCombobox*Listbox.foreground", FG_ENTRY)
    widget.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    widget.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    return style


def tool_button(bar: tk.Misc, text: str, command, icon: str | None = None,
                hint: str | None = None) -> ttk.Button:
    """Flat toolbar button: icon-only when an icon exists, else a text button.

    Icon-only buttons get a tooltip (``hint`` if given, else ``text``).
    """
    image = icons.load(icon, master=bar) if icon else None
    button = ttk.Button(bar, text="" if image else text, command=command,
                        image=image, padding=(8, 5) if image else (10, 5))
    if image is not None:
        Tooltip(button, hint or text)
    button.pack(side="left", padx=2, pady=3)
    return button


class Tooltip:
    """Small dark tooltip shown after a hover delay."""

    DELAY = 600  # ms

    def __init__(self, widget: tk.Misc, text: str):
        self.widget = widget
        self.text = text
        self._job = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._job = self.widget.after(self.DELAY, self._show)

    def _cancel(self, _event=None):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _show(self):
        self._job = None
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            below = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            if below + 40 > self.widget.winfo_screenheight():
                below = self.widget.winfo_rooty() - 36
        except tk.TclError:
            return
        self._tip = tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tk.Label(tip, text=self.text, justify="center",
                 bg=BUTTON_HOVER, fg="#eeeeee", padx=8, pady=4,
                 font=("TkDefaultFont", 8)).pack()
        try:
            tip.update_idletasks()
            tip.wm_geometry(f"+{x - tip.winfo_reqwidth() // 2}+{below}")
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
