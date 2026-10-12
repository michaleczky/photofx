"""Tests for photofx.render: EXIF, rotation, crop pipeline, thumbnail cache."""

from __future__ import annotations

from photofx.catalog import Photo, load_photo
from photofx.render import ThumbCache, load_thumb, open_rotated, render


class TestOpenRotated:
    def test_exif_orientation_applied(self, photo_factory):
        path = photo_factory(size=(800, 600), exif_orientation=6)  # 90 CW
        assert open_rotated(Photo(path=path)).size == (600, 800)

    def test_exif_orientation_1_is_upright(self, photo_factory):
        path = photo_factory(size=(800, 600), exif_orientation=1)
        assert open_rotated(Photo(path=path)).size == (800, 600)

    def test_metadata_rotation_clockwise(self, photo_factory):
        path = photo_factory(size=(800, 600))
        photo = Photo(path=path, rotation=90)
        assert open_rotated(photo).size == (600, 800)   # 90 CW
        photo.rotation = 180
        assert open_rotated(photo).size == (800, 600)
        photo.rotation = 270
        assert open_rotated(photo).size == (600, 800)

    def test_exif_and_metadata_stack(self, photo_factory):
        # EXIF says 90 CW, sidecar says another 180 -> 270 total -> portrait again
        path = photo_factory(size=(800, 600), exif_orientation=6)
        photo = Photo(path=path, rotation=180)
        assert open_rotated(photo).size == (600, 800)


class TestRenderPipeline:
    def test_crop_in_original_space(self, photo_factory):
        path = photo_factory(size=(1000, 500))
        photo = Photo(path=path, crop=(0.1, 0.2, 0.6, 1.0))
        img = render(photo)
        assert img.size == (500, 400)   # 0.5*1000 x 0.8*500

    def test_crop_in_rotated_space(self, photo_factory):
        # crop coordinates refer to the image AFTER rotation is applied
        path = photo_factory(size=(800, 600))
        photo = Photo(path=path, rotation=90, crop=(0.0, 0.0, 0.5, 0.5))
        img = render(photo)
        assert img.size == (300, 400)  # rotated to 600x800, half of each

    def test_max_size_downscales_preserving_aspect(self, photo_factory):
        path = photo_factory(size=(2000, 1000))
        img = render(Photo(path=path), max_size=300)
        assert max(img.size) <= 300
        assert img.size == (300, 150)

    def test_max_size_never_upscales(self, photo_factory):
        path = photo_factory(size=(200, 100))
        assert render(Photo(path=path), max_size=300).size == (200, 100)

    def test_full_pipeline(self, photo_factory):
        path = photo_factory(size=(1600, 1200), exif_orientation=6)
        photo = Photo(path=path, rotation=90, crop=(0.25, 0.25, 0.75, 0.75))
        img = render(photo, max_size=400)
        # 1600x1200 --exif 90--> 1200x1600 --rot 90--> 1600x1200
        # crop half -> 800x600, downscaled to 400x300
        assert img.size == (400, 300)

    def test_corrupt_file_raises_in_render(self, tmp_path):
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"this is not an image")
        try:
            render(Photo(path=bad))
        except Exception:
            pass
        else:
            raise AssertionError("expected render() to raise on corrupt file")

    def test_load_thumb_returns_none_for_corrupt_file(self, tmp_path):
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"this is not an image")
        assert load_thumb(Photo(path=bad), 170) is None

    def test_load_thumb_fits_budget(self, photo_dir):
        photo = load_photo(photo_dir / "IMG_0001.jpg")
        thumb = load_thumb(photo, 170)
        assert thumb is not None
        assert max(thumb.size) <= 2 * 170  # load_thumb renders at 2x for quality

    def test_load_thumb_respects_rotation(self, photo_dir):
        photo = load_photo(photo_dir / "IMG_0002.jpg")   # 1200x1600 stored
        photo.rotation = 90
        thumb = load_thumb(photo, 170)
        assert thumb.size[0] > thumb.size[1]  # landscape after 90 CW


class TestThumbCache:
    def test_put_get_roundtrip(self, photo_dir):
        from PIL import Image
        cache = ThumbCache()
        photo = load_photo(photo_dir / "beach.png")
        img = Image.new("RGB", (16, 16))
        assert cache.get(photo, 16) is None
        cache.put(photo, 16, img)
        assert cache.get(photo, 16) is img

    def test_key_changes_with_rotation(self, photo_dir):
        from PIL import Image
        cache = ThumbCache()
        photo = load_photo(photo_dir / "beach.png")
        cache.put(photo, 16, Image.new("RGB", (16, 16)))
        photo.rotation = 90
        assert cache.get(photo, 16) is None   # stale entry must not be reused

    def test_key_changes_with_crop(self, photo_dir):
        from PIL import Image
        cache = ThumbCache()
        photo = load_photo(photo_dir / "beach.png")
        cache.put(photo, 16, Image.new("RGB", (16, 16)))
        photo.crop = (0.1, 0.1, 0.9, 0.9)
        assert cache.get(photo, 16) is None

    def test_evicts_oldest_beyond_max(self, photo_dir):
        from PIL import Image
        cache = ThumbCache(max_items=2)
        photos = [load_photo(photo_dir / n) for n in
                  ("IMG_0001.jpg", "IMG_0002.jpg", "beach.png")]
        cache.put(photos[0], 16, Image.new("RGB", (16, 16)))
        cache.put(photos[1], 16, Image.new("RGB", (16, 16)))
        cache.put(photos[2], 16, Image.new("RGB", (16, 16)))
        assert cache.get(photos[0], 16) is None      # evicted
        assert cache.get(photos[1], 16) is not None
        assert cache.get(photos[2], 16) is not None

    def test_drop_removes_all_sizes_for_path(self, photo_dir):
        from PIL import Image
        cache = ThumbCache()
        photo = load_photo(photo_dir / "beach.png")
        cache.put(photo, 16, Image.new("RGB", (16, 16)))
        cache.put(photo, 32, Image.new("RGB", (32, 32)))
        cache.drop(photo.path)
        assert cache.get(photo, 16) is None
        assert cache.get(photo, 32) is None
