from pathlib import Path

import pytest

from tarot_canvas.utils import path_helper


@pytest.fixture
def flatpak_env(monkeypatch, tmp_path):
    """Simulate a Flatpak sandbox."""

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
    """The read-only escape hatch."""
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
    monkeypatch.setattr(path_helper.os.path, "exists", lambda p: False)
    monkeypatch.setattr(path_helper, "xdg_data_home", lambda: Path.home() / ".local/share")

    assert path_helper.get_decks_directory() == [Path.home() / ".local/share/tarot/decks"]


def test_esoterica_shares_the_shape_of_decks(flatpak_env):
    """The literal `references` segment is gone; the root is `tarot/esoterica`."""
    data = flatpak_env("land.arcana.TarotCanvas")
    assert path_helper.get_esoterica_directories() == [
        data / "tarot/esoterica",
        path_helper.EXTERNAL_ESOTERICA_PATH,
    ]


def test_devel_and_production_esoterica_do_not_share_a_write_path(flatpak_env):
    flatpak_env("land.arcana.TarotCanvas")
    prod_primary = path_helper.get_esoterica_directories()[0]

    flatpak_env("land.arcana.TarotCanvas.Devel")
    devel_primary = path_helper.get_esoterica_directories()[0]

    assert prod_primary != devel_primary


def test_outside_flatpak_esoterica_has_no_external_path(monkeypatch, tmp_path):
    monkeypatch.setattr(path_helper.os.path, "exists", lambda p: False)
    monkeypatch.setattr(path_helper, "xdg_data_home", lambda: tmp_path)

    assert path_helper.get_esoterica_directories() == [tmp_path / "tarot/esoterica"]


def test_cache_directory_honours_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    assert path_helper.get_cache_directory() == tmp_path / "cache"
    assert path_helper.get_cache_directory("tarot-canvas/catalog") == (
        tmp_path / "cache" / "tarot-canvas/catalog"
    )


def test_staging_sits_beside_the_first_root_and_is_not_one(flatpak_env):
    flatpak_env("land.arcana.TarotCanvas")
    staging = path_helper.get_staging_directory()
    roots = path_helper.get_decks_directory()

    assert staging.parent == roots[0].parent
    assert staging not in roots
