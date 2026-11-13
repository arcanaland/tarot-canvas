"""What every note editor does, wherever it is shown: write its file, and offer and follow links"""

import os

from tarot_canvas.models import notes as notes_model
from tarot_canvas.utils.logger import logger


def write_note(file_path, content):
    """Write content to file_path, making its folder, and make it durable; raises OSError"""
    dir_path = os.path.dirname(file_path)
    os.makedirs(dir_path, exist_ok=True)

    logger.info(f"Saving note to: {file_path}")
    logger.info(f"Directory: {dir_path} exists: {os.path.exists(dir_path)}")
    logger.info(f"Content length: {len(content)} characters")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        # On disk before the file is closed
        f.flush()
        os.fsync(f.fileno())

    if os.path.exists(file_path):
        logger.info(f"File saved successfully: {os.path.getsize(file_path)} bytes")
    else:
        logger.error(f"File doesn't exist after save: {file_path}")

    os.utime(file_path, None)


class NoteLinks:
    """Where a note's links lead, and what the link completer offers.

    tab emits navigation_requested; card_id() is the card the notes being edited are
    about, if any; open_here(path) opens a note of that card where it is being edited.
    """

    def __init__(self, tab, deck_manager, card_id, open_here=None):
        self.tab = tab
        self.deck_manager = deck_manager
        self.card_id = card_id
        self.open_here = open_here
        self.notes_index = {}  # card_id -> [Note], the whole card library
        self.all_notes = {}  # (card_id, path) -> Note

    def refresh(self):
        """Re-read every card's notes"""
        self.notes_index = notes_model.scan()
        self.all_notes = {
            (note.card_id, str(note.path)): note
            for notes in self.notes_index.values()
            for note in notes
        }

    def _can_navigate(self):
        return self.tab is not None and self.deck_manager is not None

    def suggestions(self):
        """Get suggestions for auto-completion when linking"""
        suggestions = []

        # Add all note names, first occurrence wins so the order is stable
        seen = set()
        for note in self.all_notes.values():
            if note.title and note.title not in seen:
                seen.add(note.title)
                suggestions.append(note.title)

        if self._can_navigate():
            # Add all cards from reference deck
            ref_deck = self.deck_manager.get_reference_deck()
            if ref_deck:
                # Use _cards directly or get_all_cards() if available
                cards = getattr(ref_deck, "get_all_cards", lambda: ref_deck._cards)()
                for card in cards:
                    suggestions.append(f"card:{card.display_name}")

            # Add all decks
            for deck in self.deck_manager.get_all_decks():
                suggestions.append(f"deck:{deck.get_name()}")

        return suggestions

    def follow(self, link_text):
        """Handle clicks on wiki links or markdown links"""
        if link_text.startswith("card:"):
            self.navigate_to_card(link_text[5:])
        elif link_text.startswith("deck:"):
            self.navigate_to_deck(link_text[5:])
        else:
            # Assume it's a note link
            self.navigate_to_note(link_text)

    def navigate_to_card(self, card_name):
        """Navigate to a specific card by name"""
        if not self._can_navigate():
            return
        ref_deck = self.deck_manager.get_reference_deck()
        if ref_deck:
            cards = getattr(ref_deck, "get_all_cards", lambda: ref_deck._cards)()
            for card in cards:
                if card.display_name.lower() == card_name.lower():
                    self.tab.navigation_requested.emit(
                        "open_card_view", {"card": card, "deck": ref_deck}
                    )
                    return

    def navigate_to_deck(self, deck_name):
        """Navigate to a specific deck by name"""
        if not self._can_navigate():
            return
        for deck in self.deck_manager.get_all_decks():
            if deck.get_name().lower() == deck_name.lower():
                self.tab.navigation_requested.emit("open_deck_view", {"deck_path": deck.deck_path})
                return

    def find_note_by_title(self, note_name):
        """A title is not unique across cards: prefer card_id()'s, then the newest.

        An empty needle matches nothing: every unnamed note has title "", so `[[]]` would
        otherwise resolve to all of them at once.
        """
        if not note_name:
            return None

        matches = [note for note in self.all_notes.values() if note.title == note_name]
        if not matches:
            return None

        card_id = self.card_id()
        if card_id:
            here = [note for note in matches if note.card_id == card_id]
            if here:
                return max(here, key=lambda note: note.modified)

        return max(matches, key=lambda note: note.modified)

    def navigate_to_note(self, note_name):
        """Open the note titled note_name: here if it is card_id()'s, else on its card"""
        note_info = self.find_note_by_title(note_name)
        if not note_info:
            return

        # A note of another card opens in that card's view
        if note_info.card_id != self.card_id() and self._can_navigate():
            ref_deck = self.deck_manager.get_reference_deck()
            if ref_deck:
                cards = getattr(ref_deck, "get_all_cards", lambda: ref_deck._cards)()
                for card in cards:
                    if card.canonical_id == note_info.card_id:
                        self.tab.navigation_requested.emit(
                            "open_card_view",
                            {"card": card, "deck": ref_deck, "open_note": note_name},
                        )
                        return

        if self.open_here is not None:
            self.open_here(str(note_info.path))
