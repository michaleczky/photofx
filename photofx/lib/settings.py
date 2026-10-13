"""Settings: the last photo folder, remembered between sessions.

Stored as JSON under the platform's per-user config directory
(``PHOTOFX_CONFIG_DIR`` overrides it — used by the test suite).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

APP_NAME = "photofx"


def config_dir() -> Path:
    override = os.environ.get("PHOTOFX_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def _config_file() -> Path:
    return config_dir() / "settings.json"


def saved_folder() -> Path | None:
    """The folder the user last opened, or None if unset or no longer there."""
    try:
        data = json.loads(_config_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    folder = data.get("folder")
    if isinstance(folder, str):
        path = Path(folder)
        if path.is_dir():
            return path
    return None


def pictures_folder() -> Path:
    """The user's photos directory (first-launch default)."""
    return Path.home() / "Pictures"


def default_folder() -> Path | None:
    """Last opened folder if it still exists, else the Pictures directory."""
    saved = saved_folder()
    if saved is not None:
        return saved
    pictures = pictures_folder()
    return pictures if pictures.is_dir() else None


def _read() -> dict:
    try:
        data = json.loads(_config_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_folder(folder: Path) -> None:
    """Update the last folder, keeping any other settings (e.g. exclude)."""
    try:
        data = _read()
        data["folder"] = str(folder)
        config_dir().mkdir(parents=True, exist_ok=True)
        _config_file().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass  # settings are a convenience, never fatal


def exclude_patterns() -> list[re.Pattern]:
    """User regexes of photo file names the grid app must not show.

    Read from the ``exclude`` list in settings.json, e.g.::

        {"folder": "/home/me/Pictures", "exclude": ["^screenshot", "_thumb$"]}

    Patterns match anywhere in the file name unless anchored; invalid
    patterns are skipped. Edit the file by hand — there is no UI yet.
    """
    patterns = _read().get("exclude")
    if not isinstance(patterns, list):
        return []
    out = []
    for raw in patterns:
        if isinstance(raw, str):
            try:
                out.append(re.compile(raw))
            except re.error:
                continue
    return out
