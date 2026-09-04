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
