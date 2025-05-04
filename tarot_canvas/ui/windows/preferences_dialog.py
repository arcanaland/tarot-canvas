from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, 
                           QComboBox, QPushButton, QDialogButtonBox, QColorDialog,
                           QWidget, QCheckBox, QLabel, QSlider)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QSettings, Qt

from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450)
        
        # Create appearance settings
        self.setup_appearance_settings()
        
        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)
        
        # Main layout
        layout = QVBoxLayout()
        layout.addWidget(self.appearance_widget)
        layout.addWidget(button_box)
        self.setLayout(layout)
        
        # Load current settings
        self.load_settings()
    
    def setup_appearance_settings(self):
        # Create appearance settings widget
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
        
        # Add a helper label for the animation slider
        anim_label = QLabel("Lower values = subtle animations, higher values = more dramatic")
        anim_label.setStyleSheet("color: #777; font-size: 10px;")
        layout.addRow("", anim_label)
        
        # Enable the color picker only when "Solid Color" is selected
        self.bg_combo.currentIndexChanged.connect(self.update_color_button_state)
        
        self.appearance_widget.setLayout(layout)
    
    def update_color_button_state(self):
        # Enable color button only when "Solid Color" is selected
        self.bg_color_btn.setEnabled(self.bg_combo.currentText() == "Solid Color")
    
    def select_bg_color(self):
        color = QColorDialog.getColor(initial=getattr(self, 'bg_color', QColor(30, 20, 50)))
        if color.isValid():
            self.bg_color = color
            # Set button background to show selected color
            self.bg_color_btn.setStyleSheet(f"background-color: {color.name()}; color: {'white' if color.lightness() < 128 else 'black'};")
    
    def load_settings(self):
        # Load settings from your settings manager
        settings = QSettings("ArcanaLand", "TarotCanvas")
        
        # Appearance settings
        theme = settings.value("appearance/theme", "System")
        theme_index = self.theme_combo.findText(theme)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
            
        bg_style = settings.value("appearance/background_style", "Checkerboard")
        bg_index = self.bg_combo.findText(bg_style)
        if bg_index >= 0:
            self.bg_combo.setCurrentIndex(bg_index)
            
        bg_color = settings.value("appearance/background_color", QColor(30, 20, 50))
        if isinstance(bg_color, str):
            bg_color = QColor(bg_color)
        self.bg_color = bg_color
        self.bg_color_btn.setStyleSheet(f"background-color: {bg_color.name()}; color: {'white' if bg_color.lightness() < 128 else 'black'};")
        
        self.animation_check.setChecked(settings.value("appearance/enable_animations", True, type=bool))
        self.animation_slider.setValue(settings.value("appearance/animation_intensity", 50, type=int))
        
        # Update dependent states
        self.update_color_button_state()
    
    def apply_settings(self):
        # Save settings to your settings manager
        settings = QSettings("ArcanaLand", "TarotCanvas")
        
        # Appearance settings
        settings.setValue("appearance/theme", self.theme_combo.currentText())
        settings.setValue("appearance/background_style", self.bg_combo.currentText())
        settings.setValue("appearance/background_color", getattr(self, 'bg_color', QColor(30, 20, 50)).name())
        settings.setValue("appearance/enable_animations", self.animation_check.isChecked())
        settings.setValue("appearance/animation_intensity", self.animation_slider.value())
        
        # Apply theme immediately
        theme_type = ThemeType.SYSTEM
        if self.theme_combo.currentText() == "Light":
            theme_type = ThemeType.LIGHT
        elif self.theme_combo.currentText() == "Dark":
            theme_type = ThemeType.DARK
        
        ThemeManager.get_instance().set_theme(theme_type)
    
    def accept(self):
        self.apply_settings()
        super().accept()