"""Tests for the viewer application (photofx.viewer).

The viewer is tested as its own application: on its own Tk root, without
the grid app, plus the standalone entry point (python -m photofx.viewer).
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from tests.conftest import DISPLAY_OK

pytest.importorskip("PIL")

from photofx.lib.catalog import load_photo, save_photo, scan_folder  # noqa: E402

requires_display = pytest.mark.skipif(not DISPLAY_OK, reason="no X display available")


@pytest.fixture
def viewer(photo_dir):
    """A viewer window on its own withdrawn root, sidecars saved on change."""
    import tkinter as tk
    from photofx.viewer.viewer import Viewer

    root = tk.Tk()
    root.withdraw()
    photos = scan_folder(photo_dir)
    window = Viewer(root, photos, 0, on_change=save_photo)
    window.update_idletasks()
    yield window
    if window.winfo_exists():
        window.destroy()
    root.destroy()


@requires_display
class TestViewerCrop:
    def test_crop_apply_persists(self, viewer, photo_dir):
        photo = viewer.photos[0]
        viewer.toggle_crop()
        viewer.draft = [0.1, 0.1, 0.6, 0.7]
        viewer.apply_crop()
        stored = load_photo(photo_dir / photo.name)
        assert stored.crop == (0.1, 0.1, 0.6, 0.7)
        assert viewer.crop_mode is False

    def test_esc_exits_crop_without_applying(self, viewer, photo_dir):
        photo = viewer.photos[0]
        viewer.toggle_crop()
        viewer.draft = [0.1, 0.1, 0.5, 0.5]
        viewer._exit_crop()
        assert load_photo(photo_dir / photo.name).crop is None

    def test_tiny_crop_is_rejected(self, viewer, photo_dir):
        photo = viewer.photos[0]
        viewer.toggle_crop()
        viewer.draft = [0.4, 0.4, 0.41, 0.45]
        viewer.apply_crop()
        assert load_photo(photo_dir / photo.name).crop is None

    def test_clear_crop(self, viewer, photo_dir):
        photo = viewer.photos[0]
        viewer.toggle_crop()
        viewer.draft = [0.1, 0.1, 0.9, 0.9]
        viewer.apply_crop()
        viewer.clear_crop()
        assert load_photo(photo_dir / photo.name).crop is None

    def test_rotate_remaps_crop(self, viewer, photo_dir):
        photo = viewer.photos[0]
        viewer.toggle_crop()
        viewer.draft = [0.1, 0.2, 0.8, 0.9]
        viewer.apply_crop()
        viewer.rotate(90)
        stored = load_photo(photo_dir / photo.name)
        assert stored.rotation == 90
        assert all(abs(a - b) < 1e-9 for a, b in
                   zip(stored.crop, (1 - 0.9, 0.1, 1 - 0.2, 0.8)))


@requires_display
class TestViewerNavigation:
    def test_navigate_wraps(self, viewer):
        viewer.navigate(-1)  # wraps to last
        assert viewer.index == len(viewer.photos) - 1
        viewer.navigate(1)   # wraps to first
        assert viewer.index == 0

    def test_flags_persist(self, viewer, photo_dir):
        viewer.set_flag("reject")
        assert load_photo(photo_dir / viewer.photo.name).flag == "reject"
        viewer.set_flag(None)
        assert load_photo(photo_dir / viewer.photo.name).flag is None

    def test_rotate_persists(self, viewer, photo_dir):
        name = viewer.photo.name
        viewer.rotate(90)
        assert load_photo(photo_dir / name).rotation == 90


@requires_display
class TestViewerRemoveCurrent:
    def test_clamps_index_when_deleting_last(self, viewer):
        viewer.navigate(len(viewer.photos) - 1)
        victim = viewer.photo
        viewer.remove_current()
        assert victim not in viewer.photos
        assert viewer.index == len(viewer.photos) - 1

    def test_can_empty_the_whole_list(self, viewer):
        while viewer.photos:
            viewer.remove_current()
        assert viewer.photos == []
        assert viewer.index == 0

    def test_delete_flow_like_standalone_app(self, viewer, photo_dir, monkeypatch):
        import tkinter.messagebox as mb
        from photofx.lib.ops import delete_photo

        monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)

        def on_delete(photo):
            delete_photo(photo_dir, photo)
            viewer.remove_current()

        viewer.on_delete = on_delete  # same wiring photofx.viewer uses
        viewer.navigate(2)
        victim = viewer.photo
        viewer._delete_current()
        assert not victim.path.exists()
        assert (photo_dir / ".photofx_trash" / victim.name).exists()
        assert victim not in viewer.photos


@requires_display
class TestStandaloneEntry:
    """python -m photofx.viewer — argument validation and launch smoke."""

    def test_invalid_folder_shows_error(self, monkeypatch, tmp_path):
        import tkinter.messagebox as mb
        from photofx.viewer.__main__ import main
        calls = []
        monkeypatch.setattr(mb, "showerror", lambda *a, **k: calls.append("error"))
        monkeypatch.setattr(mb, "showinfo", lambda *a, **k: calls.append("info"))
        main([str(tmp_path / "does-not-exist")])
        assert calls == ["error"]

    def test_empty_folder_shows_info(self, monkeypatch, tmp_path):
        import tkinter.messagebox as mb
        from photofx.viewer.__main__ import main
        (tmp_path / "empty").mkdir()
        calls = []
        monkeypatch.setattr(mb, "showerror", lambda *a, **k: calls.append("error"))
        monkeypatch.setattr(mb, "showinfo", lambda *a, **k: calls.append("info"))
        main([str(tmp_path / "empty")])
        assert calls == ["info"]

    def test_cancelled_dialog_returns_quietly(self, monkeypatch):
        from tkinter import filedialog
        from photofx.viewer.__main__ import main
        monkeypatch.setattr(filedialog, "askdirectory", lambda **k: "")
        main([])  # must return without error

    def test_launch_smoke(self, photo_dir):
        proc = subprocess.Popen(
            [sys.executable, "-m", "photofx.viewer", str(photo_dir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(4)
            assert proc.poll() is None, "viewer exited unexpectedly"
        finally:
            proc.terminate()
            out, err = proc.communicate(timeout=10)
        assert b"Traceback" not in err, err.decode()
