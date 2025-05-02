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
            os.path.expanduser("~/.local/share/tarot/decks"),
        ]
        
        # Check each path for decks (directories with deck.toml)
        for base_path in deck_paths:
            if os.path.exists(base_path):
                for deck_dir in os.listdir(base_path):
                    deck_path = os.path.join(base_path, deck_dir)
                    if os.path.isdir(deck_path) and os.path.exists(os.path.join(deck_path, "deck.toml")):
                        try:
                            print(f"Loading deck from {deck_path}")
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

    def get_all_decks(self):
        """Get all available decks including the reference deck"""
        # Create a list with all decks including the reference deck
        all_decks = list(self.decks.values())
        
        # Add reference deck if it's not already in the list
        if self.reference_deck not in all_decks:
            all_decks.insert(0, self.reference_deck)  # Insert at beginning
            
        return all_decks    
# Create a global instance
deck_manager = DeckManager()