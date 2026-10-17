# photofx

A lightweight photo catalog and editor built with Python, tkinter and
Pillow. Only the features you actually use for cataloging and culling
photos — nothing else. Two small applications share one non-destructive
library:

- **photofx** — the thumbnail grid app for browsing and culling
  (`python -m photofx`)
- **photofx.viewer** — the single-photo viewer with crop, rotate, flag and
  delete, usable standalone (`python -m photofx.viewer [folder]`)

```
photofx/
├── lib/        # shared code used by both applications
│   ├── catalog.py   # sidecar JSON metadata, folder scan, trash
│   ├── render.py    # EXIF/rotate/crop/edit pipeline, thumbnail caches, worker
│   ├── edits.py     # edit sliders: exposure, contrast, WB, saturation, Auto
│   ├── exif.py      # file and EXIF metadata for the info pane
│   ├── icons.py     # toolbar icons
│   └── ops.py       # shared operations (rotation + crop remap, delete)
├── app/        # the grid application
│   ├── main.py      # the window: folder, filters, selection operations
│   ├── grid.py      # thumbnail grid: layout, events, cell patching
│   ├── selection.py # selection state: click/ctrl/shift/drag semantics
│   ├── thumbs.py    # thumbnail sourcing: cache, background worker, pump
│   ├── cells.py     # painting of one grid cell (badges, captions)
│   ├── filters.py   # named photo filters
│   └── bars.py      # toolbar and status bar
└── viewer/     # the viewer application
    ├── viewer.py    # the window: photo list, actions, event wiring
    ├── view.py      # image canvas: fit/zoom/pan rendering
    ├── crop.py      # crop state: ratios, draft rect, drag geometry
    ├── enhance.py   # the enhance pane: sectioned sliders, Auto, Reset
    ├── info.py      # the info pane: file and EXIF metadata rows
    └── bars.py      # the bottom toolbar and the crop toolbar
```

## Features

- **Browse**: scrollable thumbnail grid for a folder (scanned recursively).
- **Multi-select**: click, Ctrl-click to add/remove, Shift-click for ranges,
  Ctrl+A for all. Every operation applies to the whole selection.
- **Rotate**: 90° right per click, stored as metadata, never touching the file.
- **Crop**: interactive crop in the viewer — drag to draw a rect, drag inside
  to move it, drag edges/corners to resize. Rule-of-thirds guides included.
  In crop mode a second toolbar appears above the main one with crop ratios
  (original, 4:3, 16:9, 1:1), an orientation swap, and apply/clear.
- **Enhance** (viewer, `e`): a pane on the right edge with exposure,
  contrast, white balance (temp/tint) and saturation sliders with live
  preview, grouped into Light and Color sections, plus Auto (white
  balance, exposure and contrast suggested from the image itself) and a
  Reset button that clears all enhancements. The pane's visibility is
  remembered between sessions. Edits apply to thumbnails too.
- **Info** (viewer, `i`): a pane in the same right-hand column as
  Enhance, shown below it when both are open, with the important facts
  about the current photo: file name, format, dimensions, size,
  modified date, and the camera data from EXIF (camera model, date
  taken, exposure, aperture, ISO, focal length, lens) when present.
  The pane's visibility is remembered between sessions.
- **Flag**: pick (★) / reject (✕) / clear.
- **Filter**: picks / rejected / without rejects / unflagged.
- **Delete**: moves photos (and their sidecars) into a `.photofx_trash` folder
  inside the scanned folder. Nothing is destroyed; restore by moving files back.
- **Non-destructive**: originals are *never* modified. Rotation, crop, edits
  and flags live in a JSON sidecar next to each image (`IMG_0001.jpg.json`).
- **Hidden & excluded files**: files whose name starts with `.` are never
  shown. Add your own exclusion regexes to the `exclude` list in the settings
  file (`~/.config/photofx/settings.json`) and photos matching them are hidden
  from the grid, e.g. `{"folder": "...", "exclude": ["^screenshot", "_thumb$"]}`.
- **Fast thumbnails**: rendered in parallel on background threads and cached
  on disk in `.photofx_cache/thumbs` inside the photo folder. Folders you
  have opened once display their thumbnails almost instantly at startup;
  cache entries are keyed by mtime/rotation/crop/edits, so edits always
  re-render.

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

1. The app opens your **Pictures** folder by default (the folder picker
   only appears when it doesn't exist). The last folder you open is
   remembered and restored on the next launch; **Open folder...** starts
   the dialog at the current folder.
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

Run it standalone with `python -m photofx.viewer [folder]` — without an
argument it opens the last used folder, or your Pictures directory on
first launch (a folder picker only appears when neither exists). The
folder shown is remembered for the next launch. Or open it from the grid
app by double-clicking a photo.

`←`/`→` navigate, `P`/`X`/`U` flag, `[`/`]` rotate, `Delete` delete.
`+`/`-` zoom in/out (also the mouse wheel), `0` fit to window; drag the
image to pan while zoomed in. The **Pick**/**Reject** buttons are
toggles: clicking one sets it and clears the other, clicking it again
clears the flag. **Original** shows the uncropped photo.
**Crop** toggles the crop overlay; drag to draw, then **Apply crop**
(or `Enter`). `Esc` leaves crop mode without applying. While cropping, a
toolbar above the main one holds the crop tools: ratio buttons (original,
4:3, 16:9, 1:1 — click the active one again for a free crop),
**Orientation** to flip the ratio between landscape and portrait, and
apply/clear. The chosen ratio constrains the overlay while you drag.

## Sidecar format

```json
{
  "flag": "pick",
  "rotation": 90,
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

- `tests/test_catalog.py`, `tests/test_render.py`, `tests/test_ops.py`,
  `tests/test_exif.py` — headless unit tests for the shared library
  (scanning, sidecar JSON, EXIF/rotation/crop pipeline, thumbnail caches,
  shared operations, file/EXIF metadata).
- `tests/test_app.py` — drives the real grid app (selection, filters,
  thumbnails, keyboard guard, embedded viewer).
- `tests/test_viewer.py` — drives the viewer as its own application
  (crop/rotate/flags, remove-current, standalone entry point).
- GUI tests need an X display and are skipped automatically when none is
  available.

## Icon credits

Toolbar icons in `photofx/icons/` come from IconArchive:

- **wefunction woofunction** set (folder, star, close) — GPL,
  https://www.iconarchive.com/show/woofunction-icons-by-wefunction.html
- **Koloria** set by GraphicRating (prev, next, zoom in, zoom out, trash) —
  free for commercial use,
  https://www.iconarchive.com/show/koloria-icons-by-graphicrating.2.html
- **Farm-Fresh** web icons by FatCow (crop) — free for commercial use,
  https://www.iconarchive.com/show/farm-fresh-icons-by-fatcow.html
- **Oxygen** set by oxygen-icons.org (rotate) — LGPL,
  https://www.iconarchive.com/show/oxygen-icons-by-oxygen-icons.org.html
