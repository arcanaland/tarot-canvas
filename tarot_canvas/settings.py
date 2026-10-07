import json
import time

from PyQt6.QtCore import QSettings

from tarot_canvas.models.esoterica_events import esoterica_events

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

LIBRARY_DETAILS_PANE_KEY = "library/details_pane"
LIBRARY_DETAILS_PANE_DEFAULT = True

LIBRARY_VIEW_KEY = "library/view"
LIBRARY_VIEW_DECKS = "decks"
LIBRARY_VIEW_NOTES = "notes"
LIBRARY_VIEWS = (LIBRARY_VIEW_DECKS, LIBRARY_VIEW_NOTES)
LIBRARY_VIEW_DEFAULT = LIBRARY_VIEW_DECKS

# Lists of family ids; an id this version doesn't know matches nothing and is kept
ESOTERICA_EXPANDED_KEY = "esoterica/expanded"
ESOTERICA_HIDDEN_KEY = "esoterica/hidden"
ESOTERICA_DISABLED_KEY = "esoterica/disabled"

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


def _string_list(key):
    """A stored list, which QSettings may hand back as None, one bare str, or a list"""
    stored = get_settings().value(key)
    if stored is None:
        return []
    if isinstance(stored, str):
        return [stored] if stored else []
    return [str(item) for item in stored]


def get_esoterica_expanded():
    """The esoterica folds that are open, on every card"""
    return _string_list(ESOTERICA_EXPANDED_KEY)


def get_esoterica_hidden():
    """The esoterica families the show menu has unchecked"""
    return _string_list(ESOTERICA_HIDDEN_KEY)


def _set_esoterica_list(key, ids):
    get_settings().setValue(key, list(ids))
    esoterica_events().display_changed.emit()


def set_esoterica_expanded(ids):
    _set_esoterica_list(ESOTERICA_EXPANDED_KEY, ids)


def set_esoterica_hidden(ids):
    _set_esoterica_list(ESOTERICA_HIDDEN_KEY, ids)


def get_esoterica_disabled():
    """The identifiers of the esoterica sources that are turned off"""
    return _string_list(ESOTERICA_DISABLED_KEY)


def set_esoterica_disabled(ids):
    get_settings().setValue(ESOTERICA_DISABLED_KEY, list(ids))
    esoterica_events().sources_changed.emit()


def _is_number(value):
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
