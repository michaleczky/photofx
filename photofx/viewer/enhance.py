"""Enhance pane: the non-destructive edit controls shown beside the photo.

:class:`EnhancePane` builds the top part of the viewer's right pane:
sliders grouped into sections (:data:`GROUPS`), plus Auto and Reset
buttons. Sliders fire :meth:`viewer.live_enhance` continuously while
dragged (live preview) and :meth:`viewer.commit_enhance` on release
(persist). New enhance features slot in by adding their key to
:data:`SLIDERS` and a section to :data:`GROUPS`.
"""

from __future__ import annotations

from tkinter import ttk

from photofx.lib import ui

# key -> (caption, min, max); values live in the sidecar via catalog.EDIT_KEYS
SLIDERS: dict[str, tuple[str, float, float]] = {
    "exposure": ("Exposure", -2.0, 2.0),
    "contrast": ("Contrast", -100, 100),
    "temp": ("Temp", -100, 100),
    "tint": ("Tint", -100, 100),
    "saturation": ("Saturation", -100, 100),
}

# section title -> slider keys, in display order
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Light", ("exposure", "contrast")),
    ("Color", ("temp", "tint", "saturation")),
)

WIDTH = 12        # caption width in characters
SCALE_LEN = 130   # slider length in pixels


class EnhancePane:
    """The viewer's enhance controls: sectioned sliders, Auto, Reset."""

    def __init__(self, viewer):
        self.viewer = viewer
        # no outer padding: the side pane provides it
        self.frame = ttk.Frame(viewer.side_pane, style="TFrame")   # packed by viewer._layout_side_pane
        self._updating = False              # guard: programmatic set is not a drag
        self.scales: dict[str, ttk.Scale] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        for title, keys in GROUPS:
            header = ttk.Label(self.frame, text=title.upper(), foreground=ui.ACCENT)
            header.pack(anchor="w", pady=(8, 2))
            ttk.Separator(self.frame).pack(fill="x")
            for key in keys:
                caption, lo, hi = SLIDERS[key]
                row = ttk.Frame(self.frame)
                row.pack(fill="x", pady=(6, 0))
                ttk.Label(row, text=caption, width=WIDTH, anchor="w").pack(side="left")
                scale = ttk.Scale(row, from_=lo, to=hi, length=SCALE_LEN,
                                  command=lambda v, k=key: self._on_drag(k, v))
                scale.pack(side="left", padx=(2, 4))
                scale.bind("<ButtonRelease-1>",
                           lambda _e, k=key: self._on_release(k))
                value = ttk.Label(row, text="0", width=6, anchor="e")
                value.pack(side="left")
                self.scales[key] = scale
                self.value_labels[key] = value
        buttons = ttk.Frame(self.frame)
        buttons.pack(fill="x", pady=(14, 0))
        ui.tool_button(buttons, "Auto", viewer.auto_enhance,
                       hint="Auto: white balance, exposure, contrast")
        ui.tool_button(buttons, "Reset", viewer.reset_enhance,
                       hint="Reset all enhancements")
        self._show_values()

    # ------------------------------------------------------- viewer events
    def _on_drag(self, key: str, value: str):
        if self._updating:
            return
        self._show_values()
        self.viewer.live_enhance(key, float(value))

    def _on_release(self, key: str):
        if self._updating:
            return
        self.viewer.commit_enhance()

    # ----------------------------------------------------------------- api
    def values(self) -> dict[str, float]:
        """Current slider positions as an edits dict (zero values dropped)."""
        out = {}
        for key, scale in self.scales.items():
            v = float(scale.get())
            if v != 0.0:
                out[key] = v
        return out

    def sync(self, photo):
        """Move the sliders to the photo's stored edits."""
        edits = photo.edits if photo is not None else {}
        self._updating = True
        try:
            for key, scale in self.scales.items():
                scale.set(edits.get(key, 0.0))
        finally:
            self._updating = False
        self._show_values()

    # ------------------------------------------------------------ helpers
    def _show_values(self):
        for key, scale in self.scales.items():
            v = float(scale.get())
            if key == "exposure":
                text = f"{v:+.2f}"
            else:
                text = f"{int(round(v)):+d}"
            self.value_labels[key].configure(text=text)
