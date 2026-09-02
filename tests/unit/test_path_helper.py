"""Paths are partitioned per app ID (RFC-012).

These pin the property that made the devel-build split possible: the code reads
XDG_DATA_HOME rather than hardcoding the production app ID, so a build published
under any other ID lands in its own directory.
"""

from pathlib import Path

import pytest

from tarot_canvas.utils import path_helper


@pytest.fixture
def flatpak_env(monkeypatch, tmp_path):
    """Simulate a Flatpak sandbox with the app-ID-derived XDG_DATA_HOME it sets."""

    def _apply(app_id):
        data = tmp_path / ".var" / "app" / app_id / "data"
        monkeypatch.setattr(path_helper.os.path, "exists", lambda p: p == "/.flatpak-info")
        monkeypatch.setattr(path_helper, "xdg_data_home", lambda: data)
        return data

    return _apply


def test_data_directory_follows_the_app_id(flatpak_env):
    prod = flatpak_env("land.arcana.TarotCanvas")
    assert path_helper.get_data_directory() == prod

    devel = flatpak_env("land.arcana.TarotCanvas.Devel")
    assert path_helper.get_data_directory() == devel
    assert devel != prod


def test_devel_and_production_decks_do_not_share_a_write_path(flatpak_env):
    flatpak_env("land.arcana.TarotCanvas")
    prod_primary = path_helper.get_decks_directory()[0]

    flatpak_env("land.arcana.TarotCanvas.Devel")
    devel_primary = path_helper.get_decks_directory()[0]

    assert prod_primary != devel_primary


def test_external_deck_library_stays_shared_under_flatpak(flatpak_env):
    """The read-only escape hatch is deliberately common to every build."""
    flatpak_env("land.arcana.TarotCanvas.Devel")
    assert path_helper.get_decks_directory()[-1] == path_helper.EXTERNAL_DECKS_PATH


def test_app_specific_path_is_appended(flatpak_env):
    data = flatpak_env("land.arcana.TarotCanvas")
    assert path_helper.get_data_directory("tarot-canvas/notes") == data / "tarot-canvas/notes"


def test_outside_flatpak_there_is_no_external_path(monkeypatch, tmp_path):
    monkeypatch.setattr(path_helper.os.path, "exists", lambda p: False)
    monkeypatch.setattr(path_helper, "xdg_data_home", lambda: tmp_path)

    assert path_helper.get_data_directory() == tmp_path
    assert path_helper.get_decks_directory() == [tmp_path / "tarot/decks"]


def test_host_default_matches_the_documented_location(monkeypatch):
    """Non-Flatpak decks must stay at ~/.local/share/tarot/decks (RFC-012 §1)."""
    monkeypatch.setattr(path_helper.os.path, "exists", lambda p: False)
    monkeypatch.setattr(path_helper, "xdg_data_home", lambda: Path.home() / ".local/share")

    assert path_helper.get_decks_directory() == [Path.home() / ".local/share/tarot/decks"]
