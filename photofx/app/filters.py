"""Named photo filters for the grid application."""

from __future__ import annotations

from photofx.lib.catalog import PICK, REJECT, Photo


class PhotoFilter:
    """A named flag-based filter over the photo list.

    Immutable in spirit: picking a different name means making a new
    instance.
    """

    NAMES = ["All photos", "Picks", "Without rejects", "Rejected", "Unflagged"]

    def __init__(self, name: str = NAMES[0]):
        if name not in self.NAMES:
            raise ValueError(f"unknown filter: {name!r}")
        self.name = name

    def matches(self, photo: Photo) -> bool:
        if self.name == "Picks":
            return photo.flag == PICK
        if self.name == "Rejected":
            return photo.flag == REJECT
        if self.name == "Without rejects":
            return photo.flag != REJECT
        if self.name == "Unflagged":
            return photo.flag is None
        return True

    def apply(self, photos: list[Photo]) -> list[Photo]:
        return [p for p in photos if self.matches(p)]
