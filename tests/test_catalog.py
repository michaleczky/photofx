"""Tests for photofx.catalog: scanning, sidecar JSON, trash."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from photofx.catalog import (
    PICK,
    REJECT,
    TRASH_DIRNAME,
    load_photo,
    move_to_trash,
    save_photo,
    scan_folder,
)
from tests.conftest import make_image

EXPECTED_NAMES = {"IMG_0001.jpg", "IMG_0002.jpg", "beach.png",
                  "sunset.jpg", "portrait.tif", "DSC_0099.webp"}


class TestScan:
    def test_finds_images_recursively(self, photo_dir):
        photos = scan_folder(photo_dir)
        assert {p.name for p in photos} == EXPECTED_NAMES
        assert len(photos) == 6

    def test_sorted_case_insensitively(self, photo_dir):
        photos = scan_folder(photo_dir)
        names = [p.name.lower() for p in photos]
        assert names == sorted(names)

    def test_skips_hidden_directories(self, photo_dir):
        (photo_dir / ".holidays").mkdir()
        make_image(photo_dir / ".holidays" / "secret.jpg", (100, 100), (10, 10, 10))
        assert len(scan_folder(photo_dir)) == 6

    def test_skips_trash_folder(self, photo_dir):
        (photo_dir / TRASH_DIRNAME).mkdir()
        make_image(photo_dir / TRASH_DIRNAME / "gone.jpg", (100, 100), (10, 10, 10))
        assert len(scan_folder(photo_dir)) == 6

    def test_ignores_non_image_files(self, photo_dir):
        (photo_dir / "notes.txt").write_text("hello")
        (photo_dir / "video.mp4").write_bytes(b"x")
        assert len(scan_folder(photo_dir)) == 6

    def test_missing_folder_returns_empty(self, tmp_path):
        assert scan_folder(tmp_path / "nope") == []

    def test_sidecar_json_files_are_not_images(self, photo_dir):
        photo = scan_folder(photo_dir)[0]
        save_photo(photo)  # writes IMG_0001.jpg.json
        assert len(scan_folder(photo_dir)) == 6


class TestSidecar:
    def test_new_photo_has_defaults(self, photo_dir):
        photo = load_photo(photo_dir / "IMG_0001.jpg")
        assert photo.flag is None
        assert photo.rotation == 0
        assert photo.crop is None
        assert photo.tags == set()

    def test_roundtrip(self, photo_dir):
        path = photo_dir / "IMG_0001.jpg"
        photo = load_photo(path)
        photo.flag = PICK
        photo.rotation = 270
        photo.tags = {"alps", "trip 2026"}
        photo.crop = (0.1, 0.2, 0.8, 0.9)
        save_photo(photo)

        data = json.loads((photo_dir / "IMG_0001.jpg.json").read_text())
        assert data["flag"] == "pick"
        assert data["rotation"] == 270
        assert data["tags"] == ["alps", "trip 2026"]
        assert data["crop"] == [0.1, 0.2, 0.8, 0.9]

        reloaded = load_photo(path)
        assert reloaded.flag == PICK
        assert reloaded.rotation == 270
        assert reloaded.crop == (0.1, 0.2, 0.8, 0.9)
        assert reloaded.tags == {"alps", "trip 2026"}

    def test_empty_metadata_writes_minimal_sidecar(self, photo_dir):
        path = photo_dir / "beach.png"
        photo = load_photo(path)
        save_photo(photo)
        data = json.loads((photo_dir / "beach.png.json").read_text())
        assert data == {"flag": None, "rotation": 0, "tags": []}

    def test_tolerates_invalid_json(self, photo_dir):
        path = photo_dir / "beach.png"
        (photo_dir / "beach.png.json").write_text("{not json")
        photo = load_photo(path)
        assert photo.flag is None and photo.rotation == 0

    def test_tolerates_bad_values(self, photo_dir):
        path = photo_dir / "beach.png"
        (photo_dir / "beach.png.json").write_text(json.dumps({
            "flag": "weird",
            "rotation": 45,          # not a multiple of 90 -> ignored
            "crop": [0.1, 0.2],      # wrong length -> ignored
            "tags": "not-a-list",    # wrong type -> ignored
        }))
        photo = load_photo(path)
        assert photo.flag is None
        assert photo.rotation == 0
        assert photo.crop is None
        assert photo.tags == set()

    def test_reject_flag_roundtrip(self, photo_dir):
        path = photo_dir / "IMG_0002.jpg"
        photo = load_photo(path)
        photo.flag = REJECT
        save_photo(photo)
        assert load_photo(path).flag == REJECT

    def test_crop_is_normalized_on_load(self, photo_dir):
        path = photo_dir / "beach.png"
        (photo_dir / "beach.png.json").write_text(json.dumps({
            "flag": None, "rotation": 0, "tags": [], "crop": [0.8, 0.9, 0.1, 0.2],
        }))
        photo = load_photo(path)
        assert photo.crop == (0.1, 0.2, 0.8, 0.9)

    def test_original_file_is_never_modified(self, photo_dir):
        path = photo_dir / "IMG_0001.jpg"
        before = path.read_bytes()
        photo = load_photo(path)
        photo.rotation, photo.flag, photo.crop = 90, PICK, (0, 0, 1, 1)
        save_photo(photo)
        assert path.read_bytes() == before


class TestTrash:
    def test_moves_photo_and_sidecar(self, photo_dir):
        photo = load_photo(photo_dir / "IMG_0001.jpg")
        photo.tags = {"x"}
        save_photo(photo)
        move_to_trash(photo_dir, photo)

        dest = photo_dir / TRASH_DIRNAME / "IMG_0001.jpg"
        assert dest.exists()
        assert (photo_dir / TRASH_DIRNAME / "IMG_0001.jpg.json").exists()
        assert not photo.path.exists()
        assert not photo.sidecar.exists()

    def test_preserves_subfolder_structure(self, photo_dir):
        photo = load_photo(photo_dir / "sub" / "portrait.tif")
        move_to_trash(photo_dir, photo)
        assert (photo_dir / TRASH_DIRNAME / "sub" / "portrait.tif").exists()

    def test_renames_on_name_collision(self, photo_dir):
        # two different files with the same name in different folders
        make_image(photo_dir / "sub" / "IMG_0001.jpg", (64, 64), (1, 2, 3))
        first = load_photo(photo_dir / "IMG_0001.jpg")
        second = load_photo(photo_dir / "sub" / "IMG_0001.jpg")
        move_to_trash(photo_dir, first)
        move_to_trash(photo_dir, second)

        assert (photo_dir / TRASH_DIRNAME / "IMG_0001.jpg").exists()
        renamed = photo_dir / TRASH_DIRNAME / "sub" / "IMG_0001.jpg"
        assert renamed.exists() or (photo_dir / TRASH_DIRNAME / "sub" / "IMG_0001_.jpg.jpg").exists()

    def test_trash_is_excluded_from_rescan(self, photo_dir):
        photo = load_photo(photo_dir / "sunset.jpg")
        move_to_trash(photo_dir, photo)
        photos = scan_folder(photo_dir)
        assert "sunset.jpg" not in {p.name for p in photos}
        assert len(photos) == 5
