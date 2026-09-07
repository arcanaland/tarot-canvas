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

# Unread as of the canvas render-correctness change: the wobble these controlled is gone
# and the preferences controls with it. Both keys are retained deliberately — stored user
# values are the migration input for the motion level that replaces them.
ANIMATIONS_ENABLED_KEY = "appearance/enable_animations"
ANIMATIONS_ENABLED_DEFAULT = True

ANIMATION_INTENSITY_KEY = "appearance/animation_intensity"
ANIMATION_INTENSITY_DEFAULT = 50

MOTION_LEVEL_KEY = "appearance/motion_level"
MOTION_LEVEL_DEFAULT = "Full"
MOTION_LEVELS = ("Off", "Reactive", "Full")


def get_motion_level(settings=None):
    """How much the canvas is allowed to move, migrating the two retired keys once.

    `Off` is no motion at all, `Reactive` keeps only the brief response to the user's own
    action, `Full` adds the ambient tier. The old enable/intensity pair maps onto the ends
    of that ladder — it could express nothing in between — and is read exactly once, after
    which the new key is authoritative.
    """
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

DECK_HEADER_EXPANDED_KEY = "deck_view/header_expanded"
DECK_HEADER_EXPANDED_DEFAULT = True


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
