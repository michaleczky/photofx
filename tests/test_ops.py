"""Tests for photofx.lib.ops: shared rotation and delete operations."""

from __future__ import annotations

from photofx.lib.catalog import load_photo, scan_folder
from photofx.lib.ops import apply_rotation, delete_photo


class TestApplyRotation:
    def test_rotation_accumulates(self, photo_factory):
        photo = load_photo(photo_factory())
        apply_rotation(photo, 90)
        assert photo.rotation == 90
        apply_rotation(photo, 90)
        assert photo.rotation == 180
        apply_rotation(photo, -90)
        assert photo.rotation == 90
        apply_rotation(photo, 270)
        assert photo.rotation == 0

    def test_crop_untouched_without_crop(self, photo_factory):
        photo = load_photo(photo_factory())
        photo.crop = None
        apply_rotation(photo, 90)
        assert photo.crop is None

    def test_crop_remap_90(self, photo_factory):
        photo = load_photo(photo_factory())
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        apply_rotation(photo, 90)
        assert photo.crop == (1 - 0.9, 0.1, 1 - 0.2, 0.8)

    def test_crop_remap_270(self, photo_factory):
        photo = load_photo(photo_factory())
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        apply_rotation(photo, -90)
        assert photo.crop == (0.2, 1 - 0.8, 0.9, 1 - 0.1)

    def test_crop_remap_180(self, photo_factory):
        photo = load_photo(photo_factory())
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        apply_rotation(photo, 180)
        assert photo.crop == (1 - 0.8, 1 - 0.9, 1 - 0.1, 1 - 0.2)

    def test_full_circle_returns_identity(self, photo_factory):
        photo = load_photo(photo_factory())
        photo.rotation = 90
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        start = (photo.rotation, photo.crop)
        for _ in range(4):
            apply_rotation(photo, 90)
        assert photo.rotation == start[0]
        assert all(abs(a - b) < 1e-9 for a, b in zip(photo.crop, start[1]))

    def test_360_in_one_call_changes_nothing(self, photo_factory):
        photo = load_photo(photo_factory())
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        apply_rotation(photo, 360)
        assert photo.rotation == 0
        assert photo.crop == (0.1, 0.2, 0.8, 0.9)


class TestDeletePhoto:
    def test_moves_to_trash_and_returns_path(self, photo_dir):
        photo = scan_folder(photo_dir)[0]
        trash = delete_photo(photo_dir, photo)
        assert trash == photo_dir / ".photofx_trash"
        assert (trash / photo.name).exists()
        assert not photo.path.exists()

    def test_falls_back_to_own_folder(self, photo_dir):
        photo = scan_folder(photo_dir)[0]
        trash = delete_photo(None, photo)
        assert trash == photo_dir / ".photofx_trash"
        assert (trash / photo.name).exists()

    def test_preserves_subfolders(self, photo_dir):
        photo = next(p for p in scan_folder(photo_dir) if p.path.parent.name == "sub")
        delete_photo(photo_dir, photo)
        assert (photo_dir / ".photofx_trash" / "sub" / photo.name).exists()
