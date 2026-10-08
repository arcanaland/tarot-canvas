import os
from importlib.resources import files
from pathlib import Path

from xdg_base_dirs import xdg_cache_home, xdg_data_home

EXTERNAL_DECKS_PATH = Path(os.path.expanduser("~/.local/share/tarot/decks"))
EXTERNAL_ESOTERICA_PATH = Path(os.path.expanduser("~/.local/share/tarot/esoterica"))
BUNDLED_ESOTERICA_PATH = Path(str(files("tarot_canvas.resources").joinpath("esoterica")))


def get_data_directory(app_specific_path=None):
    base_path = xdg_data_home()

    # Append app-specific path if provided
    if app_specific_path:
        return base_path / app_specific_path

    return base_path


def get_cache_directory(app_specific_path=None):
    base_path = xdg_cache_home()

    if app_specific_path:
        return base_path / app_specific_path

    return base_path


def get_decks_directory():
    """
    Returns all valid locations for tarot decks.

    The primary location is per-build (see get_data_directory). Under Flatpak the
    shared external library is appended as a secondary, read-only location.
    """
    paths = [get_data_directory("tarot/decks")]

    if os.path.exists("/.flatpak-info"):
        paths.append(EXTERNAL_DECKS_PATH)

    return paths


def get_staging_directory():
    """Where deck containers are unpacked"""
    return get_data_directory("tarot/.staging")


def get_esoterica_directories():
    """
    Returns all valid locations for esoterica sources, most specific first.

    The first is per-build and the only one ever written. Under Flatpak the shared
    external library follows it. The last ships with the app and is read-only.
    """
    paths = [get_data_directory("tarot/esoterica")]

    if os.path.exists("/.flatpak-info"):
        paths.append(EXTERNAL_ESOTERICA_PATH)

    paths.append(BUNDLED_ESOTERICA_PATH)

    return paths
