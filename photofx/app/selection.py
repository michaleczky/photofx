"""Grid selection state: which photos are selected, in what click order.

:class:`Selection` is pure state — the set of selected paths, the order
they were clicked in, and the anchor index for range clicks. The grid
mutates it through these methods and redraws itself afterwards.
"""

from __future__ import annotations

CTRL = 0x0004
SHIFT = 0x0001


class Selection:
    """Selected photo paths, their click order, and the range anchor."""

    def __init__(self):
        self.paths: set[str] = set()
        self.order: list[str] = []       # paths in click order (pruned lazily)
        self.anchor: int | None = None  # filtered index of the last click

    # ---------------------------------------------------------------- clicks
    def click(self, idx: int, path: str, visible: list[str], state: int = 0):
        """Click on the cell at ``idx``: plain, ctrl-toggle or shift-range."""
        if state & SHIFT:
            self._click_range(idx, visible)
        elif state & CTRL:
            self.toggle(path)
        else:
            self.paths = {path}
            self.order = [path]
        self.anchor = idx

    def drag_to(self, idx: int, visible: list[str]):
        """Shift-drag over cells: extend the anchored range to ``idx``."""
        if self.anchor is not None:
            self.paths, self.order = self._range(self.anchor, idx, visible)

    def toggle(self, path: str):
        """Ctrl-click semantics: add to the selection, or remove it."""
        if path in self.paths:
            self.paths.discard(path)
        else:
            self.paths.add(path)
            if path not in self.order:
                self.order.append(path)

    def _click_range(self, idx: int, visible: list[str]):
        if self.anchor is not None:
            self.paths, self.order = self._range(self.anchor, idx, visible)
        else:
            self.paths = {visible[idx]} if visible else set()
            self.order = list(self.paths)

    @staticmethod
    def _range(a: int, b: int, visible: list[str]) -> tuple[set[str], list[str]]:
        lo, hi = sorted((a, b))
        paths = list(visible[lo:hi + 1])
        return set(paths), paths

    # --------------------------------------------------------------- movement
    def move(self, delta: int, visible: list[str]) -> int | None:
        """Move the anchor by ``delta`` cells (clamped) and select only it.

        Returns the new anchor index, or None when there is nothing to
        select.
        """
        if not visible:
            return None
        cur = self.anchor if self.anchor is not None else -1
        idx = max(0, min(len(visible) - 1, cur + delta))
        self.paths = {visible[idx]}
        self.order = [visible[idx]]
        self.anchor = idx
        return idx

    # ------------------------------------------------------------ bookkeeping
    def select_all(self, visible: list[str]):
        self.paths = set(visible)
        self.order = list(visible)

    def clear(self):
        self.paths.clear()
        self.order.clear()
        self.anchor = None

    def retain(self, visible: set[str]):
        """Keep only paths that are still shown."""
        self.paths &= visible

    def remove(self, gone: set[str]):
        self.paths -= gone

    def ranks(self, visible: list[str]) -> dict[str, int]:
        """1-based click order per selected path, in the order they were
        picked; paths never clicked get their display order."""
        ordered = [s for s in self.order if s in self.paths]
        known = set(ordered)
        ordered += [p for p in visible if p in self.paths and p not in known]
        self.order = ordered
        return {s: i + 1 for i, s in enumerate(ordered)}
