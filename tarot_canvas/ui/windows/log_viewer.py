from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QPushButton, 
                            QHBoxLayout, QComboBox, QLabel, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QTextCursor, QFont
import logging
from tarot_canvas.utils.logger import TarotLogger

class LogViewerDialog(QDialog):
    """Dialog window to view application logs"""
    
    LOG_COLORS = {
        logging.DEBUG: QColor(100, 100, 100),     # Gray
        logging.INFO: QColor(0, 0, 0),            # Black
        logging.WARNING: QColor(255, 165, 0),     # Orange
        logging.ERROR: QColor(255, 0, 0),         # Red
        logging.CRITICAL: QColor(128, 0, 128)     # Purple
    }
    
    LOG_LEVELS = {
        "Debug": logging.DEBUG,
        "Info": logging.INFO,
        "Warning": logging.WARNING,
        "Error": logging.ERROR,
        "Critical": logging.CRITICAL
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(800, 600)
        self.setup_ui()
        
        # Subscribe to log events
        TarotLogger.subscribe(self.on_log_message)
        
        # Show initial log content
        self.load_log_file()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Controls for filtering
        controls_layout = QHBoxLayout()
        
        # Log level filter
        level_label = QLabel("Minimum Level:")
        controls_layout.addWidget(level_label)
        
        self.level_selector = QComboBox()
        for level_name in self.LOG_LEVELS.keys():
            self.level_selector.addItem(level_name)
        self.level_selector.setCurrentText("Info")  # Default to Info level
        self.level_selector.currentTextChanged.connect(self.filter_log)
        controls_layout.addWidget(self.level_selector)
        
        # Auto-scroll checkbox
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        controls_layout.addWidget(self.auto_scroll)
        
        controls_layout.addStretch()
        
        
        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.load_log_file)
        controls_layout.addWidget(refresh_button)
        
        layout.addLayout(controls_layout)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Monospace", 9))
        layout.addWidget(self.log_display)
        
    
    def load_log_file(self):
        """Load the current log file content"""
        self.clear_log_display()
        
        try:
            log_file_path = TarotLogger.get_log_file_path()
            with open(log_file_path, "r") as f:
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
            
            # Check if level meets the filter
            if level >= self.get_selected_level():
                # Format and append
                self.append_colored_text(line.strip(), level)
        except Exception as e:
            self.log_display.append(f"Error processing log line: {e}")
    
    @pyqtSlot(int, str, str)
    def on_log_message(self, level, timestamp, message):
        """Handle new log messages from the logger"""
        if level >= self.get_selected_level():
            formatted_message = f"{timestamp} - {logging.getLevelName(level)} - {message}"
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