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

MOTION_LEVEL_KEY = "appearance/motion_level"
MOTION_LEVEL_DEFAULT = "Full"
MOTION_LEVELS = ("Off", "Reactive", "Full")


def get_motion_level(settings=None):
    """How much the canvas is allowed to move"""
    settings = settings or get_settings()
    stored = settings.value(MOTION_LEVEL_KEY)
    if stored in MOTION_LEVELS:
        return stored

    level = MOTION_LEVEL_DEFAULT
    if settings.contains(ANIMATIONS_ENABLED_KEY) or settings.contains(ANIMATION_INTENSITY_KEY):
        enabled = settings.value(ANIMATIONS_ENABLED_KEY, ANIMATIONS_ENABLED_DEFAULT, type=bool)
        intensity = settings.value(ANIMATION_INTENSITY_KEY, ANIMATION_INTENSITY_DEFAULT, type=int)
        level = MOTION_LEVEL_DEFAULT if enabled and intensity > 0 else "Off"
    settings.setValue(MOTION_LEVEL_KEY, level)
    return level


def get_settings():
    return QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)


LIBRARY_DENSITY_KEY = "library/density"
LIBRARY_DENSITY_DEFAULT = "large"

LIBRARY_SORT_KEY = "library/sort"
LIBRARY_SORT_DEFAULT = "name"

LIBRARY_RECENT_KEY = "library/recent"
LIBRARY_RECENT_LIMIT = 50

SHOW_AVAILABLE_DECKS_KEY = "library/show_available_decks"
SHOW_AVAILABLE_DECKS_DEFAULT = True

# False once the user closes the library's details pane: selection then no longer opens it
LIBRARY_DETAILS_PANE_KEY = "library/details_pane"
LIBRARY_DETAILS_PANE_DEFAULT = True

DECK_HEADER_EXPANDED_KEY = "deck_view/header_expanded"
DECK_HEADER_EXPANDED_DEFAULT = True

EXPLORER_VISIBLE_KEY = "main_window/explorer_visible"
EXPLORER_VISIBLE_DEFAULT = True


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
