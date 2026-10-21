import configparser
import sys
from enum import Enum
from importlib.resources import files

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory

from tarot_canvas.settings import THEME_KEY, get_settings, get_theme
from tarot_canvas.ui import colour_scheme
from tarot_canvas.utils.logger import logger

SCHEME_PATH_PROPERTY = "KDE_COLOR_SCHEME_PATH"

# Light and dark subsets of Breeze, for the Mac, which has no icon theme;
# scripts/bundle_breeze_icons.py writes them
ICON_THEMES = str(files("tarot_canvas.resources").joinpath("icons"))


class ThemeType(Enum):
    SYSTEM = "system"  # Use the system's default style
    LIGHT = "light"  # Use a light style
    DARK = "dark"  # Use a dark style


class ThemeManager(QObject):
    """Manages application theming using Qt's built-in styles"""

    # Signal emitted when theme changes
    theme_changed = pyqtSignal(str)

    _instance = None

    @classmethod
    def get_instance(cls):
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        try:
            self._current_theme = ThemeType(get_theme(self.settings))
        except ValueError:
            self._current_theme = ThemeType.SYSTEM
        self._following_colour_scheme = False

        # The style the app started with, which System puts back; set by apply_at_startup
        self._startup_style = None

        logger.info(f"Available Qt styles: {', '.join(QStyleFactory.keys())}")
        logger.info(f"Theme manager initialized with theme: {self._current_theme.value}")

    def apply_at_startup(self):
        """Note the startup style, then apply the stored theme; once, before any window exists"""
        app = QApplication.instance()
        self._startup_style = app.style().name()
        self._apply_theme()

    def get_current_theme(self):
        """Get the current theme"""
        return self._current_theme

    def set_theme(self, theme_type):
        """
        Set the application theme

        Args:
            theme_type (ThemeType): The theme to set
        """
        if not isinstance(theme_type, ThemeType):
            try:
                theme_type = ThemeType(theme_type)
            except ValueError:
                logger.error(f"Invalid theme type: {theme_type}")
                return

        if theme_type == self._current_theme:
            return

        self._current_theme = theme_type
        self.settings.setValue(THEME_KEY, theme_type.value)

        # Apply the current theme
        self._apply_theme()

        # Emit signal for theme change
        self.theme_changed.emit(theme_type.value)
        logger.info(f"Theme changed to: {theme_type.value}")

    def _apply_theme(self, platform=sys.platform):
        """Apply the current theme to the application"""
        app = QApplication.instance()
        if not app:
            logger.error("Cannot apply theme: No QApplication instance")
            return

        theme = self._current_theme

        if platform == "darwin":
            self._apply_theme_macos(app, theme)
            return

        if theme == ThemeType.SYSTEM:
            self._apply_system_theme(app)
            return

        name = colour_scheme.LIGHT_SCHEME if theme == ThemeType.LIGHT else colour_scheme.DARK_SCHEME
        path = colour_scheme.SCHEME_DIR / name
        try:
            palette = colour_scheme.palette_from_scheme(path)
        except (OSError, KeyError, ValueError, configparser.Error) as e:
            logger.warning(f"Cannot read colour scheme {path} ({e}); following the system")
            self._apply_system_theme(app)
            return
        logger.info(f"Applying {theme.value} theme from {path}")
        app.setProperty(SCHEME_PATH_PROPERTY, str(path))
        app.setPalette(palette)
        self._renew_style(app)

    def _apply_theme_macos(self, app, theme):
        app.setStyle(QStyleFactory.create("macOS"))
        app.setStyleSheet("")

        hints = app.styleHints()
        if theme == ThemeType.LIGHT:
            hints.setColorScheme(Qt.ColorScheme.Light)
        elif theme == ThemeType.DARK:
            hints.setColorScheme(Qt.ColorScheme.Dark)
        else:  # SYSTEM
            hints.unsetColorScheme()
        logger.info(f"Applying {theme.value} theme with the macOS style")

        self._use_bundled_icons(hints)

    def _use_bundled_icons(self, hints):
        """Draw icons from bundled Breeze, light or dark with the colour scheme.

        Qt's own table on the Mac maps only some names, to SF Symbols, and
        leaves the rest blank. A theme it is told to use wins over that table,
        which still answers any name the bundle lacks.
        """
        paths = QIcon.themeSearchPaths()
        if ICON_THEMES not in paths:
            QIcon.setThemeSearchPaths([ICON_THEMES, *paths])
        if not self._following_colour_scheme:
            # System follows the OS live; a scheme the app set fires this too
            hints.colorSchemeChanged.connect(self._follow_colour_scheme)
            self._following_colour_scheme = True
        self._follow_colour_scheme(hints.colorScheme())

    def _follow_colour_scheme(self, scheme):
        if self._current_theme == ThemeType.LIGHT:
            scheme = Qt.ColorScheme.Light
        elif self._current_theme == ThemeType.DARK:
            scheme = Qt.ColorScheme.Dark
        QIcon.setThemeName("breeze-dark" if scheme == Qt.ColorScheme.Dark else "breeze")

    def _apply_system_theme(self, app):
        """The style and palette the app started with"""
        app.setProperty(SCHEME_PATH_PROPERTY, None)
        app.setPalette(QPalette())
        app.styleHints().unsetColorScheme()
        self._renew_style(app)
        logger.info("Applying system theme")

    def _renew_style(self, app):
        app.setStyle(self._startup_style or app.style().name())
