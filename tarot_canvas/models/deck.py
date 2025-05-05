import tomli
import os
import random
from pathlib import Path
import glob
from functools import lru_cache
from tarot_canvas.utils.logger import logger

class TarotDeck:
    """
    Represents a Tarot deck with methods to load and access cards and their metadata.
    
    The class follows these conventions:
    - load_*: Methods that read data from files
    - get_*: Methods that return data already in memory
    - find_*: Methods that search through existing data
    """
    
    def __init__(self, deck_path):
        """
        Initialize a TarotDeck from a deck directory.
        
        Args:
            deck_path (str): Path to the deck directory containing deck.toml
        """
        self.deck_path = deck_path
        self._metadata = None
        self._cards = None
        self._suit_aliases = None
        self._court_aliases = None
        self._card_backs = None
        self._default_back = None
        self._excluded_cards = set()
        self._excluded_reason = ""
        
        # Load essential data immediately
        self._metadata = self._load_metadata()
        self._suit_aliases = self._extract_suit_aliases()
        self._court_aliases = self._extract_court_aliases()
        self._excluded_cards, self._excluded_reason = self._extract_excluded_cards()  # New
        
        # Load cards
        self._cards = self._load_all_cards()

    # --------------------------------
    # PRIVATE DATA LOADING METHODS
    # --------------------------------
    
    def _load_metadata(self):
        """Load metadata from deck.toml file."""
        deck_file = os.path.join(self.deck_path, "deck.toml")
        if not os.path.exists(deck_file):
            raise FileNotFoundError(f"deck.toml not found in {self.deck_path}")

        with open(deck_file, "rb") as f:
            metadata = tomli.load(f)
            logger.debug(f"Loaded metadata for deck: {metadata.get('deck', {}).get('name', 'Unknown')}")
            return metadata

    def _extract_suit_aliases(self):
        """Extract suit aliases from metadata."""
        aliases = {}
        if "aliases" in self._metadata and "suits" in self._metadata["aliases"]:
            for canonical_suit, custom_name in self._metadata["aliases"]["suits"].items():
                aliases[canonical_suit] = custom_name
        
        if aliases:
            logger.debug(f"Deck '{self.get_name()}' has suit aliases: {aliases}")
        return aliases

    def _extract_court_aliases(self):
        """Extract court card aliases from metadata."""
        aliases = {}
        if "aliases" in self._metadata and "courts" in self._metadata["aliases"]:
            for canonical_court, custom_name in self._metadata["aliases"]["courts"].items():
                aliases[canonical_court] = custom_name
        return aliases

    def _extract_excluded_cards(self):
        """Extract excluded cards list from metadata."""
        excluded = set()
        reason = ""
        
        if "deck" in self._metadata and "excluded_cards" in self._metadata["deck"]:
            excluded_data = self._metadata["deck"]["excluded_cards"]
            if "cards" in excluded_data and isinstance(excluded_data["cards"], list):
                excluded.update(excluded_data["cards"])
        
            if "reason" in excluded_data:
                reason = excluded_data["reason"]
        
        if excluded:
            logger.debug(f"Deck '{self.get_name()}' has {len(excluded)} excluded cards")
        
        return excluded, reason

    def _load_all_cards(self):
        """Load all cards from the deck, respecting exclusions."""
        cards = []
        
        # Load major arcana cards
        cards.extend(self._load_major_arcana_cards())
        
        # Load minor arcana cards
        for suit in ["wands", "cups", "swords", "pentacles"]:
            cards.extend(self._load_minor_arcana_cards(suit))
            
        # Add custom cards if any
        if "custom_cards" in self._metadata:
            # TODO: Add support for custom cards
            pass
        
        # Filter out excluded cards
        filtered_cards = [card for card in cards if card["id"] not in self._excluded_cards]
        
        excluded_count = len(cards) - len(filtered_cards)
        if excluded_count > 0:
            logger.info(f"Excluded {excluded_count} cards from deck: {self.get_name()}")
        
        logger.info(f"Loaded {len(filtered_cards)} cards for deck: {self.get_name()}")    
        return filtered_cards
        
    def _load_major_arcana_cards(self):
        """Load all major arcana cards from the deck."""
        cards = []
        
        # Cache localized data to avoid repeated file access
        names = self._load_localized_names()
        alt_texts = self._load_localized_alt_texts()
        
        # Standard major arcana: 0-21
        for i in range(22):
            card_id = f"major_arcana.{i:02d}"
            
            # Try to get name from localized names, fallback to default
            name = "Unknown"
            if names and "major_arcana" in names and f"{i:02d}" in names["major_arcana"]:
                name = names["major_arcana"][f"{i:02d}"]
            
            # Find image for the card
            image_path = self._find_card_image_path("major_arcana", f"{i:02d}")
            
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
        
    def _load_minor_arcana_cards(self, suit):
        """Load all cards for a specific suit."""
        cards = []
        
        # Cache localized data
        names = self._load_localized_names()
        alt_texts = self._load_localized_alt_texts()
        
        # Get display suit name (using alias if available)
        display_suit = self.get_display_suit_name(suit)
        
        # Process numbered cards (ace through ten)
        ranks = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        for rank in ranks:
            card = self._build_minor_arcana_card(suit, rank, display_suit, names, alt_texts)
            cards.append(card)
            
        # Process court cards
        courts = ["page", "knight", "queen", "king"]
        for court in courts:
            card = self._build_court_card(suit, court, display_suit, names, alt_texts)
            cards.append(card)
            
        return cards
    
    def _build_minor_arcana_card(self, suit, rank, display_suit, names, alt_texts):
        """Build a minor arcana numbered card (ace through ten)."""
        card_id = f"minor_arcana.{suit}.{rank}"
        
        # Try to get name from localized names, fallback to default with display suit name
        name = f"{rank.capitalize()} of {display_suit}"
        if names and "minor_arcana" in names and suit in names["minor_arcana"] and rank in names["minor_arcana"][suit]:
            name = names["minor_arcana"][suit][rank]
        
        # Find image for the card
        image_path = self._find_card_image_path(f"minor_arcana/{suit}", rank)
        
        # Get alt text for the card
        alt_text = None
        if alt_texts and "minor_arcana" in alt_texts and suit in alt_texts["minor_arcana"] and rank in alt_texts["minor_arcana"][suit]:
            alt_text = alt_texts["minor_arcana"][suit][rank]
        
        return {
            "id": card_id,
            "name": name,
            "type": "minor_arcana",
            "suit": suit,             # Store canonical suit name
            "display_suit": display_suit,  # Store display suit name
            "rank": rank,
            "image": image_path,
            "alt_text": alt_text
        }
    
    def _build_court_card(self, suit, court, display_suit, names, alt_texts):
        """Build a court card (page, knight, queen, king)."""
        card_id = f"minor_arcana.{suit}.{court}"
        
        # Get display court name (using alias if available)
        display_court = self.get_display_court_name(court)
        
        # Try to get name from localized names, fallback to default with display names
        name = f"{display_court} of {display_suit}"
        if names and "minor_arcana" in names and suit in names["minor_arcana"] and court in names["minor_arcana"][suit]:
            name = names["minor_arcana"][suit][court]
        
        # Find image for the card
        image_path = self._find_card_image_path(f"minor_arcana/{suit}", court)
        
        # Get alt text for the card
        alt_text = None
        if alt_texts and "minor_arcana" in alt_texts and suit in alt_texts["minor_arcana"] and court in alt_texts["minor_arcana"][suit]:
            alt_text = alt_texts["minor_arcana"][suit][court]
        
        return {
            "id": card_id,
            "name": name,
            "type": "minor_arcana",
            "suit": suit,               # Store canonical suit name
            "display_suit": display_suit,   # Store display suit name 
            "rank": court,
            "display_rank": display_court,  # Store display rank name
            "image": image_path,
            "alt_text": alt_text
        }
        
    def _find_card_image_path(self, card_type, card_id):
        """Find the best available image for a card."""
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
        logger.warning(f"No image found for card: {card_type}/{card_id}")
        return None

    @lru_cache(maxsize=8)
    def _load_localized_names(self, lang="en"):
        """Load localized names for cards."""
        names_file = os.path.join(self.deck_path, "names", f"{lang}.toml")
        if os.path.exists(names_file):
            with open(names_file, "rb") as f:
                return tomli.load(f)
        return None

    @lru_cache(maxsize=8)
    def _load_localized_alt_texts(self, lang="en"):
        """Load alt texts for cards from localization files."""
        names_file = os.path.join(self.deck_path, "names", f"{lang}.toml")
        if os.path.exists(names_file):
            with open(names_file, "rb") as f:
                data = tomli.load(f)
                # Extract alt_text section if it exists
                if "alt_text" in data:
                    return data["alt_text"]
        return None
        
    def _load_card_backs(self):
        """Load available card back images."""
        backs = {}
        
        # Get default back
        default_back = self._metadata.get("card_backs", {}).get("default", "classic")
        
        # Find all backs
        pattern = os.path.join(self.deck_path, "card_backs", "*.png")
        back_files = glob.glob(pattern)
        
        for back_file in back_files:
            name = os.path.basename(back_file).split('.')[0]
            backs[name] = back_file
        
        self._card_backs = backs
        self._default_back = default_back
        
        return backs, default_back

    # --------------------------------
    # PUBLIC DATA ACCESS METHODS
    # --------------------------------

    def get_name(self):
        """Get the name of the deck."""
        return self._metadata.get("deck", {}).get("name", "Unknown Deck")

    def get_version(self):
        """Get the version of the deck."""
        return self._metadata.get("deck", {}).get("version", "Unknown Version")
        
    def get_description(self):
        """Get the description of the deck."""
        return self._metadata.get("deck", {}).get("description", "")
    
    def get_card_backs(self):
        """Get available card back images and the default back."""
        if self._card_backs is None:
            self._card_backs, self._default_back = self._load_card_backs()
        return self._card_backs, self._default_back
    
    def get_card_back_alt_text(self, back_name="classic", lang="en"):
        """Get alt text for a specific card back."""
        alt_texts = self._load_localized_alt_texts(lang)
        if alt_texts and "card_backs" in alt_texts and back_name in alt_texts["card_backs"]:
            return alt_texts["card_backs"][back_name]
        return None
        
    def get_card_by_id(self, card_id):
        """Get a card by its ID."""
        for card in self._cards:
            if card["id"] == card_id:
                return card
        return None
        
    def get_random_card(self):
        """Get a random card from the deck."""
        if not self._cards:
            return None
        return random.choice(self._cards)
        
    def get_cards_by_type(self, card_type):
        """
        Get all cards of a specific type from the deck.
        
        Args:
            card_type (str): Type of cards to retrieve (e.g., "major_arcana", "minor_arcana")
            
        Returns:
            list: List of card dictionaries matching the type
        """
        return [card for card in self._cards if card.get("type") == card_type]

    def get_suits(self):
        """
        Get all suits available in this deck.
        
        Returns:
            list: List of suit names (e.g., ["wands", "cups", "swords", "pentacles"])
        """
        suits = set()
        for card in self._cards:
            if card.get("type") == "minor_arcana" and "suit" in card:
                suits.add(card["suit"])
        return sorted(list(suits))

    def get_cards_by_suit(self, suit):
        """
        Get all cards of a specific suit from the deck.
        
        Args:
            suit (str): Suit name (e.g., "wands", "cups", "swords", "pentacles")
            
        Returns:
            list: List of card dictionaries matching the suit
        """
        return [card for card in self._cards if card.get("suit") == suit]
    
    def get_display_suit_name(self, canonical_suit):
        """
        Get the display name for a suit, using aliases if available.
        
        Args:
            canonical_suit (str): The canonical suit name (e.g., "wands")
            
        Returns:
            str: The display name for the suit
        """
        if canonical_suit in self._suit_aliases:
            display_name = self._suit_aliases[canonical_suit]
            return display_name
        
        return canonical_suit.capitalize()

    def get_display_court_name(self, canonical_court):
        """
        Get the display name for a court card, using aliases if available.
        
        Args:
            canonical_court (str): The canonical court name (e.g., "page")
            
        Returns:
            str: The display name for the court card
        """
        if canonical_court in self._court_aliases:
            return self._court_aliases[canonical_court]
        return canonical_court.capitalize()
    
    def get_canonical_suit_name(self, suit):
        """
        Get the canonical name for a suit, handling aliases.
        
        Args:
            suit (str): The suit name or alias
            
        Returns:
            str: The canonical suit name
        """
        # Check if this is an aliased suit name
        for canonical, alias in self._suit_aliases.items():
            if alias.lower() == suit.lower():
                return canonical
        return suit

    def is_suit_excluded(self, suit):
        """
        Check if an entire suit is excluded from the deck.
        
        Args:
            suit (str): Canonical suit name to check
        
        Returns:
            bool: True if all cards of this suit are excluded
        """
        # Get all cards that would be in this suit
        ranks = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", 
                 "page", "knight", "queen", "king"]
        
        # Check if all possible cards in this suit are excluded
        all_excluded = True
        for rank in ranks:
            card_id = f"minor_arcana.{suit}.{rank}"
            if card_id not in self._excluded_cards:
                all_excluded = False
                break
                
        return all_excluded

    def get_exclusion_reason(self):
        """Get the reason for card exclusions, if any."""
        return self._excluded_reason

    # --------------------------------
    # SEARCH/FIND METHODS
    # --------------------------------
    
    def find_card_by_attributes(self, attributes):
        """
        Find a card by matching its attributes.
        
        Args:
            attributes (dict): Dictionary of attributes to match
            
        Returns:
            dict: Card dictionary or None if not found
        """
        for card in self._cards:
            matches = True
            for key, value in attributes.items():
                if key not in card or card[key] != value:
                    matches = False
                    break
            if matches:
                return card
        return None
