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
class TestFlagToggles:
    def test_toggle_pick_sets_then_clears(self, viewer, photo_dir):
        viewer.toggle_pick()
        assert viewer.photo.flag == "pick"
        assert load_photo(photo_dir / viewer.photo.name).flag == "pick"
        viewer.toggle_pick()
        assert viewer.photo.flag is None
        assert load_photo(photo_dir / viewer.photo.name).flag is None

    def test_pick_replaces_reject_and_vice_versa(self, viewer):
        viewer.set_flag("reject")
        viewer.toggle_pick()
        assert viewer.photo.flag == "pick"
        viewer.toggle_reject()
        assert viewer.photo.flag == "reject"

    def test_buttons_show_toggled_state(self, viewer):
        viewer.toggle_pick()
        viewer._show(keep_crop=True)
        assert viewer.toolbar.pick_btn.cget("style") == "Accent.TButton"
        assert viewer.toolbar.reject_btn.cget("style") == "TButton"
        viewer.toggle_pick()
        viewer._show(keep_crop=True)
        assert viewer.toolbar.pick_btn.cget("style") == "TButton"

    def test_info_label_shows_capital_flag(self, viewer):
        viewer.set_flag("reject")
        text = viewer.toolbar.info.cget("text")
        assert "REJECT" in text
        assert viewer.photo.name in text


@requires_display
class TestZoom:
    def test_zoom_in_out_clamped_to_fit(self, viewer):
        viewer._show()
        viewer.view.zoom_by(1.25)
        assert viewer.view.zoom == 1.25
        viewer.view.zoom_by(1 / 1.25)
        assert viewer.view.zoom == 1.0
        viewer.view.zoom_by(1 / 1.25)   # cannot go below fit
        assert viewer.view.zoom == 1.0

    def test_wheel_zooms(self, viewer):
        class Ev:
            delta = 120
            x = 10
            y = 10
        viewer._show()
        viewer._on_wheel(Ev())
        assert viewer.view.zoom == 1.25

    def test_wheel_zoom_out(self, viewer):
        class Ev:
            delta = -120
            x = 10
            y = 10
        viewer._show()
        viewer.view.zoom_by(1.25)
        viewer._on_wheel(Ev())
        assert viewer.view.zoom == 1.0

    def test_pan_moves_and_clamps(self, viewer):
        viewer._show()
        viewer.view.zoom_by(1.25)               # image now larger than the window
        viewer._show(keep_crop=True)
        old = viewer.view.img_box
        viewer.view.pan_by(-5, -5)
        assert viewer.view.img_box[0] == old[0] - 5      # within bounds: exact shift
        dw = old[2] - old[0]
        viewer.view.pan_by(-10 ** 6, -10 ** 6)          # way out: clamped
        assert viewer.view.img_box[0] == viewer.view.canvas.winfo_width() - dw

    def test_zoom_resets_on_navigate(self, viewer):
        viewer._show()
        viewer.view.zoom_by(1.25)
        viewer.navigate(1)
        assert viewer.view.zoom == 1.0
        assert (viewer.view.pan_x, viewer.view.pan_y) == (0, 0)


@requires_display
class TestShowOriginal:
    def test_original_shows_uncropped(self, viewer):
        photo = viewer.photos[0]
        viewer.toggle_crop()
        viewer.draft = [0.1, 0.1, 0.6, 0.7]
        viewer.apply_crop()
        assert photo.crop is not None

        viewer.toggle_original()
        assert viewer.show_original is True
        assert viewer.toolbar.original_btn.cget("style") == "Accent.TButton"
        viewer._show(keep_crop=True)
        bw, bh = viewer.view.base.size
        ox, oy, ox2, oy2 = viewer.view.img_box
        assert abs((ox2 - ox) / (oy2 - oy) - bw / bh) < 0.01

        viewer.toggle_original()
        assert viewer.show_original is False
        viewer._show(keep_crop=True)
        ox, oy, ox2, oy2 = viewer.view.img_box
        cw = photo.crop[2] - photo.crop[0]
        chh = photo.crop[3] - photo.crop[1]
        assert abs((ox2 - ox) / (oy2 - oy) - (bw * cw) / (bh * chh)) < 0.05


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
class TestCropToolbar:
    def _pixel_ratio(self, viewer):
        x0, y0, x1, y1 = viewer.draft
        bw, bh = viewer.view.base.size
        return (x1 - x0) * bw / ((y1 - y0) * bh)

    def test_bar_shown_only_in_crop_mode(self, viewer):
        viewer.update()
        assert not viewer.crop_toolbar.frame.winfo_ismapped()
        viewer.toggle_crop()
        viewer.update()
        assert viewer.crop_toolbar.frame.winfo_ismapped()
        viewer._exit_crop()
        viewer.update()
        assert not viewer.crop_toolbar.frame.winfo_ismapped()

    def test_bar_sits_above_main_toolbar(self, viewer):
        viewer.toggle_crop()
        viewer.update()
        assert viewer.crop_toolbar.frame.winfo_rooty() < viewer.toolbar.frame.winfo_rooty()

    def test_apply_and_clear_live_in_crop_bar(self, viewer):
        viewer.toggle_crop()
        labels = [str(w.cget("text")) for w in viewer.crop_toolbar.frame.winfo_children()
                  if w.winfo_class() == "TButton"]
        assert "Apply crop" in labels
        assert "Clear crop" in labels

    def test_ratio_selection_reshapes_draft(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("4:3")
        assert viewer.crop.ratio.label == "4:3"
        assert abs(self._pixel_ratio(viewer) - 4 / 3) < 0.01
        assert viewer.crop_toolbar.ratio_buttons["4:3"].cget("style") == "Accent.TButton"

    def test_ratio_toggle_returns_to_free_crop(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("16:9")
        viewer.set_ratio("16:9")
        assert viewer.crop.ratio.label is None
        assert viewer.crop_toolbar.ratio_buttons["16:9"].cget("style") == "TButton"

    def test_original_ratio_matches_image_aspect(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("original")
        bw, bh = viewer.view.base.size
        assert abs(self._pixel_ratio(viewer) - bw / bh) < 0.01

    def test_orientation_swap_flips_ratio(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("4:3")
        viewer.swap_orientation()
        assert viewer.crop.ratio.transposed is True
        assert abs(self._pixel_ratio(viewer) - 3 / 4) < 0.01
        assert viewer.crop_toolbar.orientation_btn.cget("style") == "Accent.TButton"
        assert "3:4" in viewer.toolbar.info.cget("text")

    def test_swap_without_ratio_adopts_original(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.swap_orientation()
        assert viewer.crop.ratio.label == "original"
        bw, bh = viewer.view.base.size
        assert abs(self._pixel_ratio(viewer) - bh / bw) < 0.01

    def test_edge_drag_keeps_ratio(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("1:1")
        ox, oy, ox2, oy2 = viewer.view.img_box
        dw, dh = ox2 - ox, oy2 - oy
        viewer.crop.start_drag("e", 0.5, 0.5)
        viewer.crop.motion(0.9, 0.6, viewer.view.size)      # rel coords
        x0, y0, x1, y1 = viewer.draft
        bw, bh = viewer.view.base.size
        assert abs((x1 - x0) * bw - (y1 - y0) * bh) < 2      # square in pixels

    def test_new_rect_keeps_ratio(self, viewer):
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("16:9")
        rect = viewer.crop.new_rect(0.2, 0.2, 0.8, 0.8, viewer.view.size)
        bw, bh = viewer.view.base.size
        w = (rect[2] - rect[0]) * bw
        h = (rect[3] - rect[1]) * bh
        assert abs(w / h - 16 / 9) < 0.01

    def test_ratio_crop_applies(self, viewer, photo_dir):
        photo = viewer.photos[0]
        viewer._show()
        viewer.toggle_crop()
        viewer.set_ratio("4:3")
        draft = tuple(viewer.draft)
        viewer.apply_crop()
        stored = load_photo(photo_dir / photo.name)
        assert stored.crop is not None
        assert all(abs(a - b) < 1e-9 for a, b in zip(stored.crop, draft))
        assert viewer.crop_mode is False


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
        viewer.delete_current()
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

    def test_launch_with_folder_saves_it(self, photo_dir):
        from photofx.lib import settings
        proc = subprocess.Popen(
            [sys.executable, "-m", "photofx.viewer", str(photo_dir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(3)
        finally:
            proc.terminate()
            proc.communicate(timeout=10)
        assert settings.saved_folder() == photo_dir

    def test_launch_without_args_uses_saved_folder(self, photo_dir):
        from photofx.lib import settings
        settings.save_folder(photo_dir)
        proc = subprocess.Popen(
            [sys.executable, "-m", "photofx.viewer"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(3)
            assert proc.poll() is None, "viewer exited instead of showing the saved folder"
        finally:
            proc.terminate()
            proc.communicate(timeout=10)
