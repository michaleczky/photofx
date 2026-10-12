# photofx

A lightweight photo catalog and editor built with Python, tkinter and 
Pillow. Only the features you actually use for cataloging and culling 
photos — nothing else.

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

## Install / run

```bash
cd photofx
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m photofx
```

(Or run with any Python ≥ 3.10 that has `tkinter` and Pillow installed:
`python3 -m photofx`.)

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
