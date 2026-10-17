"""EXIF and file metadata: the data shown in the viewer's info pane.

:func:`photo_info` turns a photo into sections of ``(label, value)`` rows
— the File facts always known, plus the camera data (EXIF) when present.
Rows whose value is unknown are dropped, so a photo without EXIF simply
shows the File section only.
"""

from __future__ import annotations

from fractions import Fraction

from PIL import Image
from PIL.ExifTags import IFD

from .catalog import Photo

# EXIF tag ids (kept local: ExifTags.TAGS maps ids to names, not the other way)
MAKE = 271
MODEL = 272
DATETIME = 306
EXPOSURE_TIME = 33434
FNUMBER = 33437
ISO = 34855
DATETIME_ORIGINAL = 36867
FOCAL_LENGTH = 37386
LENS_MODEL = 42036


def photo_info(photo: Photo) -> list[tuple[str, list[tuple[str, str]]]]:
    """The info pane's content: section title -> (label, value) rows."""
    file_rows = _file_rows(photo)
    camera_rows = _camera_rows(photo.path)
    sections = [("File", file_rows)]
    if camera_rows:
        sections.append(("Camera", camera_rows))
    return sections


# -------------------------------------------------------------- file facts
def _file_rows(photo: Photo) -> list[tuple[str, str]]:
    rows = [("Name", photo.name)]
    try:
        img = Image.open(photo.path)
        fmt = img.format or photo.path.suffix.lstrip(".").upper()
        rows.append(("Format", fmt.upper()))
        rows.append(("Dimensions", f"{img.size[0]} x {img.size[1]} px"))
    except Exception:
        pass
    try:
        size = photo.path.stat().st_size
        rows.append(("Size", _file_size(size)))
        rows.append(("Modified", _timestamp(photo.path.stat().st_mtime)))
    except OSError:
        pass
    return rows


def _file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(1, size // 1024)} KB"


def _timestamp(mtime: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------- camera data
def _camera_rows(path) -> list[tuple[str, str]]:
    try:
        exif = Image.open(path).getexif()
    except Exception:
        return []
    sub = exif.get_ifd(IFD.Exif)

    def get(tag):
        value = sub.get(tag, exif.get(tag))
        return None if value in (None, "") else value

    rows = [
        ("Camera", _join(_text(get(MAKE)), _text(get(MODEL)))),
        ("Date taken", _exif_date(get(DATETIME_ORIGINAL) or get(DATETIME))),
        ("Exposure", _exposure(get(EXPOSURE_TIME))),
        ("Aperture", _aperture(get(FNUMBER))),
        ("ISO", _iso(get(ISO))),
        ("Focal length", _focal(get(FOCAL_LENGTH))),
        ("Lens", _text(get(LENS_MODEL))),
    ]
    return [(label, value) for label, value in rows if value]


def _text(value) -> str | None:
    """Decode a possibly-bytes EXIF string; empty/unknown becomes None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    value = str(value).strip()
    return value or None


def _join(*parts: str | None) -> str | None:
    out = " ".join(p for p in parts if p)
    return out or None


def _exif_date(raw) -> str | None:
    """'2024:05:01 10:20:29' -> '2024-05-01 10:20:29'."""
    text = _text(raw)
    if text is None:
        return None
    return text.replace(":", "-", 2)


def _rational(value) -> Fraction | None:
    if value is None:
        return None
    try:
        if isinstance(value, Fraction):
            return value
        num = getattr(value, "numerator", None)
        den = getattr(value, "denominator", None)
        if num is not None and den:
            return Fraction(num, den)
        return Fraction(float(value)).limit_denominator(1000000)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _exposure(raw) -> str | None:
    fraction = _rational(raw)
    if fraction is None:
        return None
    if fraction.denominator == 1:
        return f"{fraction.numerator} s"
    return f"{fraction.numerator}/{fraction.denominator} s"


def _aperture(raw) -> str | None:
    fraction = _rational(raw)
    if fraction is None or fraction <= 0:
        return None
    return f"f/{float(fraction):g}"


def _iso(raw) -> str | None:
    if isinstance(raw, (tuple, list)):    # some files store several ratings
        raw = raw[0] if raw else None
    text = _text(raw)
    if text is None:
        return None
    try:
        return f"ISO {int(float(text))}"
    except ValueError:
        return text


def _focal(raw) -> str | None:
    fraction = _rational(raw)
    if fraction is None or fraction <= 0:
        return None
    return f"{float(fraction):g} mm"
