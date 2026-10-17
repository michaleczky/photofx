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
class TestEnhancePane:
    def test_toggle_shows_and_hides_pane(self, viewer):
        viewer.toggle_enhance()
        assert viewer.enhance_visible
        assert viewer.enhance_pane.frame.winfo_manager() == "pack"
        viewer.toggle_enhance()
        assert not viewer.enhance_visible
        assert viewer.enhance_pane.frame.winfo_manager() == ""

    def test_all_sliders_are_in_the_pane(self, viewer):
        from photofx.lib.catalog import EDIT_KEYS
        assert set(viewer.enhance_pane.scales) == set(EDIT_KEYS)

    def test_pane_sliders_start_at_zero(self, viewer):
        viewer.toggle_enhance()
        for scale in viewer.enhance_pane.scales.values():
            assert float(scale.get()) == 0.0

    def test_slider_drag_previews_and_release_persists(self, viewer, photo_dir):
        viewer.toggle_enhance()
        name = viewer.photo.name
        viewer.enhance_pane.scales["exposure"].set(0.5)   # fires live_enhance
        assert viewer._live_edits is not None
        viewer._show(keep_crop=True)                      # what the debounce runs
        assert abs(viewer.view.edits["exposure"] - 0.5) < 1e-9
        assert viewer.photo.edits == {}                   # not stored while dragging
        viewer.commit_enhance()                           # what release runs
        assert abs(viewer.photo.edits["exposure"] - 0.5) < 1e-9
        assert load_photo(photo_dir / name).edits["exposure"] == 0.5

    def test_zero_slider_position_is_not_stored(self, viewer):
        viewer.toggle_enhance()
        viewer.enhance_pane.scales["contrast"].set(25)
        viewer.commit_enhance()
        assert viewer.photo.edits == {"contrast": 25.0}
        viewer.enhance_pane.scales["contrast"].set(0)
        viewer.commit_enhance()
        assert viewer.photo.edits == {}

    def test_auto_sets_edits_from_the_image(self, viewer, photo_dir):
        name = viewer.photo.name
        viewer.toggle_enhance()
        viewer.auto_enhance()
        assert viewer.photo.edits            # something was suggested
        assert viewer._live_edits is None    # no dangling drag state
        stored = load_photo(photo_dir / name).edits
        assert stored == viewer.photo.edits
        # the pane sliders follow the suggestion
        for key, scale in viewer.enhance_pane.scales.items():
            assert abs(float(scale.get()) - stored.get(key, 0.0)) < 1e-9

    def test_reset_clears_edits(self, viewer, photo_dir):
        name = viewer.photo.name
        viewer.toggle_enhance()
        viewer.enhance_pane.scales["saturation"].set(40)
        viewer.commit_enhance()
        assert viewer.photo.edits
        viewer.reset_enhance()
        assert viewer.photo.edits == {}
        assert load_photo(photo_dir / name).edits == {}

    def test_show_original_ignores_edits(self, viewer):
        viewer.toggle_enhance()
        viewer.enhance_pane.scales["temp"].set(30)
        viewer.commit_enhance()
        viewer.toggle_original()
        viewer._show(keep_crop=True)
        assert viewer.view.edits == {}
        viewer.toggle_original()
        viewer._show(keep_crop=True)
        assert viewer.view.edits == {"temp": 30.0}

    def test_info_line_marks_edited_photos(self, viewer):
        viewer.toggle_enhance()
        viewer.enhance_pane.scales["contrast"].set(10)
        viewer.commit_enhance()
        assert "[edited]" in viewer.toolbar.info.cget("text")

    def test_navigating_resyncs_sliders(self, viewer):
        viewer.toggle_enhance()
        viewer.enhance_pane.scales["tint"].set(-15)
        viewer.commit_enhance()
        viewer.navigate(1)                     # photo without edits
        assert viewer.photo.edits == {}
        for scale in viewer.enhance_pane.scales.values():
            assert float(scale.get()) == 0.0
        viewer.navigate(-1)                    # back to the edited one
        assert abs(float(viewer.enhance_pane.scales["tint"].get()) + 15) < 1e-9

    def test_pane_does_not_commit_while_closed(self, viewer):
        viewer.toggle_enhance()
        viewer.enhance_pane.scales["exposure"].set(1.0)
        viewer.commit_enhance()
        viewer.toggle_enhance()                 # close
        assert viewer.photo.edits              # the earlier edit persists
        assert viewer._live_edits is None

    def test_pane_visibility_is_remembered(self, photo_dir):
        import tkinter as tk
        from photofx.lib import settings
        from photofx.viewer.viewer import Viewer

        root = tk.Tk()
        root.withdraw()
        photos = scan_folder(photo_dir)
        assert settings.get_value("enhance_pane", False) is False
        first = Viewer(root, list(photos), 0)
        assert not first.enhance_visible        # hidden on first launch
        first.toggle_enhance()                  # leave it open
        first.destroy()

        second = Viewer(root, list(photos), 0)  # a fresh viewer remembers
        assert second.enhance_visible
        assert second.enhance_pane.frame.winfo_manager() == "pack"
        second.toggle_enhance()                 # leave it closed
        second.destroy()

        third = Viewer(root, list(photos), 0)
        assert not third.enhance_visible
        third.destroy()
        root.destroy()


@requires_display
class TestFiltersPane:
    def _captions(self, viewer):
        """The caption of every tile in the pane."""
        texts = []
        for row in viewer.filters_pane.body.winfo_children():
            for tile in row.winfo_children():
                for widget in tile.winfo_children():
                    if widget.winfo_class() == "TLabel":
                        texts.append(str(widget.cget("text")))
        return texts

    def test_toggle_shows_and_hides_pane(self, viewer):
        viewer.toggle_filters()
        assert viewer.filter_visible
        assert viewer.filters_pane.frame.winfo_manager() == "pack"
        viewer.toggle_filters()
        assert not viewer.filter_visible
        assert viewer.filters_pane.frame.winfo_manager() == ""

    def test_filters_button_shows_toggled_state(self, viewer):
        viewer.toggle_filters()
        viewer._show(keep_crop=True)
        assert viewer.toolbar.filters_btn.cget("style") == "Accent.TButton"
        viewer.toggle_filters()
        viewer._show(keep_crop=True)
        assert viewer.toolbar.filters_btn.cget("style") == "TButton"

    def test_pane_has_original_plus_every_look(self, viewer):
        from photofx.lib.looks import LOOKS
        viewer.toggle_filters()
        captions = self._captions(viewer)
        assert captions[0] == "Original"
        assert captions[1:] == list(LOOKS.values())

    def test_click_stores_the_look(self, viewer, photo_dir):
        name = viewer.photo.name
        viewer.toggle_filters()
        viewer.commit_filter("sepia")
        assert viewer.photo.filter == "sepia"
        assert viewer.view.look == "sepia"          # rendered right away
        assert load_photo(photo_dir / name).filter == "sepia"

    def test_original_tile_clears_the_look(self, viewer, photo_dir):
        name = viewer.photo.name
        viewer.commit_filter("mono")
        assert viewer.photo.filter == "mono"
        viewer.commit_filter("")
        assert viewer.photo.filter is None
        assert load_photo(photo_dir / name).filter is None

    def test_hover_previews_without_storing(self, viewer, photo_dir):
        viewer.toggle_filters()
        viewer.live_filter("noir")
        viewer._show(keep_crop=True)
        assert viewer.view.look == "noir"
        assert viewer.photo.filter is None          # preview only
        assert load_photo(photo_dir / viewer.photo.name).filter is None
        viewer.cancel_filter()
        viewer._show(keep_crop=True)
        assert viewer.view.look is None             # back to the stored look

    def test_hover_original_previews_no_look(self, viewer):
        viewer.commit_filter("mono")
        viewer.live_filter("")                      # the Original tile
        viewer._show(keep_crop=True)
        assert viewer.view.look is None
        assert viewer.photo.filter == "mono"        # not cleared by the hover

    def test_show_original_ignores_the_look(self, viewer):
        viewer.commit_filter("mono")
        viewer.toggle_original()
        viewer._show(keep_crop=True)
        assert viewer.view.look is None
        assert viewer.view.edits == {}

    def test_info_line_marks_filtered_photos(self, viewer):
        viewer.commit_filter("fade")
        assert "[edited]" in viewer.toolbar.info.cget("text")

    def test_pane_follows_navigation(self, viewer):
        from photofx.lib.looks import LOOKS
        viewer.toggle_filters()
        assert len(self._captions(viewer)) == len(LOOKS) + 1
        viewer.navigate(1)
        assert len(self._captions(viewer)) == len(LOOKS) + 1
        assert viewer.view.look is None             # the new photo is unfiltered

    def test_pane_empty_when_no_photo_left(self, viewer):
        viewer.toggle_filters()
        while viewer.photos:
            viewer.remove_current()
        viewer._photo_changed()
        assert self._captions(viewer) == []

    def test_pane_visibility_is_remembered(self, photo_dir):
        import tkinter as tk
        from photofx.lib import settings
        from photofx.viewer.viewer import Viewer

        root = tk.Tk()
        root.withdraw()
        photos = scan_folder(photo_dir)
        assert settings.get_value("filters_pane", False) is False
        first = Viewer(root, list(photos), 0)
        assert not first.filter_visible        # hidden on first launch
        first.toggle_filters()                 # leave it open
        first.destroy()

        second = Viewer(root, list(photos), 0)  # a fresh viewer remembers
        assert second.filter_visible
        assert second.filters_pane.frame.winfo_manager() == "pack"
        second.toggle_filters()                 # leave it closed
        second.destroy()

        third = Viewer(root, list(photos), 0)
        assert not third.filter_visible
        third.destroy()
        root.destroy()


@requires_display
class TestInfoPane:
    def _texts(self, viewer):
        """Every label text in the pane, headers and row values alike."""
        texts = []
        for child in viewer.info_pane.body.winfo_children():
            if child.winfo_class() == "TFrame":
                for widget in child.winfo_children():
                    texts.append(str(widget.cget("text")))
            elif child.winfo_class() == "TLabel":
                texts.append(str(child.cget("text")))
        return texts

    def test_toggle_shows_and_hides_pane(self, viewer):
        viewer.toggle_info()
        assert viewer.info_visible
        assert viewer.info_pane.frame.winfo_manager() == "pack"
        viewer.toggle_info()
        assert not viewer.info_visible
        assert viewer.info_pane.frame.winfo_manager() == ""

    def test_info_button_shows_toggled_state(self, viewer):
        viewer.toggle_info()
        viewer._show(keep_crop=True)
        assert viewer.toolbar.info_btn.cget("style") == "Accent.TButton"
        viewer.toggle_info()
        viewer._show(keep_crop=True)
        assert viewer.toolbar.info_btn.cget("style") == "TButton"

    def test_pane_shows_file_and_camera_info(self, tmp_path):
        import tkinter as tk
        from tests.conftest import make_exif_image
        from photofx.viewer.viewer import Viewer

        folder = tmp_path / "cam"
        folder.mkdir()
        make_exif_image(folder / "cam.jpg", make="TestCam", model="Model X100",
                        exposure=(1, 125), aperture=(28, 10), iso=200)
        root = tk.Tk()
        root.withdraw()
        window = Viewer(root, scan_folder(folder), 0)
        try:
            window.toggle_info()
            texts = self._texts(window)
            assert "FILE" in texts and "CAMERA" in texts
            for expected in ("cam.jpg", "JPEG", "800 x 600 px",
                             "TestCam Model X100", "1/125 s", "f/2.8",
                             "ISO 200"):
                assert expected in texts
        finally:
            window.destroy()
            root.destroy()

    def test_pane_follows_navigation(self, viewer):
        viewer.toggle_info()
        assert viewer.photos[0].name in self._texts(viewer)
        viewer.navigate(1)
        assert viewer.photos[1].name in self._texts(viewer)

    def test_pane_empty_when_no_photo_left(self, viewer):
        viewer.toggle_info()
        while viewer.photos:
            viewer.remove_current()
        viewer._photo_changed()
        assert self._texts(viewer) == []

    def test_pane_visibility_is_remembered(self, photo_dir):
        import tkinter as tk
        from photofx.lib import settings
        from photofx.viewer.viewer import Viewer

        root = tk.Tk()
        root.withdraw()
        photos = scan_folder(photo_dir)
        assert settings.get_value("info_pane", False) is False
        first = Viewer(root, list(photos), 0)
        assert not first.info_visible          # hidden on first launch
        first.toggle_info()                    # leave it open
        first.destroy()

        second = Viewer(root, list(photos), 0)
        assert second.info_visible
        assert second.info_pane.frame.winfo_manager() == "pack"
        second.toggle_info()                   # leave it closed
        second.destroy()

        third = Viewer(root, list(photos), 0)
        assert not third.info_visible
        third.destroy()
        root.destroy()


@requires_display
class TestSidePane:
    """Enhance and info share one right-hand column: enhance above info."""

    def test_both_panes_stack_in_one_column(self, viewer):
        viewer.toggle_enhance()
        viewer.toggle_info()
        viewer.update()
        assert viewer.side_pane.winfo_manager() == "pack"
        enhance = viewer.enhance_pane.frame
        info = viewer.info_pane.frame
        assert enhance.winfo_rootx() == info.winfo_rootx()   # same column
        assert enhance.winfo_rooty() < info.winfo_rooty()    # enhance on top

    def test_enhance_stays_on_top_when_info_opened_first(self, viewer):
        viewer.toggle_info()
        viewer.toggle_enhance()
        viewer.update()
        assert (viewer.enhance_pane.frame.winfo_rooty()
                < viewer.info_pane.frame.winfo_rooty())

    def test_column_stays_while_one_pane_is_open(self, viewer):
        viewer.toggle_enhance()
        viewer.toggle_info()
        viewer.toggle_enhance()
        assert viewer.side_pane.winfo_manager() == "pack"   # info still on
        viewer.toggle_info()
        assert viewer.side_pane.winfo_manager() == ""

    def test_single_pane_uses_the_column_too(self, viewer):
        viewer.toggle_info()
        viewer.update()
        assert viewer.side_pane.winfo_manager() == "pack"
        assert viewer.info_pane.frame.winfo_manager() == "pack"
        assert not viewer.enhance_pane.frame.winfo_ismapped()


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
