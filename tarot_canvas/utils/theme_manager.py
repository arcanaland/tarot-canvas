from PyQt6.QtCore import QSettings, QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QStyleFactory
from enum import Enum
import os
from tarot_canvas.utils.logger import logger

class ThemeType(Enum):
    SYSTEM = "system"  # Use the system's default style
    LIGHT = "light"    # Use a light style
    DARK = "dark"      # Use a dark style

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
        self.settings = QSettings("Arcana Land", "Tarot Canvas")
        self._current_theme = ThemeType(self.settings.value("theme", ThemeType.SYSTEM.value))
        
        # Check if running in Flatpak
        self._in_flatpak = self._check_flatpak()
        if self._in_flatpak:
            logger.info("Running in Flatpak environment")
        
        # Log available styles
        self._available_styles = QStyleFactory.keys()
        logger.info(f"Available Qt styles: {', '.join(self._available_styles)}")
        
        logger.info(f"Theme manager initialized with theme: {self._current_theme.value}")
    
    def _check_flatpak(self):
        """Check if running in a Flatpak environment"""
        return os.path.exists("/.flatpak-info")
    
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
        self.settings.setValue("theme", theme_type.value)
        
        # Apply the current theme
        self._apply_theme()
        
        # Emit signal for theme change
        self.theme_changed.emit(theme_type.value)
        logger.info(f"Theme changed to: {theme_type.value}")
    
    def _apply_theme(self):
        """Apply the current theme to the application"""
        app = QApplication.instance()
        if not app:
            logger.error("Cannot apply theme: No QApplication instance")
            return
        
        theme = self._current_theme
        
        # Special handling for Flatpak
        if self._in_flatpak:
            self._apply_theme_flatpak(app, theme)
            return
        
        if theme == ThemeType.SYSTEM:
            system_theme = self._get_system_style()
            logger.info(f"Applying system theme: {system_theme}")
            app.setStyle(system_theme)
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet("")  # Clear any custom styles
            
        elif theme == ThemeType.LIGHT:
            # Use a light style
            app.setStyle(self._get_light_style())
            # Ensure a light palette (Qt's default palette is usually light already)
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet("")  # Clear any custom styles
            
        elif theme == ThemeType.DARK:
            # Use a dark style if available, otherwise use a standard style with a dark palette
            app.setStyle(self._get_dark_style())
            
            # Create a dark palette
            from PyQt6.QtGui import QPalette, QColor
            dark_palette = QPalette()
            
            # Set color scheme for dark theme
            dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            dark_palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
            dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
            dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(80, 80, 80))
            dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
            dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 128, 0))
            dark_palette.setColor(QPalette.ColorRole.Link, QColor(85, 170, 255))
            dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(65, 105, 225))
            dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
            
            # Apply the dark palette
            app.setPalette(dark_palette)
            
            # Apply minimal stylesheet for elements that don't adapt well to palette changes
            app.setStyleSheet("""
            QToolTip { 
                color: #ffffff; 
                background-color: #505050; 
                border: 1px solid #777777; 
            }
            """)
    
    def _apply_theme_flatpak(self, app, theme):
        """Apply theme specifically for Flatpak environment"""
        from PyQt6.QtGui import QPalette
        
        # Always use Breeze style if available for best integration with KDE
        if "Breeze" in self._available_styles:
            app.setStyle(QStyleFactory.create("Breeze"))
            
            # For Flatpak in KDE, we'll use environment variables to control theming
            if theme == ThemeType.LIGHT:
                # Force light Breeze
                logger.info("Applying Breeze Light theme in Flatpak")
                os.environ["QT_STYLE_OVERRIDE"] = "Breeze"
                os.environ["KDEGLOBALS"] = "/usr/share/color-schemes/BreezeLight.colors"
                app.setPalette(app.style().standardPalette())
                app.setStyleSheet("")
                
            elif theme == ThemeType.DARK:
                # Force dark Breeze
                logger.info("Applying Breeze Dark theme in Flatpak")
                os.environ["QT_STYLE_OVERRIDE"] = "Breeze"
                os.environ["KDEGLOBALS"] = "/usr/share/color-schemes/BreezeDark.colors"
                
                # Create a dark palette as fallback
                from PyQt6.QtGui import QColor
                dark_palette = QPalette()
                
                # Breeze Dark colors
                dark_palette.setColor(QPalette.ColorRole.Window, QColor(49, 54, 59))
                dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(239, 240, 241))
                dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 38, 41))
                dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(77, 77, 77))
                dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(49, 54, 59))
                dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(239, 240, 241))
                dark_palette.setColor(QPalette.ColorRole.Text, QColor(239, 240, 241))
                dark_palette.setColor(QPalette.ColorRole.Button, QColor(49, 54, 59))
                dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(239, 240, 241))
                dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
                dark_palette.setColor(QPalette.ColorRole.Link, QColor(61, 174, 230))
                dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(61, 174, 230))
                dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
                
                # Apply the dark palette
                app.setPalette(dark_palette)
                
            else:  # SYSTEM
                # Use system theme - this seems to work well in Flatpak
                logger.info("Applying system theme in Flatpak")
                os.environ.pop("QT_STYLE_OVERRIDE", None)
                os.environ.pop("KDEGLOBALS", None)
                app.setPalette(app.style().standardPalette())
                app.setStyleSheet("")
                
        else:
            # Fall back to Fusion with appropriate palettes if Breeze isn't available
            logger.warning("Breeze style not available in Flatpak, falling back to Fusion")
            app.setStyle(QStyleFactory.create("Fusion"))
            
            if theme == ThemeType.LIGHT:
                app.setPalette(app.style().standardPalette())
                app.setStyleSheet("")
            elif theme == ThemeType.DARK:
                # Use similar code as the normal dark theme
                self._apply_dark_fusion_theme(app)
            else:  # SYSTEM
                app.setPalette(app.style().standardPalette())
                app.setStyleSheet("")
    
    def _apply_dark_fusion_theme(self, app):
        """Apply a dark theme using Fusion style"""
        from PyQt6.QtGui import QPalette, QColor
        
        dark_palette = QPalette()
        
        # Set color scheme for dark theme - using Breeze Dark colors
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(49, 54, 59))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(239, 240, 241))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 38, 41))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(77, 77, 77))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(49, 54, 59))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(239, 240, 241))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(239, 240, 241))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(49, 54, 59))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(239, 240, 241))
        dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(61, 174, 230))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(61, 174, 230))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        
        # Apply the dark palette
        app.setPalette(dark_palette)
    
    def _get_system_style(self):
        """Get the appropriate style for the system theme"""
        # Try to find the most appropriate default style for the current platform
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            return QStyleFactory.create("macOS")
        elif system == "Windows":
            return QStyleFactory.create("WindowsVista")
        else:  # Linux and others
            # Try to find the most native-looking style
            for style_name in ["Breeze", "Fusion", "GTK+", "Oxygen"]:
                if style_name in self._available_styles:
                    return QStyleFactory.create(style_name)
                    
            # Fall back to Fusion if no native style is found
            return QStyleFactory.create("Fusion")
    
    def _get_light_style(self):
        """Get the appropriate style for the light theme"""
        # Try to find Breeze for best KDE integration
        if "Breeze" in self._available_styles:
            return QStyleFactory.create("Breeze")
            
        # Fusion is a good cross-platform style that works well with light theme
        if "Fusion" in self._available_styles:
            return QStyleFactory.create("Fusion")
        
        # Fall back to system style if Fusion isn't available
        return self._get_system_style()
    
    def _get_dark_style(self):
        """Get the appropriate style for the dark theme"""
        # Try to find Breeze for best KDE integration
        if "Breeze" in self._available_styles:
            return QStyleFactory.create("Breeze")
            
        # Fusion is the best style for creating a dark theme in Qt
        if "Fusion" in self._available_styles:
            return QStyleFactory.create("Fusion")
            
        # If Fusion isn't available, try other styles known to work with dark themes
        for style_name in ["Oxygen"]:
            if style_name in self._available_styles:
                return QStyleFactory.create(style_name)
                
        # Fall back to system style if no dark-friendly styles are available
        return self._get_system_style()