"""photofx main application window."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from photofx.lib.catalog import PICK, REJECT, Photo, save_photo, scan_folder
from photofx.lib import ui
from photofx.lib.ops import apply_rotation, delete_photo
from photofx.lib.render import ThumbWorker
from photofx.lib import settings
from photofx.app.grid import PhotoGrid
from photofx.viewer.viewer import Viewer

FILTERS = ["All photos", "Picks", "Without rejects", "Rejected", "Unflagged"]
FLAG_BY_LABEL = {"Pick": PICK, "Reject": REJECT}


class App(tk.Tk):
    def __init__(self, restore_folder: bool = True):
        super().__init__()
        self.title("photofx")
        self.geometry("1280x820")
        self.configure(bg="#1e1e1e")
        ui.dark_style(self)

        self.root_folder: Path | None = None
        self.all_photos: list[Photo] = []
        self.filter_name = FILTERS[0]
        self.viewer: Viewer | None = None

        self._build_toolbar()
        self._build_grid()
        self._build_statusbar()
        self._bind_keys()
        if restore_folder:
            self._restore_last_folder()

    # ---------------------------------------------------------------- layout
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=6, pady=4)

        def btn(text, cmd, icon=None, hint=None):
            return ui.tool_button(bar, text, cmd, icon=icon, hint=hint)

        btn("Open folder...", self.open_folder, icon="folder")
        btn("Rotate", lambda: self.rotate_selection(90), icon="rotate",
            hint="Rotate 90 right  ]")
        self.pick_btn = btn("Pick", self.toggle_pick, icon="star", hint="Pick  P")
        self.reject_btn = btn("Reject", self.toggle_reject, icon="close", hint="Reject  X")
        btn("Delete", self.delete_selection, icon="trash", hint="Delete  Del")

        ttk.Label(bar, text="Filter:").pack(side="left", padx=(12, 2))
        self.filter_box = ttk.Combobox(bar, state="readonly", values=FILTERS, width=16)
        self.filter_box.current(0)
        self.filter_box.pack(side="left")
        self.filter_box.bind("<<ComboboxSelected>>", self._filter_changed)

    def _build_grid(self):
        frame = ttk.Frame(self)
        frame.pack(side="top", fill="both", expand=True)
        self.grid = PhotoGrid(frame, thumb_size=170,
                              on_select=self._selection_changed, on_open=self.open_viewer)
        self.grid.scroll.pack(side="right", fill="y")
        self.grid.pack(side="left", fill="both", expand=True)
        self.grid.bind("<Button-3>", self._context_menu, add="+")

    def _build_statusbar(self):
        self.status = tk.Label(self, anchor="w", fg="#aaa", bg="#1e1e1e", padx=8)
        self.status.pack(side="bottom", fill="x")

    def _typing(self) -> bool:
        """True when keyboard focus is in a text field — single-key shortcuts must not fire."""
        return isinstance(self.focus_get(), (tk.Entry, ttk.Entry, ttk.Combobox))

    def _bind_keys(self):
        def key(seq, fn):
            def guarded(_event=None):
                if not self._typing():
                    fn()
            self.bind(seq, guarded)
            self._key_actions[seq] = guarded
        self._key_actions = {}
        key("p", lambda: self.flag_selection(PICK))
        key("x", lambda: self.flag_selection(REJECT))
        key("u", lambda: self.flag_selection(None))
        key("bracketleft", lambda: self.rotate_selection(-90))
        key("bracketright", lambda: self.rotate_selection(90))
        key("<Delete>", self.delete_selection)
        key("<Control-a>", lambda: self.grid.select_all())
        key("<Escape>", lambda: self.grid.clear_selection())
        key("<Right>", lambda: self.grid.move_selection(1))
        key("<Left>", lambda: self.grid.move_selection(-1))
        key("<Down>", lambda: self.grid.move_selection(self.grid.columns))
        key("<Up>", lambda: self.grid.move_selection(-self.grid.columns))

    # ------------------------------------------------------------- folder io
    def _restore_last_folder(self):
        """Open the folder from the last session, or the Pictures directory."""
        folder = settings.default_folder()
        if folder is not None:
            self.open_folder(str(folder), remember=False)

    def open_folder(self, chosen: str | None = None, remember: bool = True):
        if chosen is None:
            start = self.root_folder or settings.default_folder()
            chosen = filedialog.askdirectory(
                title="Choose photo folder", initialdir=str(start) if start else None)
        if not chosen:
            return
        self._set_folder(Path(chosen), remember=remember)

    def _set_folder(self, folder: Path, remember: bool = True):
        if remember:
            settings.save_folder(folder)
        if self.grid.worker is not None:
            self.grid.worker.shutdown()
        self.root_folder = folder
        self.title(f"photofx — {folder.name}")
        self.all_photos = self._scan(folder)
        self.grid.set_worker(ThumbWorker(folder, self.grid.cache))
        self._apply_filter(keep_selection=False)

    def _scan(self, folder: Path) -> list[Photo]:
        """Scan, dropping photos whose name matches a user exclude pattern."""
        excluded = settings.exclude_patterns()
        if not excluded:
            return scan_folder(folder)
        return [p for p in scan_folder(folder)
                if not any(rx.search(p.name) for rx in excluded)]

    def destroy(self):
        if self.grid.worker is not None:
            self.grid.worker.shutdown()
        super().destroy()

    def rescan(self):
        if self.root_folder:
            self.all_photos = self._scan(self.root_folder)
            self._apply_filter()

    # -------------------------------------------------------------- filtering
    def _filter_changed(self, _event=None):
        self.filter_name = self.filter_box.get()
        self._apply_filter()

    def _photo_matches(self, photo: Photo) -> bool:
        f = self.filter_name
        if f == "Picks" and photo.flag != PICK:
            return False
        if f == "Rejected" and photo.flag != REJECT:
            return False
        if f == "Without rejects" and photo.flag == REJECT:
            return False
        if f == "Unflagged" and photo.flag is not None:
            return False
        return True

    def _apply_filter(self, keep_selection=True):
        visible = [p for p in self.all_photos if self._photo_matches(p)]
        self.grid.set_photos(visible, keep_selection=keep_selection)
        self._update_status()

    # ------------------------------------------------------------ operations
    def _each_selected(self, fn):
        photos = self.grid.selected_photos()
        for photo in photos:
            fn(photo)
            save_photo(photo)
        self.grid.refresh_cells(photos)
        self._update_status()
        return photos

    def rotate_selection(self, degrees: int):
        self._each_selected(lambda p: apply_rotation(p, degrees))

    def flag_selection(self, flag: str | None):
        self._each_selected(lambda p: setattr(p, "flag", flag))

    def toggle_pick(self):
        self._toggle_flag(PICK)

    def toggle_reject(self):
        self._toggle_flag(REJECT)

    def _toggle_flag(self, flag: str):
        """Clicking Pick/Reject: set on the whole selection, or clear when already set."""
        photos = self.grid.selected_photos()
        if not photos:
            return
        if all(p.flag == flag for p in photos):
            self._each_selected(lambda p: setattr(p, "flag", None))
        else:
            self._each_selected(lambda p: setattr(p, "flag", flag))

    def _sync_flag_buttons(self):
        photos = self.grid.selected_photos()
        ui.set_toggled(self.pick_btn, bool(photos) and all(p.flag == PICK for p in photos))
        ui.set_toggled(self.reject_btn, bool(photos) and all(p.flag == REJECT for p in photos))

    def delete_selection(self):
        photos = self.grid.selected_photos()
        if not photos:
            return
        names = ", ".join(p.name for p in photos[:5])
        more = f" ... and {len(photos) - 5} more" if len(photos) > 5 else ""
        if not messagebox.askyesno(
                "Delete",
                f"Move {len(photos)} photo(s) to the .photofx_trash folder?\n\n{names}{more}\n\n"
                "Originals are moved, not destroyed — you can restore them from the folder."):
            return
        for photo in photos:
            delete_photo(self.root_folder, photo)
            self._purge_thumb(photo)
        gone = [str(p.path) for p in photos]
        self.all_photos = [p for p in self.all_photos if str(p.path) not in set(gone)]
        self.grid.remove_paths(gone)
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.photos = [p for p in self.viewer.photos if str(p.path) not in set(gone)]
            if self.viewer.photo is None:
                self.viewer.navigate(0)
        self._update_status()

    # -------------------------------------------------------------- viewer
    def open_viewer(self, photo: Photo):
        visible = self.grid.filtered
        try:
            index = next(i for i, p in enumerate(visible) if p is photo)
        except StopIteration:
            index, visible = 0, [photo]
        self.viewer = Viewer(self, list(visible), index,
                             on_change=self._viewer_changed, on_delete=self._viewer_delete)

    def _viewer_changed(self, photo: Photo):
        save_photo(photo)
        self.grid.cache.drop(photo.path)
        self.grid.refresh_cell(photo)
        self._update_status()

    def _viewer_delete(self, photo: Photo):
        if not messagebox.askyesno("Delete", f"Move {photo.name} to .photofx_trash?"):
            return
        delete_photo(self.root_folder, photo)
        self._purge_thumb(photo)
        gone = str(photo.path)
        self.all_photos = [p for p in self.all_photos if str(p.path) != gone]
        self.grid.remove_paths([gone])
        viewer = self.viewer
        if viewer is not None and viewer.winfo_exists():
            viewer.remove_current()
            if not viewer.photos:
                viewer.destroy()

    def _purge_thumb(self, photo: Photo):
        if self.grid.worker is not None:
            self.grid.worker.disk.purge(photo.path)

    # -------------------------------------------------------- context menu
    def _context_menu(self, event):
        hit = self.grid._photo_at_event(event)
        if hit is None:
            return
        idx, photo = hit
        if str(photo.path) not in self.grid.selection:
            self.grid.selection = {str(photo.path)}
            self.grid.anchor = idx
            self.grid._redraw()
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open in viewer", command=lambda: self.open_viewer(photo))
        menu.add_separator()
        menu.add_command(label="Pick", command=lambda: self.flag_selection(PICK))
        menu.add_command(label="Reject", command=lambda: self.flag_selection(REJECT))
        menu.add_command(label="Clear flag", command=lambda: self.flag_selection(None))
        menu.add_separator()
        menu.add_command(label="Rotate", command=lambda: self.rotate_selection(90))
        menu.add_separator()
        menu.add_command(label="Delete...", command=self.delete_selection)
        menu.tk_popup(event.x_root, event.y_root)

    # --------------------------------------------------------------- status
    def _selection_changed(self, _photos):
        self._update_status()

    def _update_status(self):
        total = len(self.all_photos)
        visible = len(self.grid.filtered)
        sel = self.grid.selected_photos()
        if len(sel) == 1:
            p = sel[0]
            info = p.name
            if p.flag == PICK:
                info += "  ★"
            elif p.flag == REJECT:
                info += "  ✕"
            if p.rotation:
                info += f"  ↻{p.rotation}°"
            if p.crop:
                info += "  [cropped]"
        elif sel:
            info = f"{len(sel)} selected"
        else:
            info = "Click to select · Ctrl-click to add · Shift-click for ranges · double-click to view"
        self.status.configure(
            text=f"{visible} / {total} photos · {len(sel)} selected   |   {info}")
        self._sync_flag_buttons()


def main():
    app = App()
    app.mainloop()
