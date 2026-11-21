"""Classify an image as a card ID from its file name alone, never from the image"""

import re

from tarot_canvas.models.card_ids import COURTS, MAJOR_ARCANA_COUNT, PIPS, SUITS
from tarot_canvas.models.deck_writer import BACK, slug

_IGNORED = frozenset({"of", "the", "card", "tarot", "major", "arcana", "minor"})
_RUNS = re.compile(r"[a-z]+|[0-9]+")
_RANKS = PIPS + COURTS


def tokens(text):
    """text's words and numbers, lowercase ASCII, less the words that name no card"""
    found = []
    for part in slug(text).split("-"):
        found.extend(_RUNS.findall(part))
    return [token for token in found if token not in _IGNORED]


def classify_card_id(stem, deck):
    """The card ID (or BACK) an image's file name names, or None: only as good as the name"""
    words = tokens(stem)
    if not words:
        return None

    in_deck = {card.canonical_id: card for card in deck.cards}

    if len(words) == 1 and words[0].isdigit():
        number = int(words[0])
        card_id = f"major_arcana.{number:02d}" if number < MAJOR_ARCANA_COUNT else None
        return card_id if card_id in in_deck else None

    for card_id, card in in_deck.items():
        if card_id.startswith("major_arcana.") and tokens(card.display_name or "") == words:
            return card_id

    card_id = _minor(words)
    if card_id is not None:
        return card_id if card_id in in_deck else None

    if words in (["back"], ["cardback"]):
        return BACK
    return None


def _minor(words):
    suits = [word for word in words if word in SUITS]
    ranks = [rank for rank in (_rank(word) for word in words) if rank is not None]
    if len(suits) == 1 and len(ranks) == 1 and len(words) == 2:
        return f"minor_arcana.{suits[0]}.{ranks[0]}"
    return None


def _rank(word):
    if word in _RANKS:
        return word
    if word.isdigit() and 1 <= int(word) <= len(PIPS):
        return PIPS[int(word) - 1]
    return None
