"""Thumbnail sourcing for the grid: memory/disk cache plus a worker pool.

:class:`ThumbnailStore` produces PIL thumbnails — from the background
:class:`~photofx.lib.render.ThumbWorker` when one is installed, or from an
idle-time pump when not — and hands them to its ``on_ready`` callback. It
never touches the canvas; the grid decides what to show.
"""

from __future__ import annotations

import tkinter as tk

from photofx.lib.catalog import Photo
from photofx.lib.render import ThumbCache, ThumbWorker, load_thumb

POLL_MS = 50          # worker result poll interval
PUMP_BATCH = 8        # thumbnails rendered per idle pass without a worker


class ThumbnailStore:
    """Fills in thumbnails for the visible photos, off the UI thread when possible."""

    def __init__(self, master: tk.Misc, cache: ThumbCache, size: int, on_ready):
        self.master = master
        self.cache = cache
        self.size = size
        self.on_ready = on_ready          # called with (path, PIL image)
        self.worker: ThumbWorker | None = None
        self.pending: list[str] = []      # paths awaiting the idle pump
        self.visible: dict[str, Photo] = {}   # paths currently shown
        self._pumping = False
        self._poll_job = None

    # ---------------------------------------------------------------- worker
    def set_worker(self, worker: ThumbWorker | None):
        """Install a background worker and start polling for its results."""
        self.worker = worker
        if worker is not None:
            self.pending.clear()
            self.cancel_poll()
            self._poll_job = self.master.after(POLL_MS, self._poll)

    def shutdown(self):
        if self.worker is not None:
            self.worker.shutdown()

    def purge(self, photo: Photo):
        """Drop a photo's thumbnails from the worker's disk cache."""
        if self.worker is not None:
            self.worker.disk.purge(photo.path)

    def cancel_poll(self):
        if self._poll_job is not None:
            try:
                self.master.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None

    # -------------------------------------------------------------- requests
    def set_photos(self, photos: list[Photo]):
        """The photos currently visible (for the pump's path lookups)."""
        self.visible = {str(p.path): p for p in photos}

    def request(self, photo: Photo):
        """Queue a thumbnail: to the worker, or to the idle pump.

        Without a worker the path is only appended; the caller is
        responsible for scheduling :meth:`pump_idle` afterwards.
        """
        if self.worker is not None:
            self.worker.submit(photo, self.size)
        else:
            s = str(photo.path)
            if s not in self.pending:
                self.pending.append(s)

    def refresh(self, photo: Photo):
        """Metadata changed: drop cached renders and queue a new one."""
        self.cache.drop(photo.path)
        if self.worker is not None:
            self.worker.submit(photo, self.size)
        else:
            self._enqueue(photo)

    def _enqueue(self, photo: Photo):
        s = str(photo.path)
        if s not in self.pending:
            self.pending.append(s)
            self.master.after_idle(self.pump_idle)

    # ------------------------------------------------------------------ pump
    def _poll(self):
        """UI thread: drain finished worker thumbnails and hand them over."""
        if self.worker is None or not self.master.winfo_exists():
            return
        for path, _size, img in self.worker.collect(24):
            self.on_ready(path, img)
        self._poll_job = self.master.after(POLL_MS, self._poll)

    def pump_idle(self):
        """Fallback thumbnail generation without a worker (idle-time)."""
        if self._pumping:
            return
        self._pumping = True
        try:
            for _ in range(PUMP_BATCH):
                if not self.pending:
                    break
                path = self.pending.pop(0)
                photo = self.visible.get(path)
                if photo is None:
                    continue
                img = self.cache.get(photo, self.size)
                if img is None:
                    img = load_thumb(photo, self.size)
                    if img is not None:
                        self.cache.put(photo, self.size, img)
                if img is not None:
                    self.on_ready(path, img)
            if self.pending:
                self.master.after_idle(self.pump_idle)
        finally:
            self._pumping = False
