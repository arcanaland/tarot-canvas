from tarot_canvas.models.deck_types import Card, CardKind
from tarot_canvas.ui.card_colours import CARD_COLOURS, card_colour


def test_an_unknown_card_takes_the_default():
    coins = Card(
        canonical_id="minor_arcana.coins.ace",
        kind=CardKind.MINOR,
        display_name="Ace of Coins",
        suit_key="coins",
    )
    assert card_colour(None) == CARD_COLOURS["default"]
    assert card_colour(coins) == CARD_COLOURS["default"]
