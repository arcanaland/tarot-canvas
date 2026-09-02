import os
from pathlib import Path

from xdg_base_dirs import xdg_data_home

# Read-only escape hatch: a deck library shared with non-Flatpak builds and with
# other builds of this app. Granted by --filesystem in the manifest, deliberately
# common to every build so a devel build can see the real decks.
EXTERNAL_DECKS_PATH = Path(os.path.expanduser("~/.local/share/tarot/decks"))


def get_data_directory(app_specific_path=None):
    """
    Get the appropriate data directory based on environment.

    Under Flatpak, XDG_DATA_HOME is already ~/.var/app/$FLATPAK_ID/data, so the
    plain XDG lookup is correct in and out of the sandbox — and a build published
    under a different app ID lands in its own directory rather than the shipped
    app's.

    Args:
        app_specific_path (str, optional): App-specific subdirectory to append

    Returns:
        Path: The appropriate data path
    """
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

    Returns:
        list: List of Path objects to check for tarot decks
    """
    paths = [get_data_directory("tarot/decks")]

    if os.path.exists("/.flatpak-info"):
        paths.append(EXTERNAL_DECKS_PATH)

    return paths
