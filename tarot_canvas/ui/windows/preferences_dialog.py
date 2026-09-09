from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.settings import (
    ANIMATION_INTENSITY_DEFAULT,
    ANIMATION_INTENSITY_KEY,
    ANIMATIONS_ENABLED_DEFAULT,
    ANIMATIONS_ENABLED_KEY,
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    THEME_DEFAULT,
    THEME_KEY,
    get_settings,
)
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType


class PreferencesDialog(QDialog):
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450)

        self.setup_appearance_settings()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        # Button box
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply_settings
        )

        # Main layout
        layout = QVBoxLayout()
        layout.addWidget(self.appearance_widget)
        layout.addWidget(button_box)
        self.setLayout(layout)

        self.load_settings()

    def setup_appearance_settings(self):
        self.appearance_widget = QWidget()
        layout = QFormLayout()

        # Theme selection
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        layout.addRow("Theme:", self.theme_combo)

        # Canvas background
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(["Checkerboard", "Gradient", "Solid Color"])
        layout.addRow("Canvas Background:", self.bg_combo)

        # Background color button (enabled only for solid color)
        self.bg_color_btn = QPushButton("Select Color")
        self.bg_color_btn.clicked.connect(self.select_bg_color)
        layout.addRow("Background Color:", self.bg_color_btn)

        # Card animation options
        self.animation_check = QCheckBox("Enable card animations")
        layout.addRow("", self.animation_check)

        # Animation intensity
        self.animation_slider = QSlider(Qt.Orientation.Horizontal)
        self.animation_slider.setMinimum(0)
        self.animation_slider.setMaximum(100)
        self.animation_slider.setTickInterval(10)
        self.animation_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        layout.addRow("Animation Intensity:", self.animation_slider)

        # Enable the color picker only when "Solid Color" is selected
        self.bg_combo.currentIndexChanged.connect(self.update_color_button_state)

        self.appearance_widget.setLayout(layout)

    def update_color_button_state(self):
        # Enable color button only when "Solid Color" is selected
        self.bg_color_btn.setEnabled(self.bg_combo.currentText() == "Solid Color")

    def select_bg_color(self):
        color = QColorDialog.getColor(
            initial=getattr(self, "bg_color", QColor(BACKGROUND_COLOR_DEFAULT))
        )

        if color.isValid():
            self.bg_color = color
            # Set button background to show selected color
            self.bg_color_btn.setStyleSheet(
                f"background-color: {color.name()}; color: {'white' if color.lightness() < 128 else 'black'};"
            )

    def load_settings(self):
        settings = get_settings()

        # Appearance settings
        theme = settings.value(THEME_KEY, THEME_DEFAULT)
        theme_index = self.theme_combo.findText(theme)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)

        bg_style = settings.value(BACKGROUND_STYLE_KEY, BACKGROUND_STYLE_DEFAULT)
        bg_index = self.bg_combo.findText(bg_style)
        if bg_index >= 0:
            self.bg_combo.setCurrentIndex(bg_index)

        bg_color = QColor(settings.value(BACKGROUND_COLOR_KEY, BACKGROUND_COLOR_DEFAULT))
        self.bg_color = bg_color
        self.bg_color_btn.setStyleSheet(
            f"background-color: {bg_color.name()}; color: {'white' if bg_color.lightness() < 128 else 'black'};"
        )

        self.animation_check.setChecked(
            settings.value(ANIMATIONS_ENABLED_KEY, ANIMATIONS_ENABLED_DEFAULT, type=bool)
        )
        self.animation_slider.setValue(
            settings.value(ANIMATION_INTENSITY_KEY, ANIMATION_INTENSITY_DEFAULT, type=int)
        )

        # Update dependent states
        self.update_color_button_state()

    def apply_settings(self):
        settings = get_settings()

        # Appearance settings
        settings.setValue(THEME_KEY, self.theme_combo.currentText())
        settings.setValue(BACKGROUND_STYLE_KEY, self.bg_combo.currentText())
        settings.setValue(
            BACKGROUND_COLOR_KEY,
            getattr(self, "bg_color", QColor(BACKGROUND_COLOR_DEFAULT)).name(),
        )

        settings.setValue(ANIMATIONS_ENABLED_KEY, self.animation_check.isChecked())
        settings.setValue(ANIMATION_INTENSITY_KEY, self.animation_slider.value())

        theme_type = ThemeType.SYSTEM
        if self.theme_combo.currentText() == "Light":
            theme_type = ThemeType.LIGHT
        elif self.theme_combo.currentText() == "Dark":
            theme_type = ThemeType.DARK

        ThemeManager.get_instance().set_theme(theme_type)

        self.settings_changed.emit()

    def accept(self):
        self.apply_settings()
        super().accept()
