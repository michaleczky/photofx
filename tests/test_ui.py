"""GUI tests for the shared dark theme, tool buttons and tooltips."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from tests.conftest import DISPLAY_OK

pytest.importorskip("PIL")

from photofx.lib import ui  # noqa: E402

requires_display = pytest.mark.skipif(not DISPLAY_OK, reason="no X display available")


@pytest.fixture
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


@requires_display
class TestDarkStyle:
    def test_theme_is_clam_dark(self, root):
        style = ui.dark_style(root)
        assert style.theme_use() == "clam"
        assert style.lookup("TFrame", "background") == ui.PANEL
        assert style.lookup("TButton", "background") == ui.BUTTON

    def test_button_has_hover_state(self, root):
        style = ui.dark_style(root)
        hover = style.map("TButton", "background")
        assert ("active", ui.BUTTON_HOVER) in hover

    def test_style_is_idempotent(self, root):
        ui.dark_style(root)
        style = ui.dark_style(root)
        assert style.lookup("TFrame", "background") == ui.PANEL


@requires_display
class TestToolButton:
    def test_icon_button_is_icon_only_with_tooltip(self, root):
        bar = ttk.Frame(root)
        button = ui.tool_button(bar, "Pick", lambda: None, icon="star", hint="Pick  P")
        assert button.cget("text") == ""
        assert button.cget("image")
        enter_bound = button.bind("<Enter>")
        assert enter_bound, "icon-only button must have a tooltip binding"

    def test_missing_icon_falls_back_to_text(self, root):
        bar = ttk.Frame(root)
        button = ui.tool_button(bar, "Pick", lambda: None, icon="does-not-exist")
        assert button.cget("text") == "Pick"
        assert not button.bind("<Enter>"), "text button needs no tooltip"

    def test_plain_text_button(self, root):
        bar = ttk.Frame(root)
        button = ui.tool_button(bar, "Add tag", lambda: None)
        assert button.cget("text") == "Add tag"


@requires_display
class TestSetToggled:
    def test_swaps_style(self, root):
        bar = ttk.Frame(root)
        button = ui.tool_button(bar, "Pick", lambda: None, icon="star")
        assert button.cget("style") in ("", "TButton")
        ui.set_toggled(button, True)
        assert button.cget("style") == "Accent.TButton"
        ui.set_toggled(button, False)
        assert button.cget("style") == "TButton"


@requires_display
class TestTooltip:
    def test_show_and_cancel(self, root):
        bar = ttk.Frame(root)
        root.update_idletasks()
        button = ttk.Button(bar, text="x")
        button.pack()
        root.update()
        tip = ui.Tooltip(button, "Pick  P")
        tip._show()
        assert tip._tip is not None and tip._tip.winfo_exists()
        label = tip._tip.children
        (child,) = [w for w in label.values() if isinstance(w, tk.Label)]
        assert child.cget("text") == "Pick  P"
        tip._cancel()
        assert tip._tip is None

    def test_hover_schedules_one_show(self, root):
        bar = ttk.Frame(root)
        button = ttk.Button(bar, text="x")
        button.pack()
        root.update()
        tip = ui.Tooltip(button, "hint")
        tip._schedule()
        first = tip._job
        tip._schedule()  # re-entering must cancel the pending show, not stack
        assert tip._job is not None and tip._job != first
        tip._cancel()
        root.update()
        assert tip._tip is None
