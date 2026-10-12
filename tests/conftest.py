"""Shared fixtures: sample photo trees and a Tk root when a display exists."""

from __future__ import annotations

import random
import tkinter as tk

import pytest
from PIL import Image, ImageDraw

SPECS = [
    # (name, size, color, subfolder)
    ("IMG_0001.jpg", (1600, 1200), (180, 90, 60), ""),
    ("IMG_0002.jpg", (1200, 1600), (60, 120, 180), ""),
    ("beach.png", (2000, 1300), (80, 160, 200), ""),
    ("sunset.jpg", (2400, 1600), (220, 120, 60), ""),
    ("portrait.tif", (900, 1400), (120, 100, 160), "sub"),
    ("DSC_0099.webp", (1000, 700), (100, 200, 100), ""),
]


def make_image(path, size, color, seed=0):
    rng = random.Random(seed)
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    for _ in range(30):
        x, y = rng.randint(0, size[0] - 1), rng.randint(0, size[1] - 1)
        r = rng.randint(5, 60)
        c = tuple(min(255, v + rng.randint(-60, 60)) for v in color)
        draw.ellipse([x, y, x + r, y + r], fill=c)
    img.save(path)
    return img


@pytest.fixture
def photo_dir(tmp_path):
    """A folder tree with six sample photos (jpg/png/tif/webp, one nested)."""
    root = tmp_path / "vacation"
    (root / "sub").mkdir(parents=True)
    for i, (name, size, color, sub) in enumerate(SPECS):
        make_image(root / sub / name, size, color, seed=i)
    return root


@pytest.fixture
def photo_factory(tmp_path):
    """Callable(name, size=(w,h), color=(r,g,b), exif_orientation=None) -> Path."""
    folder = tmp_path / "single"
    folder.mkdir()

    def make(name="test.jpg", size=(800, 600), color=(90, 120, 180), exif_orientation=None):
        img = Image.new("RGB", size, color)
        path = folder / name
        if exif_orientation is not None:
            exif = Image.Exif()
            exif[274] = exif_orientation  # Orientation tag
            img.save(path, exif=exif)
        else:
            img.save(path)
        return path

    return make


def _display_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


DISPLAY_OK = _display_available()
