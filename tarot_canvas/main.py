import sys
import os
import argparse
import urllib.parse
from PyQt6.QtWidgets import QApplication
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.models.reference_deck import ReferenceDeck
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.utils.theme_manager import ThemeManager
from tarot_canvas.utils.logger import logger

def initialize_reference_deck():
    if not ReferenceDeck.is_reference_deck_present():
        print("Reference deck not found. Setting up...")
        try:
            ReferenceDeck.download_reference_deck()
        except Exception as e:
            print(f"Error setting up the reference deck: {e}")
            sys.exit(1)

def main():
    initialize_reference_deck()

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
    
    # Create and show the main window
    main_window = MainWindow()
    
    # If a URI is provided, parse and open the card
    parser = argparse.ArgumentParser(description='Tarot Canvas')
    parser.add_argument('uri', nargs='?', help='Open a specific card by URI')
    args = parser.parse_args()
    
    if args.uri and args.uri.startswith('tarot://'):
        # Parse the URI
        parsed_uri = urllib.parse.urlparse(args.uri)
        path = parsed_uri.netloc + parsed_uri.path
        
        # Remove any leading/trailing slashes
        card_id = path.strip('/')
        
        # Find the card
        if card_id:
            card_parts = card_id.split('.')
            
            # Get reference deck
            deck = deck_manager.get_reference_deck()
            
            # Find the card
            if len(card_parts) >= 2:
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
                # Try to find by direct ID
                card = deck.get_card(card_id)
            
            # If card found, open it
            if card:
                main_window.open_card_view(card, deck)
            else:
                print("Card not found in the reference deck.")
    
    main_window.show()
    
    # Run the application event loop
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())

