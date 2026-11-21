"""Every deck the app knows, loaded once each and keyed by resolved path."""

import logging
import os
from collections import defaultdict
from pathlib import Path

from tarot_canvas.models import staged_delete
from tarot_canvas.models.arcana_backend import load_deck
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.reference_deck import ReferenceDeck
from tarot_canvas.utils.path_helper import get_decks_directory

log = logging.getLogger(__name__)


class DeckLibrary:
    def __init__(self):
        self._reference = None
        # Scanned decks, listed by decks()
        self._scanned = {}
        # Every deck load() has built, scanned or not
        self._loaded = {}
        self._scan()

    @staticmethod
    def path_key(path):
        """A deck's identity: its path, resolved and case-folded where the OS folds case."""
        if not path:
            return None
        return os.path.normcase(os.path.realpath(os.fspath(path)))

    def decks(self):
        """The reference deck first, if present, then the others in path order."""
        others = tuple(self._scanned[key] for key in sorted(self._scanned))
        return (self._reference, *others) if self._reference is not None else others

    def reference(self):
        """The reference deck, or None if it hasn't been downloaded."""
        return self._reference

    def load(self, path):
        """The deck at path, built on first use. Raises what load_deck raises."""
        key = self.path_key(path)
        deck = self._loaded.get(key)
        if deck is None:
            deck = load_deck(path)
            self._loaded[key] = deck
        return deck

    def reload(self, path):
        """read a deck from disk again"""
        key = self.path_key(path)
        deck = load_deck(path)
        self._loaded[key] = deck
        if key in self._scanned:
            self._scanned[key] = deck
        deck_events().decks_changed.emit()
        return deck

    def find_by_identifier(self, identifier):
        return tuple(deck for deck in self.decks() if deck.metadata.identifier == identifier)

    def decks_containing(self, card_id):
        """(deck, card) for every deck that has card_id with its image on disk."""
        found = []
        for deck in self.decks():
            card = deck.find_card(card_id)
            if card and card.default_image() and os.path.exists(card.default_image()):
                found.append((deck, card))
        return found

    def rescan(self):
        """Forget every deck and scan again. Tabs keep the deck objects they hold."""
        self._scan()
        deck_events().decks_changed.emit()

    def _scan(self):
        self._reference = None
        self._scanned = {}
        self._loaded = {}
        self._load_reference()
        for root in self._deck_roots():
            log.info("Loading decks from %s", root)
            for name in os.listdir(root):
                path = os.path.join(root, name)
                # Hidden: an install still being copied in. Staged: a removal still undoable
                if (
                    name.startswith(".")
                    or staged_delete.is_staged(name)
                    or not os.path.isfile(os.path.join(path, "deck.toml"))
                ):
                    continue
                key = self.path_key(path)
                if key in self._loaded:
                    continue
                try:
                    deck = self.load(path)
                except Exception as e:
                    log.exception("Error loading deck %s: %s", path, e)
                    continue
                self._scanned[key] = deck
                log.info("Loaded deck '%s' from %s", deck.metadata.name, path)
        self._warn_on_shared_identifiers()

    def _load_reference(self):
        if not ReferenceDeck.is_reference_deck_present():
            log.warning("Reference deck not found")
            return
        try:
            self._reference = self.load(ReferenceDeck.get_reference_deck_path())
            log.info("Reference deck loaded successfully")
        except Exception as e:
            log.exception("Error loading reference deck: %s", e)

    @staticmethod
    def _deck_roots():
        """The deck directories that exist, creating the primary one."""
        roots = get_decks_directory()
        os.makedirs(roots[0], exist_ok=True)
        return [root for root in roots if os.path.isdir(root)]

    def _warn_on_shared_identifiers(self):
        paths = defaultdict(list)
        for deck in self.decks():
            if deck.metadata.identifier is not None:
                paths[deck.metadata.identifier].append(os.fspath(deck.root_path))
        for identifier, shared in paths.items():
            if len(shared) > 1:
                log.warning(
                    "%s decks share the identifier '%s': %s",
                    len(shared),
                    identifier,
                    ", ".join(shared),
                )


def is_removable(deck):
    """Whether the deck's folder is one the app installed and may take away"""
    root = Path(get_decks_directory()[0]).resolve()
    return Path(deck.root_path).resolve().parent == root


deck_library = DeckLibrary()
