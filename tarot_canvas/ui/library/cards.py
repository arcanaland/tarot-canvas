"""A card of a deck by its id, as the Library's lists name and picture it"""


def card_in(deck, card_id):
    if deck is None:
        return None
    try:
        return deck.get_card_by_id(card_id)
    except Exception:
        return None


def card_name(deck, card_id):
    """The deck's name for the card."""
    card = card_in(deck, card_id)
    name = (card or {}).get("name")
    return name or card_id


def card_cover_path(deck, card_id):
    card = card_in(deck, card_id)
    return (card or {}).get("image")
