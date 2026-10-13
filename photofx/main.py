"""photofx main application window."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .catalog import PICK, REJECT, Photo, move_to_trash, save_photo, scan_folder
from . import icons
from .grid import PhotoGrid
from .render import ThumbWorker
from .viewer import Viewer

FILTERS = ["All photos", "Picks", "Without rejects", "Rejected", "Unflagged", "Untagged"]
FLAG_BY_LABEL = {"Pick": PICK, "Reject": REJECT}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("photofx")
        self.geometry("1280x820")
        self.configure(bg="#1e1e1e")
        ttk.Style(self).theme_use("clam")

        self.root_folder: Path | None = None
        self.all_photos: list[Photo] = []
        self.filter_name = FILTERS[0]
        self.tag_query = ""
        self.viewer: Viewer | None = None

        self._build_toolbar()
        self._build_grid()
        self._build_statusbar()
        self._bind_keys()

    # ---------------------------------------------------------------- layout
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=6, pady=4)

        def btn(text, cmd, icon=None):
            image = icons.load(icon, master=bar) if icon else None
            ttk.Button(bar, text=text, command=cmd, image=image,
                       compound="left" if image else None).pack(side="left", padx=2)

        btn("Open folder…", self.open_folder, icon="folder")
        btn("Rotate left", lambda: self.rotate_selection(-90), icon="arrow-left")
        btn("Rotate right", lambda: self.rotate_selection(90), icon="arrow-right")
        btn("Pick", lambda: self.flag_selection(PICK), icon="star")
        btn("Reject", lambda: self.flag_selection(REJECT), icon="close")
        btn("Clear flag", lambda: self.flag_selection(None), icon="star-off")
        btn("Delete", self.delete_selection, icon="trash")

        ttk.Label(bar, text="Tag:").pack(side="left", padx=(12, 2))
        self.tag_entry = ttk.Entry(bar, width=16)
        self.tag_entry.pack(side="left")
        self.tag_entry.insert(0, "add tag…")
        self.tag_entry.bind("<FocusIn>", self._tag_focus_in)
        self.tag_entry.bind("<Return>", self._tag_entered)
        btn("Add tag", self._add_tag_from_entry)
        btn("Remove tag", self._remove_tag_from_entry)

        ttk.Label(bar, text="Filter:").pack(side="left", padx=(12, 2))
        self.filter_box = ttk.Combobox(bar, state="readonly", values=FILTERS, width=16)
        self.filter_box.current(0)
        self.filter_box.pack(side="left")
        self.filter_box.bind("<<ComboboxSelected>>", self._filter_changed)

        self.tag_filter_entry = ttk.Entry(bar, width=14)
        self.tag_filter_entry.insert(0, "filter by tag…")
        self.tag_filter_entry.bind("<FocusIn>", lambda e: self._clear_placeholder(self.tag_filter_entry, "filter by tag…"))
        self.tag_filter_entry.bind("<Return>", self._tag_filter_entered)
        self.tag_filter_entry.bind("<FocusOut>", lambda e: self._restore_placeholder(self.tag_filter_entry, "filter by tag…"))
        self.tag_filter_entry.pack(side="left", padx=4)

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
            self.bind(seq, lambda e: None if self._typing() else fn())
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
    def open_folder(self, chosen: str | None = None):
        if chosen is None:
            chosen = filedialog.askdirectory(title="Choose photo folder")
        if not chosen:
            return
        self._set_folder(Path(chosen))

    def _set_folder(self, folder: Path):
        if self.grid.worker is not None:
            self.grid.worker.shutdown()
        self.root_folder = folder
        self.title(f"photofx — {folder.name}")
        self.all_photos = scan_folder(folder)
        self.grid.set_worker(ThumbWorker(folder, self.grid.cache))
        self._apply_filter(keep_selection=False)

    def destroy(self):
        if self.grid.worker is not None:
            self.grid.worker.shutdown()
        super().destroy()

    def rescan(self):
        if self.root_folder:
            self.all_photos = scan_folder(self.root_folder)
            self._apply_filter()

    # -------------------------------------------------------------- filtering
    def _filter_changed(self, _event=None):
        self.filter_name = self.filter_box.get()
        self._apply_filter()

    def _tag_filter_entered(self, _event=None):
        text = self.tag_filter_entry.get().strip()
        if text == "filter by tag…":
            text = ""
        self.tag_query = text.lower()
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
        if f == "Untagged" and photo.tags:
            return False
        if self.tag_query:
            wanted = [w.strip().lstrip("#") for w in self.tag_query.split(",") if w.strip()]
            if wanted and not any(w in photo.tags for w in wanted):
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
        def rotate(photo: Photo):
            photo.rotation = (photo.rotation + degrees) % 360
            if photo.crop is not None:
                x0, y0, x1, y1 = photo.crop
                if degrees % 360 == 90:
                    photo.crop = (1 - y1, x0, 1 - y0, x1)
                elif degrees % 360 == 270:
                    photo.crop = (y0, 1 - x1, y1, 1 - x0)
                elif degrees % 360 == 180:
                    photo.crop = (1 - x1, 1 - y1, 1 - x0, 1 - y0)
        self._each_selected(rotate)

    def flag_selection(self, flag: str | None):
        self._each_selected(lambda p: setattr(p, "flag", flag))

    def delete_selection(self):
        photos = self.grid.selected_photos()
        if not photos:
            return
        names = ", ".join(p.name for p in photos[:5])
        more = f" … and {len(photos) - 5} more" if len(photos) > 5 else ""
        if not messagebox.askyesno(
                "Delete",
                f"Move {len(photos)} photo(s) to the .photofx_trash folder?\n\n{names}{more}\n\n"
                "Originals are moved, not destroyed — you can restore them from the folder."):
            return
        for photo in photos:
            if self.root_folder:
                move_to_trash(self.root_folder, photo)
            else:
                move_to_trash(photo.path.parent, photo)
            self._purge_thumb(photo)
        gone = [str(p.path) for p in photos]
        self.all_photos = [p for p in self.all_photos if str(p.path) not in set(gone)]
        self.grid.remove_paths(gone)
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.photos = [p for p in self.viewer.photos if str(p.path) not in set(gone)]
            if self.viewer.photo is None:
                self.viewer.navigate(0)
        self._update_status()

    # ------------------------------------------------------------- tagging
    def _tag_focus_in(self, _event=None):
        self._clear_placeholder(self.tag_entry, "add tag…")

    def _clear_placeholder(self, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, "end")
            entry.configure(foreground="#111")

    def _restore_placeholder(self, entry, placeholder):
        if not entry.get():
            entry.delete(0, "end")
            entry.insert(0, placeholder)
            entry.configure(foreground="#888")

    def _tag_entered(self, _event=None):
        text = self.tag_entry.get().strip()
        if text.startswith("-"):
            self._remove_tag(text.lstrip("-"))
        elif text:
            self._add_tag(text)
        self.tag_entry.delete(0, "end")

    def _add_tag_from_entry(self):
        self._add_tag(self.tag_entry.get().strip().lstrip("#"))

    def _remove_tag_from_entry(self):
        self._remove_tag(self.tag_entry.get().strip().lstrip("-#"))

    def _clean_tag(self, raw: str) -> list[str]:
        tags = {t.strip().lstrip("#") for t in raw.split(",")}
        return [t for t in tags if t]

    def _add_tag(self, raw: str):
        tags = self._clean_tag(raw)
        if not tags:
            return
        self._each_selected(lambda p: p.tags.update(tags))

    def _remove_tag(self, raw: str):
        tags = set(self._clean_tag(raw))
        if not tags:
            return
        self._each_selected(lambda p: p.tags.difference_update(tags))

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
        root = self.root_folder or photo.path.parent
        move_to_trash(root, photo)
        self._purge_thumb(photo)
        gone = str(photo.path)
        self.all_photos = [p for p in self.all_photos if str(p.path) != gone]
        self.grid.remove_paths([gone])
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.photos = [p for p in self.viewer.photos if str(p.path) != gone]
            if not self.viewer.photos:
                self.viewer.destroy()
            elif self.viewer.index >= len(self.viewer.photos):
                self.viewer.index = len(self.viewer.photos) - 1
            if self.viewer.winfo_exists():
                self.viewer.draft = None
                self.viewer._show()

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
        menu.add_command(label="Rotate left", command=lambda: self.rotate_selection(-90))
        menu.add_command(label="Rotate right", command=lambda: self.rotate_selection(90))
        menu.add_separator()
        if photo.tags:
            sub = tk.Menu(menu, tearoff=0)
            for tag in sorted(photo.tags):
                sub.add_command(label=f"Remove “{tag}”",
                                command=lambda t=tag: self._remove_tag(t))
            menu.add_cascade(label="Remove tags", menu=sub)
        menu.add_command(label="Delete…", command=self.delete_selection)
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
            if p.tags:
                info += "  " + " ".join("#" + t for t in sorted(p.tags))
        elif sel:
            common = set.intersection(*(p.tags for p in sel)) if sel else set()
            info = f"{len(sel)} selected · tags on all: " + (
                " ".join("#" + t for t in sorted(common)) if common else "(none)")
        else:
            info = "Click to select · Ctrl-click to add · Shift-click for ranges · double-click to view"
        self.status.configure(
            text=f"{visible} / {total} photos · {len(sel)} selected   |   {info}")


def main():
    app = App()
    app.mainloop()
