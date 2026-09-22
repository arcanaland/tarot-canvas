from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck import TarotDeck


def test_canonical_order_is_the_majors_then_four_suits():
    assert len(CANONICAL_CARD_IDS) == 78
    assert len(set(CANONICAL_CARD_IDS)) == 78
    assert CANONICAL_CARD_IDS[0] == "major_arcana.00"
    assert CANONICAL_CARD_IDS[21] == "major_arcana.21"
    assert CANONICAL_CARD_IDS[22] == "minor_arcana.wands.ace"
    assert CANONICAL_CARD_IDS[-1] == "minor_arcana.pentacles.king"


def test_a_deck_with_nothing_excluded_walks_the_canonical_order(tmp_path):
    (tmp_path / "deck.toml").write_text(
        """
        [deck]
        schema_version = "2.0"
        name = "Bare"
        version = "1.0"
        """,
        encoding="utf-8",
    )
    deck = TarotDeck(str(tmp_path))

    assert tuple(c["id"] for c in deck.get_all_cards()) == CANONICAL_CARD_IDS
