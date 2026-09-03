import os
from pathlib import Path

from xdg_base_dirs import xdg_data_home

EXTERNAL_DECKS_PATH = Path(os.path.expanduser("~/.local/share/tarot/decks"))


def get_data_directory(app_specific_path=None):
    base_path = xdg_data_home()

    # Append app-specific path if provided
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
