"""Catalog: photo model, sidecar JSON metadata, folder scanning, trash."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
TRASH_DIRNAME = ".photofx_trash"

PICK = "pick"
REJECT = "reject"


@dataclass
class Photo:
    path: Path
    flag: str | None = None          # "pick" | "reject" | None
    rotation: int = 0                # 0, 90, 180, 270 (clockwise, on top of EXIF)
    crop: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 in 0..1, rotated space

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def sidecar(self) -> Path:
        return self.path.with_name(self.path.name + ".json")


def load_photo(path: Path) -> Photo:
    photo = Photo(path=path)
    sidecar = photo.sidecar
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if data.get("flag") in (PICK, REJECT):
            photo.flag = data["flag"]
        if data.get("rotation") in (90, 180, 270):
            photo.rotation = data["rotation"]
        crop = data.get("crop")
        if isinstance(crop, list) and len(crop) == 4:
            x0, y0, x1, y1 = crop
            if all(isinstance(v, (int, float)) for v in (x0, y0, x1, y1)):
                photo.crop = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return photo


def save_photo(photo: Photo) -> None:
    data: dict = {"flag": photo.flag, "rotation": photo.rotation}
    if photo.crop is not None:
        data["crop"] = [round(v, 6) for v in photo.crop]
    photo.sidecar.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def scan_folder(root: Path) -> list[Photo]:
    """Recursively find images, skipping hidden dirs and the trash folder."""
    photos: list[Photo] = []
    if not root.is_dir():
        return photos
    for path in sorted(root.rglob("*"), key=lambda p: str(p).lower()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        if path.name.startswith("."):
            continue  # hidden file (e.g. macOS ._ forks, editor backups)
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue  # hidden dir (e.g. .photofx_trash)
        photos.append(load_photo(path))
    return photos


def trash_target(root: Path, photo: Photo) -> Path:
    """Where this photo would be moved inside the trash folder."""
    rel = photo.path.relative_to(root)
    dest = root / TRASH_DIRNAME / rel
    return dest


def move_to_trash(root: Path, photo: Photo) -> None:
    dest = trash_target(root, photo)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stem = dest.stem
        dest = dest.with_name(f"{stem}_{photo.path.suffix}{dest.suffix}")
    shutil.move(str(photo.path), str(dest))
    if photo.sidecar.exists():
        sidecar_dest = dest.with_name(dest.name + ".json")
        if sidecar_dest.exists():
            sidecar_dest.unlink()
        shutil.move(str(photo.sidecar), str(sidecar_dest))
