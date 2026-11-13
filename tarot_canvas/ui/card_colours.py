from tarot_canvas.models.card_ids import SUITS
from tarot_canvas.models.deck_types import CardKind

MAJOR_ARCANA = "major_arcana"

CARD_COLOURS = {
    MAJOR_ARCANA: "#916de4",  # Purple
    "wands": "#ff9800",  # Orange
    "cups": "#2196f3",  # Blue
    "swords": "#ffeb3b",  # Yellow
    "pentacles": "#4caf50",  # Green
    "default": "#9e9e9e",  # Gray, for a card of no known type or suit
}

SLOT_COLOUR = "#7f7f7f"

# In canonical order, as coverage's runs are
ARCANA_KEYS = (MAJOR_ARCANA, *SUITS)


def colour_of(kind, suit=None):
    """The colour for a card's kind then its suit"""
    if kind is CardKind.MAJOR:
        return CARD_COLOURS[MAJOR_ARCANA]
    if kind is CardKind.MINOR and suit in CARD_COLOURS:
        return CARD_COLOURS[suit]
    return CARD_COLOURS["default"]


def card_colour(card):
    """The colour for a card, or the default for None"""
    return colour_of(card.kind, card.suit_key) if card else colour_of(None)
