"""Info pane: the metadata of the current photo, shown beside the image.

:class:`InfoPane` builds the lower part of the viewer's right pane:
one section per :func:`photofx.lib.exif.photo_info` group, each a header
plus label/value rows. :meth:`sync` rebuilds the rows for a photo, so
the pane always shows the photo on screen.
"""

from __future__ import annotations

from tkinter import ttk

from photofx.lib import ui
from photofx.lib.exif import photo_info

LABEL_WIDTH = 12   # label width in characters, like the enhance captions
VALUE_WRAP = 180    # px at which long values (lens names) wrap


class InfoPane:
    """The viewer's photo info: sectioned file and camera metadata."""

    def __init__(self, viewer):
        self.viewer = viewer
        # no outer padding: the side pane provides it
        self.frame = ttk.Frame(viewer.side_pane, style="TFrame")   # packed by viewer._layout_side_pane
        self.body = ttk.Frame(self.frame)
        self.body.pack(anchor="n")
        self.sync(None)

    # ----------------------------------------------------------------- api
    def sync(self, photo):
        """Rebuild the rows for ``photo`` (nothing shown when None)."""
        for child in self.body.winfo_children():
            child.destroy()
        if photo is None:
            return
        for title, rows in photo_info(photo):
            header = ttk.Label(self.body, text=title.upper(),
                               foreground=ui.ACCENT)
            header.pack(anchor="w", pady=(8, 2))
            ttk.Separator(self.body).pack(fill="x")
            for label, value in rows:
                row = ttk.Frame(self.body)
                row.pack(fill="x", pady=(6, 0))
                ttk.Label(row, text=label, width=LABEL_WIDTH,
                          anchor="w").pack(side="left")
                ttk.Label(row, text=value, wraplength=VALUE_WRAP,
                          anchor="w", justify="left").pack(side="left")
