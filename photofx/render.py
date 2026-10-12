"""Render: Pillow pipeline (EXIF -> rotation -> crop) and thumbnail caching.

Originals are never modified. Every pixel the user sees is produced here
from the original file plus the metadata in the sidecar.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageOps

from .catalog import Photo

Image.MAX_IMAGE_PIXELS = None  # trust local files


def open_rotated(photo: Photo) -> Image.Image:
    """Original with EXIF orientation and sidecar rotation applied (no crop)."""
    img = Image.open(photo.path)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if not isinstance(img, Image.Image):  # exif_transpose may return None on odd files
        img = Image.open(photo.path)
    if photo.rotation:
        img = img.rotate(-photo.rotation, expand=True)
    return img


def render(photo: Photo, max_size: int | None = None) -> Image.Image:
    """Full pipeline: EXIF -> rotation -> crop, optionally downscaled to fit."""
    img = open_rotated(photo)
    if photo.crop is not None:
        x0, y0, x1, y1 = photo.crop
        w, h = img.size
        img = img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    if max_size and max(img.size) > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img


def load_thumb(photo: Photo, size: int) -> Image.Image | None:
    """Fast path for thumbnails: JPEG draft mode, then the full pipeline."""
    try:
        img = Image.open(photo.path)
        if img.format == "JPEG":
            img.draft("RGB", (size * 2, size * 2))
        return render(photo, size * 2)
    except Exception:
        return None


class ThumbCache:
    """Thread-safe LRU cache of rendered thumbnails keyed by (path, mtime, size)."""

    def __init__(self, max_items: int = 600):
        self._items: OrderedDict[tuple, Image.Image] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_items

    def key(self, photo: Photo, size: int):
        try:
            mtime = photo.path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        return (str(photo.path), mtime, photo.rotation, photo.crop, tuple(sorted(photo.tags)), size)

    def get(self, photo: Photo, size: int) -> Image.Image | None:
        with self._lock:
            img = self._items.get(self.key(photo, size))
            if img is not None:
                self._items.move_to_end(self.key(photo, size))
            return img

    def put(self, photo: Photo, size: int, img: Image.Image) -> None:
        with self._lock:
            self._items[self.key(photo, size)] = img
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def drop(self, path: Path) -> None:
        s = str(path)
        with self._lock:
            for k in [k for k in self._items if k[0] == s]:
                del self._items[k]
