"""Tests for photofx.lib.exif: the info pane's data source."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from tests.conftest import make_exif_image  # noqa: E402

from photofx.lib.catalog import load_photo  # noqa: E402
from photofx.lib.exif import photo_info  # noqa: E402


def rows(sections, section):
    for title, rows in sections:
        if title == section:
            return dict(rows)
    return {}


def test_plain_photo_shows_file_section_only(photo_dir):
    photo = load_photo(photo_dir / "IMG_0001.jpg")
    sections = photo_info(photo)
    assert [title for title, _ in sections] == ["File"]
    file_rows = rows(sections, "File")
    assert file_rows["Name"] == "IMG_0001.jpg"
    assert file_rows["Format"] == "JPEG"
    assert file_rows["Dimensions"] == "1600 x 1200 px"


def test_file_rows_report_size_and_mtime(photo_dir):
    from datetime import datetime

    photo = load_photo(photo_dir / "IMG_0001.jpg")
    stat = photo.path.stat()
    file_rows = rows(photo_info(photo), "File")
    assert file_rows["Size"].endswith(("KB", "MB"))
    assert file_rows["Modified"] == datetime.fromtimestamp(
        stat.st_mtime).strftime("%Y-%m-%d %H:%M")


def test_camera_rows_from_exif(photo_dir):
    path = make_exif_image(
        photo_dir / "IMG_0001.jpg",
        make="TestCam", model="Model X100",
        exposure=(1, 125), aperture=(56, 10), iso=200,
        focal_length=(240, 10), lens="Lens 24-70",
        date_taken="2024:05:01 10:20:29")
    photo = load_photo(path)
    camera = rows(photo_info(photo), "Camera")
    assert camera["Camera"] == "TestCam Model X100"
    assert camera["Exposure"] == "1/125 s"
    assert camera["Aperture"] == "f/5.6"
    assert camera["ISO"] == "ISO 200"
    assert camera["Focal length"] == "24 mm"
    assert camera["Lens"] == "Lens 24-70"
    assert camera["Date taken"] == "2024-05-01 10:20:29"


def test_exif_datetime_used_when_no_original(photo_dir):
    path = make_exif_image(photo_dir / "IMG_0001.jpg", datetime="2023:01:02 03:04:05")
    camera = rows(photo_info(load_photo(path)), "Camera")
    assert camera["Date taken"] == "2023-01-02 03:04:05"


def test_partial_exif_only_reports_known_values(photo_dir):
    path = make_exif_image(photo_dir / "IMG_0001.jpg",
                           model="Model X100", iso=400)
    camera = rows(photo_info(load_photo(path)), "Camera")
    assert camera == {"Camera": "Model X100", "ISO": "ISO 400"}


def test_whole_second_exposure_is_not_a_fraction(photo_dir):
    path = make_exif_image(photo_dir / "IMG_0001.jpg", exposure=(2, 1))
    camera = rows(photo_info(load_photo(path)), "Camera")
    assert camera["Exposure"] == "2 s"
