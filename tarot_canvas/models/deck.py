import toml
import os

class TarotDeck:
    def __init__(self, deck_path):
        self.deck_path = deck_path
        self.metadata = self.load_metadata()

    def load_metadata(self):
        deck_file = os.path.join(self.deck_path, "deck.toml")
        if not os.path.exists(deck_file):
            raise FileNotFoundError(f"deck.toml not found in {self.deck_path}")

        with open(deck_file, "r") as f:
            return toml.load(f)

    def get_card_backs(self):
        return self.metadata.get("card_backs", {}).get("default", "classic")

    def get_name(self):
        return self.metadata.get("deck", {}).get("name", "Unknown Deck")

    def get_version(self):
        return self.metadata.get("deck", {}).get("version", "Unknown Version")
