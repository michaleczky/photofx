"""Headless tests for the persisted settings (last photo folder)."""

from __future__ import annotations

import json

from photofx.lib import settings


def test_saved_folder_roundtrip(tmp_path):
    folder = tmp_path / "pics"
    folder.mkdir()
    settings.save_folder(folder)
    assert settings.saved_folder() == folder


def test_missing_config_returns_none(tmp_path):
    assert settings.saved_folder() is None


def test_stale_folder_is_ignored(tmp_path):
    settings.save_folder(tmp_path / "gone")  # never created
    assert settings.saved_folder() is None


def test_corrupt_config_returns_none(tmp_path):
    (settings.config_dir()).mkdir(parents=True)
    (settings.config_dir() / "settings.json").write_text("{not json", encoding="utf-8")
    assert settings.saved_folder() is None


def test_saved_folder_wins_over_pictures(tmp_path, monkeypatch):
    saved = tmp_path / "saved"
    saved.mkdir()
    settings.save_folder(saved)
    monkeypatch.setattr(settings, "pictures_folder", lambda: tmp_path / "Pictures")
    assert settings.default_folder() == saved


def test_pictures_dir_used_when_nothing_saved(tmp_path, monkeypatch):
    pictures = tmp_path / "Pictures"
    pictures.mkdir()
    monkeypatch.setattr(settings, "pictures_folder", lambda: pictures)
    assert settings.default_folder() == pictures
    assert settings.saved_folder() is None  # fallback was not persisted


def test_default_folder_none_without_pictures(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pictures_folder", lambda: tmp_path / "missing")
    assert settings.default_folder() is None


def test_config_goes_to_override_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTOFX_CONFIG_DIR", str(tmp_path))
    folder = tmp_path / "photos"
    folder.mkdir()
    settings.save_folder(folder)
    f = tmp_path / "settings.json"
    assert json.loads(f.read_text(encoding="utf-8")) == {"folder": str(folder)}
    assert settings.saved_folder() == folder


def _write_settings(data):
    settings.config_dir().mkdir(parents=True, exist_ok=True)
    (settings.config_dir() / "settings.json").write_text(
        json.dumps(data), encoding="utf-8")


def test_exclude_patterns_empty_by_default():
    assert settings.exclude_patterns() == []


def test_exclude_patterns_are_compiled():
    _write_settings({"exclude": ["^screenshot", "_thumb$"]})
    patterns = settings.exclude_patterns()
    assert [p.pattern for p in patterns] == ["^screenshot", "_thumb$"]
    assert patterns[0].search("screenshot_01.jpg")
    assert not patterns[0].search("IMG_01.jpg")


def test_exclude_patterns_skip_invalid_and_non_strings():
    _write_settings({"exclude": ["[unclosed", 42, None, "^ok$"]})
    assert [p.pattern for p in settings.exclude_patterns()] == ["^ok$"]


def test_exclude_patterns_ignored_when_not_a_list():
    _write_settings({"exclude": "^screenshot"})
    assert settings.exclude_patterns() == []


def test_saving_folder_keeps_exclude_list(tmp_path):
    _write_settings({"exclude": ["^screenshot"]})
    folder = tmp_path / "photos"
    folder.mkdir()
    settings.save_folder(folder)
    assert [p.pattern for p in settings.exclude_patterns()] == ["^screenshot"]
    assert settings.saved_folder() == folder
