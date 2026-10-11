from tarot_canvas.ui.card_colours import CARD_COLOURS, card_colour


def test_an_unknown_card_takes_the_default():
    assert card_colour(None) == CARD_COLOURS["default"]
    assert card_colour({"type": "minor_arcana", "suit": "coins"}) == CARD_COLOURS["default"]
    assert card_colour({"type": "oracle"}) == CARD_COLOURS["default"]
