import toml
import os
import random
from pathlib import Path
import glob

class TarotDeck:
    def __init__(self, deck_path):
        self.deck_path = deck_path
        self.metadata = self.load_metadata()
        self.cards = self.load_cards()

    def load_metadata(self):
        deck_file = os.path.join(self.deck_path, "deck.toml")
        if not os.path.exists(deck_file):
            raise FileNotFoundError(f"deck.toml not found in {self.deck_path}")

        with open(deck_file, "r") as f:
            return toml.load(f)

    def load_cards(self):
        """Load all cards from the deck"""
        cards = []
        
        # Get major arcana cards
        cards.extend(self.get_major_arcana_cards())
        
        # Get minor arcana cards
        for suit in ["wands", "cups", "swords", "pentacles"]:
            cards.extend(self.get_minor_arcana_cards(suit))
            
        # Add custom cards if any
        if "custom_cards" in self.metadata:
            # TODO: Add support for custom cards
            pass
            
        return cards
        
    def get_major_arcana_cards(self):
        """Get all major arcana cards"""
        cards = []
        
        # Check for localized names
        names = self.load_localized_names()
        
        # Standard major arcana: 0-21
        for i in range(22):
            card_id = f"major_arcana.{i:02d}"
            
            # Try to get name from localized names, fallback to default
            name = "Unknown"
            if names and "major_arcana" in names and f"{i:02d}" in names["major_arcana"]:
                name = names["major_arcana"][f"{i:02d}"]
            
            # Find image for the card
            image_path = self.find_card_image("major_arcana", f"{i:02d}")
            
            cards.append({
                "id": card_id,
                "name": name,
                "type": "major_arcana",
                "number": i,
                "image": image_path
            })
            
        return cards
        
    def get_minor_arcana_cards(self, suit):
        """Get all cards for a specific suit"""
        cards = []
        
        # Check for localized names
        names = self.load_localized_names()
        
        # Numbers: ace, two, ..., ten
        ranks = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        
        # Court cards: page, knight, queen, king
        courts = ["page", "knight", "queen", "king"]
        
        # Process numbered cards
        for rank in ranks:
            card_id = f"minor_arcana.{suit}.{rank}"
            
            # Try to get name from localized names, fallback to default
            name = f"{rank.capitalize()} of {suit.capitalize()}"
            if names and "minor_arcana" in names and suit in names["minor_arcana"] and rank in names["minor_arcana"][suit]:
                name = names["minor_arcana"][suit][rank]
            
            # Find image for the card
            image_path = self.find_card_image(f"minor_arcana/{suit}", rank)
            
            cards.append({
                "id": card_id,
                "name": name,
                "type": "minor_arcana",
                "suit": suit,
                "rank": rank,
                "image": image_path
            })
            
        # Process court cards
        for court in courts:
            card_id = f"minor_arcana.{suit}.{court}"
            
            # Try to get name from localized names, fallback to default
            name = f"{court.capitalize()} of {suit.capitalize()}"
            if names and "minor_arcana" in names and suit in names["minor_arcana"] and court in names["minor_arcana"][suit]:
                name = names["minor_arcana"][suit][court]
            
            # Find image for the card
            image_path = self.find_card_image(f"minor_arcana/{suit}", court)
            
            cards.append({
                "id": card_id,
                "name": name,
                "type": "minor_arcana",
                "suit": suit,
                "rank": court,
                "image": image_path
            })
            
        return cards
    
    def find_card_image(self, card_type, card_id):
        """Find the best available image for a card"""
        # Check in preferred order: h1200, h2400, h750, scalable, ansi32
        for folder in ["h1200", "h2400", "h750", "scalable"]:
            for ext in [".png", ".jpg", ".jpeg", ".svg"]:
                path = os.path.join(self.deck_path, folder, card_type, f"{card_id}{ext}")
                if os.path.exists(path):
                    return path
                
        # Try to find an image in any "h" prefixed folder, prioritizing highest resolution
        h_folders = []
        for item in os.listdir(self.deck_path):
            if os.path.isdir(os.path.join(self.deck_path, item)) and item.startswith('h') and item[1:].isdigit():
                h_folders.append(item)
        
        # Sort by resolution (numeric value after 'h') in descending order
        h_folders.sort(key=lambda x: int(x[1:]), reverse=True)
        
        # Look in each folder in order of resolution
        for folder in h_folders:
            pattern = os.path.join(self.deck_path, folder, card_type, f"{card_id}.*")
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
            
        # If not found in h folders, check any remaining folders
        pattern = os.path.join(self.deck_path, "*", card_type, f"{card_id}.*")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
            
        # Return a placeholder if no image found
        return None
        
    def load_localized_names(self, lang="en"):
        """Load localized names for cards"""
        names_file = os.path.join(self.deck_path, "names", f"{lang}.toml")
        if os.path.exists(names_file):
            with open(names_file, "r") as f:
                return toml.load(f)
        return None
        
    def get_card_backs(self):
        """Get available card back images"""
        backs = {}
        
        # Get default back
        default_back = self.metadata.get("card_backs", {}).get("default", "classic")
        
        # Find all backs
        pattern = os.path.join(self.deck_path, "card_backs", "*.png")
        back_files = glob.glob(pattern)
        
        for back_file in back_files:
            name = os.path.basename(back_file).split('.')[0]
            backs[name] = back_file
            
        return backs, default_back

    def get_name(self):
        return self.metadata.get("deck", {}).get("name", "Unknown Deck")

    def get_version(self):
        return self.metadata.get("deck", {}).get("version", "Unknown Version")
        
    def get_description(self):
        return self.metadata.get("deck", {}).get("description", "")
        
    def get_card_by_id(self, card_id):
        """Get a card by its ID"""
        for card in self.cards:
            if card["id"] == card_id:
                return card
        return None
        
    def get_random_card(self):
        """Get a random card from the deck"""
        if not self.cards:
            return None
        return random.choice(self.cards)
        
    def find_card_by_attributes(self, attributes):
        """Find a card by matching its attributes
        
        Args:
            attributes (dict): Dictionary of attributes to match
            
        Returns:
            dict: Card dictionary or None if not found
        """
        for card in self.cards:
            matches = True
            for key, value in attributes.items():
                if key not in card or card[key] != value:
                    matches = False
                    break
            if matches:
                return card
        return None
