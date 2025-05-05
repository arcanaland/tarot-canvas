import os
from pathlib import Path
import glob
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.reference_deck import ReferenceDeck
from tarot_canvas.utils.logger import logger

class DeckManager:
    def __init__(self):
        self.decks = {}
        self.reference_deck = None
        
        # Try to load reference deck but don't fail if it doesn't exist
        self.load_reference_deck()
        
        # Load other decks
        self.load_decks()

    def load_decks(self):
        """Load all available decks from standard locations"""
        deck_paths = [
            os.path.expanduser("~/.local/share/tarot/decks"),
        ]
        
        # Check each path for decks (directories with deck.toml)
        for base_path in deck_paths:
            if os.path.exists(base_path):
                for deck_dir in os.listdir(base_path):
                    deck_path = os.path.join(base_path, deck_dir)
                    if os.path.isdir(deck_path) and os.path.exists(os.path.join(deck_path, "deck.toml")):
                        try:
                            logger.debug(f"Loading deck from {deck_path}")
                            deck = TarotDeck(deck_path)
                            self.decks[deck.get_name()] = deck
                            logger.info(f"Loaded deck '{deck.get_name()}' from {deck_path}")

                        except Exception as e:
                            logger.error(f"Error loading deck {deck_path}: {e}")
    
    def get_deck_names(self):
        """Get a list of available deck names"""
        return list(self.decks.keys())
        
    def get_deck(self, name):
        """Get a deck by name"""
        return self.decks.get(name)
        
    def get_reference_deck(self):
        """Get the reference deck (may be None if not downloaded yet)"""
        return self.reference_deck

    def load_reference_deck(self):
        """Load or reload the reference deck"""
        if ReferenceDeck.is_reference_deck_present():
            try:
                self.reference_deck = TarotDeck(ReferenceDeck.get_reference_deck_path())
                logger.info("Reference deck loaded successfully")
                return True
            except Exception as e:
                logger.error(f"Error loading reference deck: {e}")
                self.reference_deck = None
                return False
        else:
            logger.warning("Reference deck not found")
            self.reference_deck = None
            return False

    def get_all_decks(self):
        """Get all available decks including the reference deck"""
        # Create a list with all decks
        all_decks = list(self.decks.values())
        
        # Add reference deck if it exists and isn't already in the list
        if self.reference_deck is not None and self.reference_deck not in all_decks:
            all_decks.insert(0, self.reference_deck)  # Insert at beginning
            
        return all_decks

# Create a global instance
deck_manager = DeckManager()