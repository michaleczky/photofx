"""Tests for photofx.lib.edits: the slider math and the Auto suggestion."""

from __future__ import annotations

import math

import pytest
from PIL import Image

from photofx.lib.edits import auto_edits, apply_edits, is_default

NEUTRAL = (128, 128, 128)


def solid(color, size=(300, 200)) -> Image.Image:
    return Image.new("RGB", size, color)


class TestIsDefault:
    def test_empty_is_default(self):
        assert is_default({})

    def test_zero_values_are_default(self):
        assert is_default({"exposure": 0.0, "temp": 0})

    def test_any_nonzero_is_an_edit(self):
        assert not is_default({"temp": -5})


class TestApplyEdits:
    def test_default_returns_same_object(self):
        img = solid(NEUTRAL)
        assert apply_edits(img, {}) is img
        assert apply_edits(img, {"contrast": 0, "tint": 0.0}) is img

    def test_exposure_brightens_linearly(self):
        img = solid((60, 60, 60))
        out = apply_edits(img, {"exposure": 1.0})     # +1 EV = double
        assert out.getpixel((5, 5)) == (120, 120, 120)

    def test_negative_exposure_darkens(self):
        img = solid((200, 200, 200))
        out = apply_edits(img, {"exposure": -1.0})
        assert out.getpixel((5, 5)) == (100, 100, 100)

    def test_highlights_clip_at_255(self):
        img = solid((200, 200, 200))
        out = apply_edits(img, {"exposure": 2.0})    # x4 -> 800
        assert out.getpixel((5, 5)) == (255, 255, 255)

    def test_temp_positive_warms(self):
        img = solid((100, 100, 100))
        out = apply_edits(img, {"temp": 50})
        r, g, b = out.getpixel((5, 5))
        assert r > g > b

    def test_temp_negative_cools(self):
        img = solid((100, 100, 100))
        out = apply_edits(img, {"temp": -50})
        r, g, b = out.getpixel((5, 5))
        assert b > g > r

    def test_tint_positive_is_magenta(self):
        img = solid((100, 100, 100))
        out = apply_edits(img, {"tint": 50})
        r, g, b = out.getpixel((5, 5))
        assert g < r and g < b

    def test_saturation_minus_100_is_grayscale(self):
        img = solid((200, 40, 40))
        out = apply_edits(img, {"saturation": -100})
        r, g, b = out.getpixel((5, 5))
        assert r == g == b

    def test_saturation_50_boosts_color(self):
        img = solid((150, 100, 100))
        out = apply_edits(img, {"saturation": 50})
        r, g, b = out.getpixel((5, 5))
        assert r - g > 50          # spread wider than the original 50
        assert b == g              # equal channels stay equal

    def test_contrast_stretches_around_the_mean(self):
        # Pillow's Contrast pivots at the image's mean gray
        img = Image.new("RGB", (20, 2))
        for x in range(20):
            for y in range(2):
                img.putpixel((x, y), (60, 60, 60) if x < 10 else (190, 190, 190))
        out = apply_edits(img, {"contrast": 50})     # factor 1.5
        assert out.getpixel((0, 0))[0] <= 30          # 60 moves away from mean
        assert out.getpixel((15, 0))[0] >= 220        # 190 moves away from mean

    def test_does_not_mutate_input(self):
        img = solid((100, 120, 140))
        before = img.copy()
        apply_edits(img, {"exposure": 1.0, "temp": 30})
        assert img.getpixel((5, 5)) == before.getpixel((5, 5))

    def test_non_rgb_mode_is_converted(self):
        img = solid((200, 100, 100)).convert("L")
        out = apply_edits(img, {"exposure": 1.0})
        assert out.mode == "RGB"
        assert out.getpixel((5, 5))[0] == 255

    def test_scale_independent(self):
        """Same edits on a big and a small render give matching pixels."""
        img = solid((100, 140, 200), (1200, 800))
        small = img.resize((60, 40), Image.LANCZOS)
        a = apply_edits(img, {"exposure": 0.5, "temp": 30})
        b = apply_edits(small, {"exposure": 0.5, "temp": 30})
        assert a.getpixel((0, 0)) == b.getpixel((0, 0))


class TestAutoEdits:
    def test_neutral_image_suggests_little(self):
        # 18% sRGB gray is the exposure target: almost nothing to do
        out = auto_edits(solid((118, 118, 118)))
        assert abs(out.get("exposure", 0.0)) <= 0.05
        assert out.get("temp", 0) == 0
        assert out.get("tint", 0) == 0

    def test_blue_cast_gets_warmed(self):
        out = auto_edits(solid((70, 110, 190)))
        assert out.get("temp", 0) > 0          # yellow up, blue down

    def test_orange_cast_gets_cooled(self):
        out = auto_edits(solid((190, 110, 70)))
        assert out.get("temp", 0) < 0

    def test_green_cast_gets_magenta_tint(self):
        out = auto_edits(solid((110, 190, 110)))
        assert out.get("tint", 0) > 0

    def test_dark_image_gets_positive_exposure(self):
        out = auto_edits(solid((40, 40, 40)))
        assert out.get("exposure", 0.0) > 0

    def test_bright_image_gets_negative_exposure(self):
        out = auto_edits(solid((240, 240, 240)))
        assert out.get("exposure", 0.0) < 0

    def test_exposure_is_clamped(self):
        out = auto_edits(solid((2, 2, 2)))
        assert out["exposure"] <= 1.5
        out = auto_edits(solid((254, 254, 254)))
        assert out["exposure"] >= -1.5

    def test_only_known_keys_returned(self):
        from photofx.lib.catalog import EDIT_KEYS
        out = auto_edits(solid((70, 110, 190)))
        assert set(out) <= set(EDIT_KEYS)
        assert all(v != 0 for v in out.values())

    def test_suggested_edits_really_balance_the_image(self):
        """After applying Auto's WB, channel means should be near equal."""
        img = solid((90, 115, 160))     # mild cast, no clamping needed
        out = auto_edits(img)
        edited = apply_edits(img, out)
        r, g, b = edited.getpixel((5, 5))
        assert abs(r - g) <= 4 and abs(b - g) <= 4

    def test_works_from_large_image_quickly(self):
        import time
        img = solid((70, 110, 190), (4000, 3000))
        start = time.monotonic()
        auto_edits(img)
        assert time.monotonic() - start < 2.0   # samples, no full-res math
