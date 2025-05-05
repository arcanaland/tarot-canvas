import sys
import os
import argparse
import urllib.parse
from PyQt6.QtWidgets import (QApplication, QProgressDialog, QMessageBox, 
                            QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon
from tarot_canvas.utils.path_helper import get_data_directory, get_decks_directory
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.models.reference_deck import ReferenceDeck
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.utils.theme_manager import ThemeManager
from tarot_canvas.utils.logger import logger
from pathlib import Path
from importlib.resources import files

class DeckDownloadThread(QThread):
    progress_update = pyqtSignal(int, str)
    download_complete = pyqtSignal(bool, str)
    
    def run(self):
        try:
            # Call the download function with our own progress callback
            ReferenceDeck.download_reference_deck(progress_callback=self.update_progress)
            self.download_complete.emit(True, "")
        except Exception as e:
            self.download_complete.emit(False, str(e))
    
    def update_progress(self, percent, message):
        self.progress_update.emit(percent, message)

class SetupDialog(QDialog):
    """Initial setup dialog that handles reference deck download"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("First-time Setup")
        self.setMinimumSize(400, 200)
        
        # Try to set the app icon
        try:
            ICON_PATH = files('tarot_canvas.resources.icons').joinpath('icon.png')
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        except Exception:
            pass
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Add welcome message
        welcome_label = QLabel("Welcome to Tarot Canvas!")
        welcome_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(welcome_label)
        
        # Add description
        desc_label = QLabel("Before we start, we need to download the Rider-Waite-Smith tarot deck.")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Add status label
        self.status_label = QLabel("Preparing to download...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Add retry button (hidden initially)
        self.retry_button = QPushButton("Retry Download")
        self.retry_button.clicked.connect(self.start_download)
        self.retry_button.hide()
        layout.addWidget(self.retry_button)
        
        # Download success flag
        self.download_success = False
        
        # Start the download automatically
        QThread.msleep(500)  # Small delay to ensure UI is shown
        self.start_download()
    
    def start_download(self):
        # Hide retry button if shown
        self.retry_button.hide()
        
        # Reset progress
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting download...")
        
        # Create and start download thread
        self.download_thread = DeckDownloadThread()
        self.download_thread.progress_update.connect(self.update_progress)
        self.download_thread.download_complete.connect(self.handle_download_completion)
        self.download_thread.start()
    
    def update_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
    
    def handle_download_completion(self, success, error):
        if success:
            self.download_success = True
            self.status_label.setText("Download complete! Starting application...")
            self.progress_bar.setValue(100)
            
            # Close the dialog after a short delay
            QThread.msleep(1000)
            self.accept()
        else:
            self.download_success = False
            self.status_label.setText(f"Download failed: {error}")
            self.retry_button.show()

def main():
    # Suppress Qt warnings about Wayland
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland=false"

    # Initialize the application
    app = QApplication(sys.argv)
    app.setApplicationName("tarot-canvas")
    app.setApplicationDisplayName("Tarot Canvas")
    app.setDesktopFileName("land.arcana.TarotCanvas")

    # Initialize and apply theme
    logger.info("Initializing theme manager")
    theme_manager = ThemeManager.get_instance()
    
    # Check if reference deck is already present
    needs_download = not ReferenceDeck.is_reference_deck_present()
    
    # If we need to download the reference deck, show setup dialog
    if needs_download:
        setup_dialog = SetupDialog()
        result = setup_dialog.exec()
        
        # If dialog was rejected or download failed, exit
        if not result or not setup_dialog.download_success:
            logger.error("Reference deck download failed or was cancelled")
            return 1
        
        # Reload deck manager after download
        try:
            # Reinitialize deck manager to load the newly downloaded deck
            deck_manager.load_reference_deck()
            if not deck_manager.get_reference_deck():
                logger.error("Failed to load reference deck after download")
                QMessageBox.critical(
                    None, 
                    "Error",
                    "Failed to load the reference deck after downloading. The application will now exit."
                )
                return 1
        except Exception as e:
            logger.error(f"Error loading reference deck: {e}")
            QMessageBox.critical(
                None, 
                "Error",
                f"Error loading reference deck: {e}\nThe application will now exit."
            )
            return 1
    
    # Now that we have the reference deck, create and show main window
    main_window = MainWindow()
    main_window.show()
    
    # Process URI argument if provided
    process_uri_argument(app.arguments(), main_window)
    
    # Run the application event loop
    return app.exec()

def process_uri_argument(args, main_window):
    """Process URI argument for opening specific cards"""
    # Create argument parser
    parser = argparse.ArgumentParser(description='Tarot Canvas')
    parser.add_argument('uri', nargs='?', help='Open a specific card by URI')
    
    # Parse just the known args, ignoring Qt's own args
    known_args, _ = parser.parse_known_args(args)
    
    if hasattr(known_args, 'uri') and known_args.uri and known_args.uri.startswith('tarot://'):
        # Parse the URI
        parsed_uri = urllib.parse.urlparse(known_args.uri)
        path = parsed_uri.netloc + parsed_uri.path
        
        # Remove any leading/trailing slashes
        card_id = path.strip('/')
        
        # Find the card
        if card_id:
            card_parts = card_id.split('.')
            
            # Get reference deck
            deck = deck_manager.get_reference_deck()
            
            # Find the card
            card = None
            if deck and len(card_parts) >= 2:
                # For minor arcana: minor_arcana.wands.queen
                if card_parts[0] == "minor_arcana" and len(card_parts) == 3:
                    card = deck.find_card_by_attributes({
                        "type": "minor_arcana",
                        "suit": card_parts[1],
                        "rank": card_parts[2]
                    })
                # For major arcana: major_arcana.0
                elif card_parts[0] == "major_arcana" and len(card_parts) == 2:
                    card = deck.find_card_by_attributes({
                        "type": "major_arcana",
                        "number": card_parts[1]
                    })
                else:
                    # Try to find by direct ID
                    card = deck.get_card(card_id)
            else:
                # Try to find by direct ID if deck exists
                if deck:
                    card = deck.get_card(card_id)
            
            # If card found, open it
            if card:
                main_window.open_card_view(card, deck)
            else:
                logger.warning(f"Card not found in the reference deck: {card_id}")

if __name__ == "__main__":
    sys.exit(main())

