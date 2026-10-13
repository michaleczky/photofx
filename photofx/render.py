"""Render: Pillow pipeline (EXIF -> rotation -> crop) and thumbnail caching.

Originals are never modified. Every pixel the user sees is produced here
from the original file plus the metadata in the sidecar.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
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
        return render(photo, size)
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


class DiskThumbCache:
    """Persistent thumbnails under <folder>/.photofx_cache/thumbs.

    File names encode the source path plus mtime/rotation/crop/size, so a
    cached thumb is reused only while the photo and its metadata are
    unchanged. JPEG keeps the files small and fast to reload.
    """

    def __init__(self, folder: Path):
        self.dir = Path(folder) / ".photofx_cache" / "thumbs"
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _path_key(path: Path) -> str:
        return hashlib.sha1(str(path).encode("utf-8")).hexdigest()

    def get(self, photo: Photo, size: int) -> Image.Image | None:
        f = self._cached_file(photo, size)
        if f is None or not f.exists():
            return None
        try:
            img = Image.open(f)
            img.load()
            return img
        except Exception:
            return None

    def put(self, photo: Photo, size: int, img: Image.Image) -> None:
        f = self._cached_file(photo, size)
        if f is None:
            return
        try:
            img.convert("RGB").save(f, "JPEG", quality=85)
        except Exception:
            pass

    def purge(self, path: Path) -> None:
        """Remove every cached variant of a photo (e.g. after delete)."""
        for f in self.dir.glob(self._path_key(path) + "_*.jpg"):
            try:
                f.unlink()
            except OSError:
                pass

    def _cached_file(self, photo: Photo, size: int) -> Path | None:
        try:
            mtime = photo.path.stat().st_mtime_ns
        except OSError:
            return None
        meta = f"{mtime}|{photo.rotation}|{photo.crop}|{size}"
        meta_key = hashlib.sha1(meta.encode("utf-8")).hexdigest()[:16]
        return self.dir / f"{self._path_key(photo.path)}_{meta_key}.jpg"


class ThumbWorker:
    """Renders thumbnails in background threads.

    Pillow releases the GIL while decoding and resizing, so a pool of
    workers parallelises thumbnail generation across CPU cores. Results
    are pushed onto a deque that the UI thread drains via collect().
    """

    def __init__(self, cache_dir: Path, memory: ThumbCache, workers: int | None = None):
        self.memory = memory
        self.disk = DiskThumbCache(cache_dir)
        n = workers or max(2, (os.cpu_count() or 4) - 1)
        self.pool = ThreadPoolExecutor(max_workers=n)
        self.results: deque[tuple[str, int, Image.Image]] = deque()

    def submit(self, photo: Photo, size: int) -> None:
        self.pool.submit(self._render, photo, size)

    def _render(self, photo: Photo, size: int) -> None:
        img = self.memory.get(photo, size)
        if img is None:
            img = self.disk.get(photo, size)
        if img is None:
            img = load_thumb(photo, size)
            if img is not None:
                self.disk.put(photo, size, img)
        if img is not None:
            self.memory.put(photo, size, img)
            self.results.append((str(photo.path), size, img))

    def collect(self, limit: int = 24) -> list[tuple[str, int, Image.Image]]:
        out = []
        while len(out) < limit and self.results:
            out.append(self.results.popleft())
        return out

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
