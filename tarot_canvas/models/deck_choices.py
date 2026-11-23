"""Deck picker"""

import os

from tarot_canvas.models import library_curation
from tarot_canvas.models.deck_library import DeckLibrary, deck_library


def _order(deck):
    return deck.metadata.name.casefold(), DeckLibrary.path_key(deck.root_path)


def deck_choices(current=None, containing=None):
    """Tarot decks to populate our deck picker"""
    if isinstance(current, str | os.PathLike):
        kept = DeckLibrary.path_key(current)
    else:
        kept = DeckLibrary.path_key(current.root_path) if current is not None else None

    if containing is None:
        entries = [(deck, deck) for deck in deck_library.decks()]
    else:
        entries = [(deck, (deck, card)) for deck, card in deck_library.decks_containing(containing)]

    pins, hides = library_curation.deck_pins(), library_curation.deck_hides()
    pinned, rest = [], []

    for deck, entry in sorted(entries, key=lambda each: _order(each[0])):
        identifier = deck.metadata.identifier
        if identifier in hides and DeckLibrary.path_key(deck.root_path) != kept:
            continue
        (pinned if identifier in pins else rest).append(entry)

    return pinned, rest
