import os
import tomli
from pathlib import Path
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

class EsotericaManager:
    """
    Manages esoteric text content from reference sources like books or websites.
    This allows displaying interpretations, correspondences, and passages for each card.
    """
    
    def __init__(self):
        self.sources = {}
        self.load_sources()
        
    def load_sources(self):
        """Load all available esoterica sources from the data directory"""
        # Get the data directory for esoterica content
        data_dir = get_data_directory()
        esoterica_dir = os.path.join(data_dir, "tarot", "esoterica", "references")
        
        # Create the directory if it doesn't exist
        os.makedirs(esoterica_dir, exist_ok=True)
        
        logger.debug(f"Looking for esoterica files in: {esoterica_dir}")
        
        # Look for all .toml files recursively in the esoterica directory
        toml_files = list(Path(esoterica_dir).glob("**/*.toml"))
        
        if not toml_files:
            logger.warning(f"No .toml files found in {esoterica_dir} (including subdirectories)")
            
            # Also check the current directory for development/testing
            current_dir_files = list(Path(".").glob("*.toml"))
            if current_dir_files:
                logger.info(f"Found {len(current_dir_files)} .toml files in current directory, attempting to load")
                for file_path in current_dir_files:
                    if "tarot-for-change" in file_path.name:
                        try:
                            logger.info(f"Attempting to load: {file_path}")
                            self._load_source(file_path)
                        except Exception as e:
                            logger.error(f"Error loading esoterica source {file_path}: {e}")
        
        # Process all files found in the esoterica directory and its subdirectories
        for file_path in toml_files:
            try:
                logger.debug(f"Loading esoterica file: {file_path}")
                self._load_source(file_path)
            except Exception as e:
                logger.error(f"Error loading esoterica source {file_path}: {e}")
        
        logger.info(f"Loaded {len(self.sources)} esoterica sources")
    
    def _load_source(self, file_path):
        """Load a single esoterica source from a .toml file"""
        try:
            logger.debug(f"Opening file: {file_path}")
            with open(file_path, "rb") as f:
                try:
                    content = tomli.load(f)
                    logger.debug(f"Successfully parsed TOML: {file_path}")
                except Exception as parse_error:
                    logger.error(f"Failed to parse TOML file {file_path}: {parse_error}")
                    return
                
            # Debug the content structure
            logger.debug(f"TOML content keys: {list(content.keys())}")
                
            # Extract source metadata
            if "meta" not in content:
                logger.warning(f"Missing 'meta' section in {file_path}")
                return
                
            meta = content["meta"]
            source_id = meta.get("id")
            
            if not source_id:
                logger.warning(f"Missing 'id' in meta section of {file_path}")
                return
                
            # Debug the passages structure
            if "passages" in content:
                logger.debug(f"Passages section found with keys: {list(content['passages'].keys())}")
                
                # Check for major arcana passages
                if "major_arcana" in content["passages"]:
                    major_keys = list(content["passages"]["major_arcana"].keys())
                    logger.debug(f"Found major arcana passages for: {major_keys}")
                
                # Check for minor arcana passages
                if "minor_arcana" in content["passages"]:
                    minor_suits = list(content["passages"]["minor_arcana"].keys())
                    logger.debug(f"Found minor arcana passages for suits: {minor_suits}")
            else:
                logger.warning(f"No 'passages' section found in {file_path}")
                
            # Store the source by ID for easy access
            self.sources[source_id] = {
                "meta": meta,
                "passages": content.get("passages", {})
            }
            
            logger.info(f"Successfully loaded esoterica source: {meta.get('name', source_id)}")
            
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
        except PermissionError:
            logger.error(f"Permission denied when opening {file_path}")
        except Exception as e:
            logger.error(f"Error parsing esoterica file {file_path}: {e}")
    
    def get_passages_for_card(self, card_id):
        """
        Get all passages for a specific card from all available sources.
        
        Args:
            card_id: The card ID to look for (e.g., "major_arcana.00" for The Fool)
            
        Returns:
            A list of dictionaries with passage and source information
        """
        logger.debug(f"Looking for passages for card ID: {card_id}")
        
        results = []
        
        # Determine card type and number for lookup
        card_type = None
        card_number = None
        suit = None
        
        # Handle card ID formats
        if "major_arcana" in card_id:
            # Format: major_arcana.00
            card_type = "major_arcana"
            # Extract just the number part (last segment after the dot)
            card_number = card_id.split(".")[-1]
            logger.debug(f"Parsed as major arcana card number: {card_number}")
        elif "minor_arcana" in card_id:
            # Format: minor_arcana.wands.ace
            parts = card_id.split(".")
            if len(parts) == 3:
                card_type = "minor_arcana"
                suit = parts[1]
                card_number = parts[2]
                logger.debug(f"Parsed as minor arcana card: suit={suit}, number={card_number}")
        
        # If we couldn't parse the card ID, return empty list
        if not card_type:
            logger.warning(f"Could not parse card ID format: {card_id}")
            return results
            
        # Check all sources for matching passages
        for source_id, source in self.sources.items():
            logger.debug(f"Checking source '{source_id}' for card {card_type}.{card_number}")
            passage = self._find_passage_in_source(source, card_type, card_number, suit)
            if passage:
                logger.debug(f"Found passage in source '{source_id}'")
                results.append(passage)
            else:
                logger.debug(f"No passage found in source '{source_id}'")
                
        logger.info(f"Found {len(results)} passages for card {card_id}")
        return results
    
    def get_passage_for_card(self, card_id, source_id=None):
        """
        Get a passage for a specific card from a specific source or from all sources.
        
        Args:
            card_id: The card ID to look for (e.g., "major_arcana.00" for The Fool)
            source_id: Optional source ID to look in. If None, will return the first match from any source.
            
        Returns:
            A dictionary with passage and source information, or None if not found
        """
        logger.debug(f"Looking for passage for card ID: {card_id}, source: {source_id or 'any'}")
        
        # Determine card type and number for lookup
        card_type = None
        card_number = None
        suit = None
        
        # Handle card ID formats
        if "major_arcana" in card_id:
            # Format: major_arcana.00
            card_type = "major_arcana"
            # Extract just the number part (last segment after the dot)
            card_number = card_id.split(".")[-1]
            logger.debug(f"Parsed as major arcana card number: {card_number}")
        elif "minor_arcana" in card_id:
            # Format: minor_arcana.wands.ace
            parts = card_id.split(".")
            if len(parts) == 3:
                card_type = "minor_arcana"
                suit = parts[1]
                card_number = parts[2]
                logger.debug(f"Parsed as minor arcana card: suit={suit}, number={card_number}")
        
        # If we couldn't parse the card ID, return None
        if not card_type:
            logger.warning(f"Could not parse card ID format: {card_id}")
            return None
            
        # If a specific source is requested, only check that one
        if source_id and source_id in self.sources:
            logger.debug(f"Checking specific source: {source_id}")
            return self._find_passage_in_source(self.sources[source_id], card_type, card_number, suit)
            
        # Otherwise check all sources and return the first match
        for source_id, source in self.sources.items():
            logger.debug(f"Checking source '{source_id}' for card {card_type}.{card_number}")
            passage = self._find_passage_in_source(source, card_type, card_number, suit)
            if passage:
                logger.debug(f"Found passage in source '{source_id}'")
                return passage
                
        logger.debug(f"No passage found for card {card_id}")
        return None
    
    def _find_passage_in_source(self, source, card_type, card_number, suit=None):
        """
        Find a passage for a card in a specific source
        
        Args:
            source: The source dictionary
            card_type: 'major_arcana' or 'minor_arcana'
            card_number: Card number as string (e.g., '00', '01')
            suit: Optional suit name for minor arcana
            
        Returns:
            Dictionary with passage and source info or None
        """
        passages = source.get("passages", {})
        
        # For major arcana, check passages.major_arcana.XX
        if card_type == "major_arcana" and card_type in passages:
            major_passages = passages[card_type]
            if card_number in major_passages:
                logger.debug(f"Found major arcana passage for card {card_number}")
                return {
                    "text": major_passages[card_number].get("text", ""),
                    "source": source["meta"]
                }
                
        # For minor arcana, check passages.minor_arcana.suit.XX
        elif card_type == "minor_arcana" and card_type in passages:
            minor_passages = passages[card_type]
            if suit and suit in minor_passages and card_number in minor_passages[suit]:
                logger.debug(f"Found minor arcana passage for {suit} {card_number}")
                return {
                    "text": minor_passages[suit][card_number].get("text", ""),
                    "source": source["meta"]
                }
                
        return None
    
    def get_all_sources(self):
        """Get metadata for all loaded sources"""
        return {source_id: source["meta"] for source_id, source in self.sources.items()}

# Create a singleton instance
esoterica_manager = EsotericaManager()