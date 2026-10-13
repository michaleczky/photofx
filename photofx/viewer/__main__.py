"""Standalone viewer application: python -m photofx.viewer [folder]

Opens the full-screen single-photo viewer over a folder. Crop, rotate,
flag and delete work as in the grid app; every change is written to the
photo's JSON sidecar, originals are never modified.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    from photofx.lib.catalog import scan_folder, save_photo
    from photofx.lib.ops import delete_photo
    from photofx.viewer.viewer import Viewer

    argv = sys.argv[1:] if argv is None else argv
    folder = Path(argv[0]) if argv else None

    root = tk.Tk()
    root.withdraw()
    if folder is None:
        chosen = filedialog.askdirectory(title="Choose photo folder")
        if not chosen:
            root.destroy()
            return
        folder = Path(chosen)
    if not folder.is_dir():
        messagebox.showerror("photofx viewer", f"Not a folder: {folder}")
        root.destroy()
        return
    photos = scan_folder(folder)
    if not photos:
        messagebox.showinfo("photofx viewer", "No photos found in that folder.")
        root.destroy()
        return

    def on_change(photo):
        save_photo(photo)

    def on_delete(photo):
        if not messagebox.askyesno("Delete", f"Move {photo.name} to .photofx_trash?"):
            return
        delete_photo(folder, photo)
        viewer.remove_current()
        if not viewer.photos:
            root.destroy()

    viewer = Viewer(root, photos, 0, on_change=on_change, on_delete=on_delete)
    viewer.title(f"photofx viewer — {folder.name}")
    viewer.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
