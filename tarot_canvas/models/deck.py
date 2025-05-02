import toml
import os
import random
from pathlib import Path
import glob
from tarot_canvas.utils.logger import logger

class TarotDeck:
    def __init__(self, deck_path):
        self.deck_path = deck_path
        self.metadata = self.load_metadata()
        self.suit_aliases = self.get_suit_aliases()  # Load suit aliases
        self.court_aliases = self.get_court_aliases()  # Load court card aliases
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
        
        # Load alt text
        alt_texts = self.load_alt_texts()
        
        # Standard major arcana: 0-21
        for i in range(22):
            card_id = f"major_arcana.{i:02d}"
            
            # Try to get name from localized names, fallback to default
            name = "Unknown"
            if names and "major_arcana" in names and f"{i:02d}" in names["major_arcana"]:
                name = names["major_arcana"][f"{i:02d}"]
            
            # Find image for the card
            image_path = self.find_card_image("major_arcana", f"{i:02d}")
            
            # Get alt text for the card
            alt_text = None
            if alt_texts and "major_arcana" in alt_texts and f"{i:02d}" in alt_texts["major_arcana"]:
                alt_text = alt_texts["major_arcana"][f"{i:02d}"]
            
            cards.append({
                "id": card_id,
                "name": name,
                "type": "major_arcana",
                "number": i,
                "image": image_path,
                "alt_text": alt_text
            })
            
        return cards
        
    def get_minor_arcana_cards(self, suit):
        """Get all cards for a specific suit"""
        cards = []
        
        # Check for localized names
        names = self.load_localized_names()
        
        # Load alt text
        alt_texts = self.load_alt_texts()
        
        # Get display suit name (using alias if available)
        display_suit = self.get_display_suit_name(suit)
        
        # Numbers: ace, two, ..., ten
        ranks = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        
        # Court cards: page, knight, queen, king
        courts = ["page", "knight", "queen", "king"]
        
        # Process numbered cards
        for rank in ranks:
            card_id = f"minor_arcana.{suit}.{rank}"
            
            # Try to get name from localized names, fallback to default with display suit name
            name = f"{rank.capitalize()} of {display_suit}"
            if names and "minor_arcana" in names and suit in names["minor_arcana"] and rank in names["minor_arcana"][suit]:
                name = names["minor_arcana"][suit][rank]
            
            # Find image for the card
            image_path = self.find_card_image(f"minor_arcana/{suit}", rank)
            
            # Get alt text for the card
            alt_text = None
            if alt_texts and "minor_arcana" in alt_texts and suit in alt_texts["minor_arcana"] and rank in alt_texts["minor_arcana"][suit]:
                alt_text = alt_texts["minor_arcana"][suit][rank]
            
            cards.append({
                "id": card_id,
                "name": name,
                "type": "minor_arcana",
                "suit": suit,              # Store canonical suit name
                "display_suit": display_suit,  # Store display suit name
                "rank": rank,
                "image": image_path,
                "alt_text": alt_text
            })
            
        # Process court cards
        for court in courts:
            card_id = f"minor_arcana.{suit}.{court}"
            
            # Get display court name (using alias if available)
            display_court = self.get_display_court_name(court)
            
            # Try to get name from localized names, fallback to default with display names
            name = f"{display_court} of {display_suit}"
            if names and "minor_arcana" in names and suit in names["minor_arcana"] and court in names["minor_arcana"][suit]:
                name = names["minor_arcana"][suit][court]
            
            # Find image for the card
            image_path = self.find_card_image(f"minor_arcana/{suit}", court)
            
            # Get alt text for the card
            alt_text = None
            if alt_texts and "minor_arcana" in alt_texts and suit in alt_texts["minor_arcana"] and court in alt_texts["minor_arcana"][suit]:
                alt_text = alt_texts["minor_arcana"][suit][court]
            
            cards.append({
                "id": card_id,
                "name": name,
                "type": "minor_arcana",
                "suit": suit,               # Store canonical suit name
                "display_suit": display_suit,   # Store display suit name 
                "rank": court,
                "display_rank": display_court,  # Store display rank name
                "image": image_path,
                "alt_text": alt_text
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
    
    def load_alt_texts(self, lang="en"):
        """Load alt texts for cards from localization files"""
        names_file = os.path.join(self.deck_path, "names", f"{lang}.toml")
        if os.path.exists(names_file):
            with open(names_file, "r") as f:
                data = toml.load(f)
                # Extract alt_text section if it exists
                if "alt_text" in data:
                    return data["alt_text"]
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
    
    def get_card_back_alt_text(self, back_name="classic", lang="en"):
        """Get alt text for a specific card back"""
        alt_texts = self.load_alt_texts(lang)
        if alt_texts and "card_backs" in alt_texts and back_name in alt_texts["card_backs"]:
            return alt_texts["card_backs"][back_name]
        return None

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

    def get_cards_by_type(self, card_type):
        """Get all cards of a specific type from the deck
        
        Args:
            card_type (str): Type of cards to retrieve (e.g., "major_arcana", "minor_arcana")
            
        Returns:
            list: List of card dictionaries matching the type
        """
        return [card for card in self.cards if card.get("type") == card_type]

    def get_suits(self):
        """Get all suits available in this deck
        
        Returns:
            list: List of suit names (e.g., ["wands", "cups", "swords", "pentacles"])
        """
        suits = set()
        for card in self.cards:
            if card.get("type") == "minor_arcana" and "suit" in card:
                suits.add(card["suit"])
        return sorted(list(suits))

    def get_cards_by_suit(self, suit):
        """Get all cards of a specific suit from the deck
        
        Args:
            suit (str): Suit name (e.g., "wands", "cups", "swords", "pentacles")
            
        Returns:
            list: List of card dictionaries matching the suit
        """
        return [card for card in self.cards if card.get("suit") == suit]

    def get_suit_aliases(self):
        """Get suit aliases from metadata if available"""
        aliases = {}
        if "aliases" in self.metadata and "suits" in self.metadata["aliases"]:
            for canonical_suit, custom_name in self.metadata["aliases"]["suits"].items():
                aliases[canonical_suit] = custom_name
        
        if aliases:
            logger.debug(f"Deck '{self.get_name()}' has suit aliases: {aliases}")
        return aliases

    def get_court_aliases(self):
        """Get court card aliases from metadata if available"""
        aliases = {}
        if "aliases" in self.metadata and "courts" in self.metadata["aliases"]:
            for canonical_court, custom_name in self.metadata["aliases"]["courts"].items():
                aliases[canonical_court] = custom_name
        return aliases
    
    def get_canonical_suit_name(self, suit):
        """Get the canonical name for a suit, handling aliases"""
        # Check if this is an aliased suit name
        for canonical, alias in self.suit_aliases.items():
            if alias.lower() == suit.lower():
                return canonical
        return suit

    def get_display_suit_name(self, canonical_suit):
        """Get the display name for a suit, using aliases if available"""
        if canonical_suit in self.suit_aliases:
            display_name = self.suit_aliases[canonical_suit]
            return display_name
        
        return canonical_suit.capitalize()

    def get_display_court_name(self, canonical_court):
        """Get the display name for a court card, using aliases if available"""
        if canonical_court in self.court_aliases:
            return self.court_aliases[canonical_court]
        return canonical_court.capitalize()
