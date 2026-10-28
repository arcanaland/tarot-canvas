from tarot_canvas.models.card_ids import SUITS

MAJOR_ARCANA = "major_arcana"

CARD_COLOURS = {
    MAJOR_ARCANA: "#916de4",  # Purple
    "wands": "#ff9800",  # Orange
    "cups": "#2196f3",  # Blue
    "swords": "#ffeb3b",  # Yellow
    "pentacles": "#4caf50",  # Green
    "default": "#9e9e9e",  # Gray, for a card of no known type or suit
}

# In canonical order, as coverage's runs are
ARCANA_KEYS = (MAJOR_ARCANA, *SUITS)


def card_colour_key(card):
    """The CARD_COLOURS key for a card dict by its type then its suit"""
    if not card:
        return "default"
    card_type = card.get("type", "")
    if card_type == MAJOR_ARCANA:
        return MAJOR_ARCANA
    if card_type == "minor_arcana" and card.get("suit", "") in CARD_COLOURS:
        return card["suit"]
    return "default"


def card_colour(card):
    """The colour for a card dict by its type then its suit"""
    return CARD_COLOURS[card_colour_key(card)]
