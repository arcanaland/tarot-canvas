import os
from pathlib import Path

from xdg_base_dirs import xdg_cache_home, xdg_data_home

EXTERNAL_DECKS_PATH = Path(os.path.expanduser("~/.local/share/tarot/decks"))
EXTERNAL_ESOTERICA_PATH = Path(os.path.expanduser("~/.local/share/tarot/esoterica"))


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
    """Where deck containers unpack before they are renamed into a library root.

    A sibling of the first root, so on its filesystem, but not a root itself:
    the scanner would list a half-unpacked deck here, dot-directory or not.
    """
    return get_data_directory("tarot/.staging")


def get_esoterica_directories():
    """
    Returns all valid locations for esoterica sources, most specific first.
    """
    paths = [get_data_directory("tarot/esoterica")]

    if os.path.exists("/.flatpak-info"):
        paths.append(EXTERNAL_ESOTERICA_PATH)

    return paths
