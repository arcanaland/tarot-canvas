import logging
from typing import ClassVar

from PyQt6.QtCore import QEvent, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QPalette, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from tarot_canvas.ui import typography
from tarot_canvas.utils.logger import TarotLogger


class LogViewerDialog(QDialog):
    """Dialog window to view application logs"""

    # Define colors for light theme
    LIGHT_THEME_COLORS: ClassVar[dict] = {
        logging.DEBUG: QColor(100, 100, 100),  # Gray
        logging.INFO: QColor(0, 0, 0),  # Black
        logging.WARNING: QColor(255, 165, 0),  # Orange
        logging.ERROR: QColor(255, 0, 0),  # Red
        logging.CRITICAL: QColor(128, 0, 128),  # Purple
    }

    # Define colors for dark theme
    DARK_THEME_COLORS: ClassVar[dict] = {
        logging.DEBUG: QColor(170, 170, 170),  # Light Gray
        logging.INFO: QColor(220, 220, 220),  # Off-White
        logging.WARNING: QColor(255, 190, 0),  # Gold
        logging.ERROR: QColor(255, 100, 100),  # Light Red
        logging.CRITICAL: QColor(255, 100, 255),  # Pink
    }

    LOG_LEVELS: ClassVar[dict] = {
        "Debug": logging.DEBUG,
        "Info": logging.INFO,
        "Warning": logging.WARNING,
        "Error": logging.ERROR,
        "Critical": logging.CRITICAL,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(800, 600)

        self.update_colors_for_theme()

        self.setup_ui()

        # Subscribe to log events
        TarotLogger.subscribe(self.on_log_message)

        # Show initial log content
        self.load_log_file()

    def update_colors_for_theme(self):
        """Pick the colour set by the palette's lightness, whichever theme put it there"""
        if self.palette().color(QPalette.ColorRole.Base).lightness() < 128:
            self.LOG_COLORS = self.DARK_THEME_COLORS
        else:
            self.LOG_COLORS = self.LIGHT_THEME_COLORS

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "log_display"):
            self.update_colors_for_theme()
            self.reload_with_new_colors()

    def reload_with_new_colors(self):
        """Reload the log content with the new color scheme"""
        # Save current scroll position
        scrollbar = self.log_display.verticalScrollBar()
        scroll_position = scrollbar.value()

        # Reload the log with new colors
        self.load_log_file()

        # Restore scroll position
        scrollbar.setValue(scroll_position)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Controls for filtering
        controls_layout = QHBoxLayout()

        # Log level filter
        level_label = QLabel("Minimum Level:")
        controls_layout.addWidget(level_label)

        self.level_selector = QComboBox()
        for level_name in self.LOG_LEVELS:
            self.level_selector.addItem(level_name)
        self.level_selector.setCurrentText("Info")  # Default to Info level
        self.level_selector.currentTextChanged.connect(self.filter_log)
        controls_layout.addWidget(self.level_selector)

        # Auto-scroll checkbox
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        controls_layout.addWidget(self.auto_scroll)

        controls_layout.addStretch()

        # Search box - adding a new feature
        self.search_label = QLabel("Search:")
        controls_layout.addWidget(self.search_label)

        self.search_box = QComboBox()
        self.search_box.setEditable(True)
        self.search_box.setMinimumWidth(150)
        self.search_box.editTextChanged.connect(self.filter_log)
        controls_layout.addWidget(self.search_box)

        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.setIcon(QIcon.fromTheme("view-refresh"))
        refresh_button.clicked.connect(self.load_log_file)
        controls_layout.addWidget(refresh_button)

        layout.addLayout(controls_layout)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        typography.apply(self.log_display, typography.Role.BODY, fixed=True)
        layout.addWidget(self.log_display)

    def load_log_file(self):
        """Load the current log file content"""
        self.clear_log_display()

        try:
            log_file_path = TarotLogger.get_log_file_path()
            with open(log_file_path) as f:
                for line in f:
                    self.process_log_line(line)
        except Exception as e:
            self.log_display.append(f"Error loading log file: {e}")

    def process_log_line(self, line):
        """Process a line from the log file and display it if it matches the filter"""
        try:
            # Parse log level from the line
            if " - DEBUG - " in line:
                level = logging.DEBUG
            elif " - INFO - " in line:
                level = logging.INFO
            elif " - WARNING - " in line:
                level = logging.WARNING
            elif " - ERROR - " in line:
                level = logging.ERROR
            elif " - CRITICAL - " in line:
                level = logging.CRITICAL
            else:
                level = logging.INFO  # Default if can't determine

            # Check if level meets the filter and search text matches (if any)
            search_text = self.search_box.currentText().strip().lower()
            if level >= self.get_selected_level() and (
                not search_text or search_text in line.lower()
            ):
                # Format and append
                self.append_colored_text(line.strip(), level)
        except Exception as e:
            self.log_display.append(f"Error processing log line: {e}")

    @pyqtSlot(int, str, str)
    def on_log_message(self, level, timestamp, message):
        """Handle new log messages from the logger"""
        # Check if level meets the filter and search text matches (if any)
        search_text = self.search_box.currentText().strip().lower()
        formatted_message = f"{timestamp} - {logging.getLevelName(level)} - {message}"

        if level >= self.get_selected_level() and (
            not search_text or search_text in formatted_message.lower()
        ):
            self.append_colored_text(formatted_message, level)

    def append_colored_text(self, text, level):
        """Append colored text to the log display"""
        # Save current cursor position
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Set color based on log level
        text_format = cursor.charFormat()
        text_format.setForeground(self.LOG_COLORS.get(level, QColor(0, 0, 0)))
        cursor.setCharFormat(text_format)

        # Insert text and newline
        cursor.insertText(f"{text}\n")

        # Auto-scroll if enabled
        if self.auto_scroll.isChecked():
            self.log_display.setTextCursor(cursor)
            self.log_display.ensureCursorVisible()

    def get_selected_level(self):
        """Get the selected log level as an integer"""
        level_name = self.level_selector.currentText()
        return self.LOG_LEVELS.get(level_name, logging.INFO)

    def filter_log(self):
        """Reapply filtering based on current settings"""
        self.load_log_file()

    def clear_log_display(self):
        """Clear the log display"""
        self.log_display.clear()

    def closeEvent(self, event):
        """Handle window close event"""
        # Unsubscribe from logger
        TarotLogger.unsubscribe(self.on_log_message)
        super().closeEvent(event)
