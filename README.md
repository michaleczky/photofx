# photofx

A lightweight photo catalog and editor built with Python, tkinter and
Pillow. Only the features you actually use for cataloging and culling
photos — nothing else. Two small applications share one non-destructive
library:

- **photofx** — the thumbnail grid app for browsing, culling and tagging
  (`python -m photofx`)
- **photofx.viewer** — the single-photo viewer with crop, rotate, flag and
  delete, usable standalone (`python -m photofx.viewer [folder]`)

```
photofx/
├── lib/        # shared code used by both applications
│   ├── catalog.py   # sidecar JSON metadata, folder scan, trash
│   ├── render.py    # EXIF/rotate/crop pipeline, thumbnail caches, worker
│   ├── icons.py     # toolbar icons
│   └── ops.py       # shared operations (rotation + crop remap, delete)
├── app/        # the grid application
└── viewer/     # the viewer application
```

## Features

- **Browse**: scrollable thumbnail grid for a folder (scanned recursively).
- **Multi-select**: click, Ctrl-click to add/remove, Shift-click for ranges,
  Ctrl+A for all. Every operation applies to the whole selection.
- **Rotate**: 90° left/right, stored as metadata, never touching the file.
- **Crop**: interactive crop in the viewer — drag to draw a rect, drag inside
  to move it, drag edges/corners to resize. Rule-of-thirds guides included.
- **Flag**: pick (★) / reject (✕) / clear.
- **Tags**: free-text tags, comma-separated; add to or remove from the selection.
- **Filter**: picks / rejected / without rejects / unflagged / untagged, plus a
  tag text filter.
- **Delete**: moves photos (and their sidecars) into a `.photofx_trash` folder
  inside the scanned folder. Nothing is destroyed; restore by moving files back.
- **Non-destructive**: originals are *never* modified. Rotation, crop, flags and
  tags live in a JSON sidecar next to each image (`IMG_0001.jpg.json`).
- **Fast thumbnails**: rendered in parallel on background threads and cached
  on disk in `.photofx_cache/thumbs` inside the photo folder. Folders you
  have opened once display their thumbnails almost instantly at startup;
  cache entries are keyed by mtime/rotation/crop, so edits always re-render.

## Install / run

```bash
cd photofx
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m photofx
```

(Or run with any Python ≥ 3.10 that has `tkinter` and Pillow installed:
`python3 -m photofx`.)

### Windowed launchers (.pyw)

- `photofx.pyw` — grid application
- `viewer.pyw [folder]` — viewer application

On Windows these run under pythonw with no console window; on Linux they
are plain executable scripts (double-clickable if you associate `.pyw`
with your Python). If the interpreter that starts them lacks Pillow, they
re-exec themselves with `.venv`'s Python, so desktop launchers work
without any shell setup.

## Usage

1. **Open folder…** and pick your photo folder.
2. Select photos (click / Ctrl / Shift / Ctrl+A).
3. Use the toolbar, the right-click context menu, or keyboard shortcuts.

### Keyboard shortcuts (main window)

| Key | Action |
| --- | --- |
| `P` / `X` / `U` | pick / reject / clear flag |
| `[` / `]` | rotate left / right |
| `Delete` | move selection to `.photofx_trash` |
| arrows | move selection |
| `Ctrl+A` / `Esc` | select all / clear selection |
| double-click | open in viewer |

### Viewer

Run it standalone with `python -m photofx.viewer [folder]` (a folder picker
appears if you omit the argument), or open it from the grid app by
double-clicking a photo.

`←`/`→` navigate, `P`/`X`/`U` flag, `[`/`]` rotate, `Delete` delete.
**Crop** toggles the crop overlay; drag to draw, then **Apply crop**
(or `Enter`). `Esc` leaves crop mode without applying.

### Tags

Type tags (comma-separated) in the toolbar entry and press **Add tag** (or
Enter). Prefix with `-` (e.g. `-alps`) to remove instead. The status bar
shows the tags shared by all selected photos.

## Sidecar format

```json
{
  "flag": "pick",
  "rotation": 90,
  "tags": ["alps", "trip"],
  "crop": [0.1, 0.2, 0.8, 0.9]
}
```

- `flag`: `"pick"`, `"reject"` or `null`
- `rotation`: degrees clockwise (0/90/180/270), applied after the EXIF
  orientation
- `crop`: `[x0, y0, x1, y1]` in fractions of the *rotated* image

Deleting the sidecar file resets the photo to its original state.

## Running the tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

- `tests/test_catalog.py`, `tests/test_render.py`, `tests/test_ops.py` —
  headless unit tests for the shared library (scanning, sidecar JSON,
  EXIF/rotation/crop pipeline, thumbnail caches, shared operations).
- `tests/test_app.py` — drives the real grid app (selection, filters,
  tagging, thumbnails, keyboard guard, embedded viewer).
- `tests/test_viewer.py` — drives the viewer as its own application
  (crop/rotate/flags, remove-current, standalone entry point).
- GUI tests need an X display and are skipped automatically when none is
  available.

## Icon credits

Toolbar icons in `photofx/icons/` come from IconArchive:

- **wefunction woofunction** set (folder, arrows, star, star-off, close,
  pencil) — GPL, https://www.iconarchive.com/show/woofunction-icons-by-wefunction.html
- **Koloria** set by GraphicRating (trash) — free for commercial use,
  https://www.iconarchive.com/show/koloria-icons-by-graphicrating.2.html
