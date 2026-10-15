import configparser
import sys
from enum import Enum

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory

from tarot_canvas.settings import THEME_KEY, get_settings, get_theme
from tarot_canvas.ui import colour_scheme
from tarot_canvas.utils.logger import logger

# Set by KColorSchemeManager; Breeze reads it for the menu bar's colours, and the Plasma
# platform theme for the title bar's
SCHEME_PATH_PROPERTY = "KDE_COLOR_SCHEME_PATH"


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

        # An explicit palette, as a KDE app's Window Color Scheme menu sets; the
        # platform theme ignores setColorScheme(), and the style's standardPalette()
        # is the desktop's (#34)
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

    def _apply_system_theme(self, app):
        """The style and palette the app started with, still following the desktop's"""
        app.setProperty(SCHEME_PATH_PROPERTY, None)
        app.setPalette(QPalette())
        app.styleHints().unsetColorScheme()
        self._renew_style(app)
        logger.info("Applying system theme")

    def _renew_style(self, app):
        """A fresh instance of the startup style, polishing every widget again.

        Breeze reads SCHEME_PATH_PROPERTY once per window, when it first polishes it, and
        keeps the menu bar's text colour from then on; switching Light to Dark at runtime
        left dark labels on the dark header until the style was made anew.
        """
        app.setStyle(self._startup_style or app.style().name())
