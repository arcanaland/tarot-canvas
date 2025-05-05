import os
from pathlib import Path
from xdg_base_dirs import xdg_data_home

def get_data_directory(app_specific_path=None):
    """
    Get the appropriate data directory based on environment.
    
    Args:
        app_specific_path (str, optional): App-specific subdirectory to append
        
    Returns:
        Path: The appropriate data path based on whether running in Flatpak
    """
    # Check if running in Flatpak
    if os.path.exists("/.flatpak-info"):
        # Use Flatpak-specific data directory
        base_path = Path(os.path.expanduser("~/.var/app/land.arcana.TarotCanvas/data"))
    else:
        # Use normal XDG path for non-Flatpak environments
        base_path = xdg_data_home()
    
    # Append app-specific path if provided
    if app_specific_path:
        return base_path / app_specific_path
    
    return base_path

def get_decks_directory():
    """
    Returns all valid locations for tarot decks.
    
    In a normal environment, returns only the standard location.
    In a Flatpak environment, returns both the Flatpak location and the external location 
    that has been granted read access.

    Returns:
        list: List of Path objects to check for tarot decks
    """
    paths = []
    
    # In Flatpak environment
    if os.path.exists("/.flatpak-info"):
        # Primary location is inside the Flatpak sandbox
        flatpak_path = Path(os.path.expanduser("~/.var/app/land.arcana.TarotCanvas/data/tarot/decks"))
        paths.append(flatpak_path)
        
        # The secondary location is the external path we have read permission for
        external_path = Path(os.path.expanduser("~/.local/share/tarot/decks"))
        paths.append(external_path)
    else:
        # In non-Flatpak environment, just use the standard location
        standard_path = Path(os.path.expanduser("~/.local/share/tarot/decks"))
        paths.append(standard_path)
    
    return paths