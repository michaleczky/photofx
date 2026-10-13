"""Shared edit operations used by both applications."""

from __future__ import annotations

from pathlib import Path

from .catalog import TRASH_DIRNAME, Photo, move_to_trash


def apply_rotation(photo: Photo, degrees: int) -> None:
    """Rotate by a quarter-turn multiple on top of the current metadata.

    Rotation is clockwise; an existing crop rect is remapped so the cropped
    area keeps covering the same pixels of the original.
    """
    degrees %= 360
    photo.rotation = (photo.rotation + degrees) % 360
    if photo.crop is None or degrees == 0:
        return
    x0, y0, x1, y1 = photo.crop
    if degrees == 90:
        photo.crop = (1 - y1, x0, 1 - y0, x1)
    elif degrees == 180:
        photo.crop = (1 - x1, 1 - y1, 1 - x0, 1 - y0)
    elif degrees == 270:
        photo.crop = (y0, 1 - x1, y1, 1 - x0)


def delete_photo(folder: Path | None, photo: Photo) -> Path:
    """Move a photo and its sidecar into the trash folder.

    ``folder`` is the catalog root (needed to preserve subfolder structure
    inside the trash); falls back to the photo's own parent directory.
    Returns the trash folder path.
    """
    root = folder or photo.path.parent
    move_to_trash(root, photo)
    return root / TRASH_DIRNAME
