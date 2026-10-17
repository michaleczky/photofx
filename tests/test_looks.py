"""Tests for photofx.lib.looks: the named filter recipes."""

from __future__ import annotations

from PIL import Image

from photofx.lib.looks import LOOKS, apply_look

NEUTRAL = (128, 128, 128)


def solid(color, size=(300, 200)) -> Image.Image:
    return Image.new("RGB", size, color)


class TestApplyLook:
    def test_no_look_returns_same_object(self):
        img = solid(NEUTRAL)
        assert apply_look(img, None) is img
        assert apply_look(img, "") is img

    def test_unknown_look_returns_same_object(self):
        img = solid(NEUTRAL)
        assert apply_look(img, "no-such-look") is img

    def test_every_look_accepts_gray_images(self):
        for name in LOOKS:
            out = apply_look(Image.new("L", (40, 30), 100), name)
            assert out.size == (40, 30)
            assert out.mode == "RGB"

    def test_look_names_and_captions_differ(self):
        assert set(LOOKS) == {"mono", "sepia", "noir", "vivid", "fade",
                              "golden", "arctic"}
        assert all(LOOKS[name] != name for name in LOOKS)


class TestTheLooks:
    def test_mono_is_gray(self):
        out = apply_look(solid((200, 60, 120)), "mono")
        r, g, b = out.getpixel((5, 5))
        assert r == g == b

    def test_sepia_is_warm_gray(self):
        out = apply_look(solid((200, 60, 120)), "sepia")
        r, g, b = out.getpixel((5, 5))
        assert r > g > b

    def test_noir_is_harder_than_mono(self):
        img = solid((200, 60, 120))
        mono = apply_look(img, "mono")
        noir = apply_look(img, "noir")
        # same gray conversion, extra contrast around 128 pushes mid tones down
        assert noir.getpixel((5, 5))[0] < mono.getpixel((5, 5))[0]

    def test_fade_lifts_the_blacks(self):
        out = apply_look(solid((0, 0, 0)), "fade")
        assert out.getpixel((5, 5))[0] > 0

    def test_fade_pulls_the_highlights(self):
        out = apply_look(solid((255, 255, 255)), "fade")
        assert out.getpixel((5, 5))[0] < 255

    def test_vivid_punches_saturation(self):
        out = apply_look(solid((200, 60, 120)), "vivid")
        r, g, b = out.getpixel((5, 5))
        assert (r - g) > (200 - 60)

    def test_golden_warms(self):
        out = apply_look(solid(NEUTRAL), "golden")
        r, _g, b = out.getpixel((5, 5))
        assert r > b

    def test_arctic_cools(self):
        out = apply_look(solid(NEUTRAL), "arctic")
        r, _g, b = out.getpixel((5, 5))
        assert b > r

    def test_tone_looks_stay_in_range(self):
        for name in ("vivid", "fade", "golden", "arctic", "noir"):
            out = apply_look(solid((0, 128, 255)), name)
            for v in out.getpixel((5, 5)):
                assert 0 <= v <= 255
