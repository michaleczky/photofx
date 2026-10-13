"""GUI tests for the grid application (photofx.app).

These run against the real tkinter UI and are skipped automatically when
no X display is available.
"""

from __future__ import annotations

import pytest

from tests.conftest import DISPLAY_OK

pytest.importorskip("PIL")

from photofx.lib import icons  # noqa: E402
from photofx.lib.catalog import load_photo  # noqa: E402

requires_display = pytest.mark.skipif(not DISPLAY_OK, reason="no X display available")


class FakeEvent:
    """Just enough of a tkinter event for grid click handling."""

    def __init__(self, x, y, state=0):
        self.x = x
        self.y = y
        self.state = state


@pytest.fixture
def app(photo_dir):
    from photofx.app.main import App
    application = App()
    application.open_folder(str(photo_dir))
    application.update()
    yield application
    application.grid.pending.clear()  # no thumbnail pump after destroy
    try:
        application.destroy()
    except Exception:
        pass


def click(grid, index, state=0):
    """Simulate a click on the cell at the given filtered index."""
    col = index % grid.columns
    row = index // grid.columns
    x = 10 + col * grid.cell_w + 5     # PAD + col*cell + a bit inside
    y = 10 + row * grid.cell_h + 5
    grid._on_click(FakeEvent(x, y, state))


@requires_display
class TestGridSelection:
    def test_single_click_selects_one(self, app):
        app.grid.columns = 3
        click(app.grid, 4)
        selected = app.grid.selected_photos()
        assert len(selected) == 1
        assert selected[0] is app.grid.filtered[4]

    def test_ctrl_click_toggles(self, app):
        app.grid.columns = 3
        click(app.grid, 0)
        click(app.grid, 2, state=0x0004)   # ctrl
        assert len(app.grid.selection) == 2
        click(app.grid, 0, state=0x0004)   # ctrl again removes
        assert len(app.grid.selection) == 1

    def test_shift_click_selects_range(self, app):
        app.grid.columns = 3
        click(app.grid, 1)
        click(app.grid, 3, state=0x0001)   # shift
        selected = app.grid.selected_photos()
        assert len(selected) == 3
        assert {p.name for p in selected} == set(
            app.grid.filtered[i].name for i in (1, 2, 3))

    def test_plain_click_replaces_selection(self, app):
        app.grid.columns = 3
        click(app.grid, 0, state=0x0004)
        click(app.grid, 1, state=0x0004)
        click(app.grid, 2)                  # no modifier -> replace
        assert len(app.grid.selection) == 1

    def test_click_on_empty_area_clears(self, app):
        app.grid.columns = 3
        click(app.grid, 0)
        app.grid._on_click(FakeEvent(5, 100000, state=0))  # far below grid
        assert app.grid.selection == set()

    def test_select_all_and_clear(self, app):
        app.grid.select_all()
        assert len(app.grid.selection) == len(app.grid.filtered)
        app.grid.clear_selection()
        assert app.grid.selection == set()

    def test_move_selection_clamps_and_updates_anchor(self, app):
        app.grid.columns = 3
        click(app.grid, 0)
        app.grid.move_selection(1)
        assert app.grid.selected_photos()[0] is app.grid.filtered[1]
        app.grid.move_selection(-50)                    # clamps at 0
        assert app.grid.selected_photos()[0] is app.grid.filtered[0]
        app.grid.move_selection(500)                    # clamps at end
        last = len(app.grid.filtered) - 1
        assert app.grid.selected_photos()[0] is app.grid.filtered[last]

    def test_remove_paths_drops_selection_and_photos(self, app):
        victim = app.grid.filtered[0]
        app.grid.select_all()
        app.grid.remove_paths([str(victim.path)])
        assert str(victim.path) not in app.grid.selection
        assert victim not in app.grid.photos
        assert len(app.grid.filtered) == len(app.all_photos) - 1


@requires_display
class TestFilters:
    def test_flag_filters(self, app):
        photos = app.grid.filtered
        app.grid.selection = {str(photos[0].path), str(photos[1].path)}
        app.flag_selection("pick")
        app.grid.selection = {str(photos[2].path)}
        app.flag_selection("reject")

        for name, expected in (
            ("Picks", {photos[0].name, photos[1].name}),
            ("Rejected", {photos[2].name}),
            ("Without rejects", {p.name for p in photos} - {photos[2].name}),
            ("Unflagged", {p.name for p in photos[2:]} - {photos[2].name}),
        ):
            app.filter_box.set(name)
            app._filter_changed()
            assert {p.name for p in app.grid.filtered} == expected, name

    def test_untagged_filter(self, app):
        photos = app.grid.filtered
        app.grid.selection = {str(photos[0].path)}
        app._add_tag("alps")
        app.filter_box.set("Untagged")
        app._filter_changed()
        assert {p.name for p in app.grid.filtered} == \
            {p.name for p in photos} - {photos[0].name}

    def test_tag_text_filter(self, app):
        photos = app.grid.filtered
        app.grid.selection = {str(photos[0].path), str(photos[1].path)}
        app._add_tag("alps")
        app.grid.selection = {str(photos[2].path)}
        app._add_tag("beach")

        app.tag_filter_entry.delete(0, "end")
        app.tag_filter_entry.insert(0, "alps")
        app._tag_filter_entered()
        assert {p.name for p in app.grid.filtered} == {photos[0].name, photos[1].name}

    def test_all_photos_shows_everything(self, app):
        app.filter_box.set("Rejected")
        app._filter_changed()
        assert app.grid.filtered == []
        app.filter_box.set("All photos")
        app._filter_changed()
        assert len(app.grid.filtered) == len(app.all_photos)


@requires_display
class TestOperations:
    def test_flag_selection_persists_sidecars(self, app, photo_dir):
        photos = app.grid.filtered[:3]
        app.grid.selection = {str(p.path) for p in photos}
        app.flag_selection("pick")
        for p in photos:
            assert load_photo(photo_dir / p.name).flag == "pick"

    def test_rotate_selection_persists(self, app, photo_dir):
        photos = app.grid.filtered[:2]
        app.grid.selection = {str(p.path) for p in photos}
        app.rotate_selection(90)
        for p in photos:
            assert load_photo(photo_dir / p.name).rotation == 90

    def test_rotate_selection_remaps_crop(self, app, photo_dir):
        photo = app.grid.filtered[0]
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        app.grid.selection = {str(photo.path)}
        app.rotate_selection(90)
        stored = load_photo(photo_dir / photo.name)
        assert stored.rotation == 90
        assert all(abs(a - b) < 1e-9 for a, b in
                   zip(stored.crop, (0.1, 0.1, 0.8, 0.8)))

    def test_add_and_remove_tags(self, app, photo_dir):
        photos = app.grid.filtered[:3]
        app.grid.selection = {str(p.path) for p in photos}
        app._add_tag("alps, trip")
        for p in photos:
            assert load_photo(photo_dir / p.name).tags == {"alps", "trip"}

        app._remove_tag("alps")
        for p in photos:
            assert load_photo(photo_dir / p.name).tags == {"trip"}

    def test_delete_selection_moves_to_trash(self, app, photo_dir, monkeypatch):
        import tkinter.messagebox
        monkeypatch.setattr(tkinter.messagebox, "askyesno", lambda *a, **k: True)
        victims = app.grid.filtered[:2]
        app.grid.selection = {str(p.path) for p in victims}
        app.delete_selection()

        trash = photo_dir / ".photofx_trash"
        for p in victims:
            assert (trash / p.name).exists()
            assert not p.path.exists()
        assert len(app.grid.filtered) == len(app.all_photos) == 4

    def test_selection_status_shows_common_tags(self, app):
        photos = app.grid.filtered[:2]
        app.grid.selection = {str(p.path) for p in photos}
        app._add_tag("shared")
        assert "#shared" in app.status.cget("text")


@requires_display
class TestKeyboardGuard:
    def test_typing_guard_classifies_focus(self, app, monkeypatch):
        monkeypatch.setattr(app, "focus_get", lambda: None)
        assert app._typing() is False          # grid/nowhere -> shortcuts fire
        monkeypatch.setattr(app, "focus_get", lambda: app.grid)
        assert app._typing() is False
        monkeypatch.setattr(app, "focus_get", lambda: app.tag_entry)
        assert app._typing() is True          # text entry -> shortcuts suppressed

    def test_single_keys_ignored_while_typing(self, app, monkeypatch):
        app.grid.select_all()
        app.flag_selection(None)
        monkeypatch.setattr(app, "focus_get", lambda: app.tag_entry)
        app._key_actions["p"]()
        app.update()
        assert all(p.flag is None for p in app.grid.selected_photos()), \
            "P must not flag while typing in the tag entry"

    def test_single_keys_work_when_grid_focused(self, app, monkeypatch):
        app.grid.select_all()
        app.flag_selection(None)
        monkeypatch.setattr(app, "focus_get", lambda: None)
        app._key_actions["p"]()
        app.update()
        assert all(p.flag == "pick" for p in app.grid.selected_photos())


@requires_display
class TestThumbnailWorker:
    def _wait_for(self, app, cond, timeout=20.0):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_worker_populates_disk_cache_and_grid(self, app, photo_dir):
        cache_dir = photo_dir / ".photofx_cache" / "thumbs"
        assert self._wait_for(app, lambda: len(list(cache_dir.glob("*.jpg"))) >= 6)
        assert self._wait_for(app, lambda: len(app.grid.tk_images) >= 6)
        # every visible cell now shows a real image item
        for photo in app.grid.filtered:
            assert app.grid.find_withtag("img:" + str(photo.path))

    def test_worker_uses_cache_on_refilter(self, app, photo_dir):
        self._wait_for(app, lambda: len(app.grid.tk_images) >= 6)
        before = len(app.grid.tk_images)
        app.grid.select_all()
        app.flag_selection("pick")          # forces badge redraw + refresh_cells
        app.filter_box.set("Picks")
        app._filter_changed()
        assert self._wait_for(app, lambda: len(app.grid.tk_images) == 6)
        assert before == 6  # nothing was lost by the filter round-trip

    def test_purge_on_delete(self, app, photo_dir, monkeypatch):
        import tkinter.messagebox
        monkeypatch.setattr(tkinter.messagebox, "askyesno", lambda *a, **k: True)
        cache_dir = photo_dir / ".photofx_cache" / "thumbs"
        assert self._wait_for(app, lambda: len(list(cache_dir.glob("*.jpg"))) >= 6)
        victim = app.grid.filtered[0]
        app.grid.selection = {str(victim.path)}
        app.delete_selection()
        remaining = list(cache_dir.glob("*.jpg"))
        assert len(remaining) == 5  # only the victim's thumbnails were purged
        # the victim's cache entry is really gone
        from photofx.lib.render import DiskThumbCache
        assert DiskThumbCache(photo_dir).get(victim, app.grid.thumb_size) is None


@requires_display
class TestIcons:
    def test_all_toolbar_icons_load(self, app):
        for name in ("folder", "arrow-left", "arrow-right", "star",
                     "star-off", "close", "pencil", "trash"):
            photo_img = icons.load(name)
            assert photo_img is not None, f"missing icon: {name}"
            assert photo_img.width() <= 32

    def test_missing_icon_returns_none(self, app):
        assert icons.load("does-not-exist") is None


@requires_display
class TestEmbeddedViewer:
    """The grid app launching the viewer window over its current selection."""

    def test_open_viewer_and_apply_crop(self, app, photo_dir):
        photo = app.grid.filtered[0]
        app.open_viewer(photo)
        viewer = app.viewer
        viewer.update_idletasks()
        viewer.toggle_crop()
        viewer.draft = [0.1, 0.1, 0.6, 0.7]
        viewer.apply_crop()
        stored = load_photo(photo_dir / photo.name)
        assert stored.crop == (0.1, 0.1, 0.6, 0.7)
        viewer.destroy()

    def test_viewer_delete_updates_grid(self, app, photo_dir, monkeypatch):
        import tkinter.messagebox
        monkeypatch.setattr(tkinter.messagebox, "askyesno", lambda *a, **k: True)
        photo = app.grid.filtered[0]
        app.open_viewer(photo)
        viewer = app.viewer
        viewer.update_idletasks()
        viewer._delete_current()
        assert not photo.path.exists()
        assert (photo_dir / ".photofx_trash" / photo.name).exists()
        assert photo not in app.grid.photos
        assert photo not in viewer.photos
        assert viewer.index < len(viewer.photos)
        viewer.destroy()
