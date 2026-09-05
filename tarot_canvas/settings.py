import json
import time

from PyQt6.QtCore import QSettings

SETTINGS_ORGANIZATION = "ArcanaLand"
SETTINGS_APPLICATION = "TarotCanvas"

THEME_KEY = "appearance/theme"
THEME_DEFAULT = "System"

BACKGROUND_STYLE_KEY = "appearance/background_style"
BACKGROUND_STYLE_DEFAULT = "Gradient"

BACKGROUND_COLOR_KEY = "appearance/background_color"
BACKGROUND_COLOR_DEFAULT = "#1e1432"

ANIMATIONS_ENABLED_KEY = "appearance/enable_animations"
ANIMATIONS_ENABLED_DEFAULT = True

ANIMATION_INTENSITY_KEY = "appearance/animation_intensity"
ANIMATION_INTENSITY_DEFAULT = 50


def get_settings():
    return QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)


LIBRARY_DENSITY_KEY = "library/density"
LIBRARY_DENSITY_DEFAULT = "large"

LIBRARY_SORT_KEY = "library/sort"
LIBRARY_SORT_DEFAULT = "name"

LIBRARY_RECENT_KEY = "library/recent"
LIBRARY_RECENT_LIMIT = 50

DECK_HEADER_EXPANDED_KEY = "deck_view/header_expanded"
DECK_HEADER_EXPANDED_DEFAULT = False


def get_recent_decks():
    """Mapping of deck path -> last-opened epoch seconds."""
    raw = get_settings().value(LIBRARY_RECENT_KEY, "", type=str)
    if not raw:
        return {}
    try:
        recent = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(recent, dict):
        return {}
    return {str(path): float(when) for path, when in recent.items() if _is_number(when)}


def record_deck_opened(deck_path, when=None):
    """Remember that `deck_path` was opened, for the library's recency sort."""
    if not deck_path:
        return
    recent = get_recent_decks()
    recent[str(deck_path)] = float(when if when is not None else time.time())
    if len(recent) > LIBRARY_RECENT_LIMIT:
        keep = sorted(recent.items(), key=lambda item: item[1], reverse=True)
        recent = dict(keep[:LIBRARY_RECENT_LIMIT])
    get_settings().setValue(LIBRARY_RECENT_KEY, json.dumps(recent))


def _is_number(value):
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
