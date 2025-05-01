import os
from pathlib import Path
import glob
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.reference_deck import ReferenceDeck

class DeckManager:
    def __init__(self):
        self.decks = {}
        self.reference_deck = TarotDeck(ReferenceDeck.get_reference_deck_path())
        self.load_decks()

    def load_decks(self):
        """Load all available decks from standard locations"""
        deck_paths = [
            os.path.expanduser("~/.local/share/tarot-canvas/decks"),
        ]
        
        # Check each path for decks (directories with deck.toml)
        for base_path in deck_paths:
            if os.path.exists(base_path):
                for deck_dir in os.listdir(base_path):
                    deck_path = os.path.join(base_path, deck_dir)
                    if os.path.isdir(deck_path) and os.path.exists(os.path.join(deck_path, "deck.toml")):
                        try:
                            deck = TarotDeck(deck_path)
                            self.decks[deck.get_name()] = deck
                        except Exception as e:
                            print(f"Error loading deck {deck_path}: {e}")
    

    def get_deck_names(self):
        """Get a list of available deck names"""
        return list(self.decks.keys())
        
    def get_deck(self, name):
        """Get a deck by name"""
        return self.decks.get(name)
        
    def get_reference_deck(self):
        """Get the reference deck"""
        return self.reference_deck
        
# Create a global instance
deck_manager = DeckManager()