import pytest

from tarot_canvas.models.card_search import (
    EXACT,
    PREFIX,
    SUBSTRING,
    SYNONYMS,
    WORDS,
    CardTerms,
    Query,
    roman,
)

FOOL = {"id": "major_arcana.00", "name": "The Fool", "type": "major_arcana", "number": 0}
MAGICIAN = {"id": "major_arcana.01", "name": "The Magician", "type": "major_arcana", "number": 1}
EMPRESS = {"id": "major_arcana.03", "name": "The Empress", "type": "major_arcana", "number": 3}
STRENGTH = {"id": "major_arcana.08", "name": "Strength", "type": "major_arcana", "number": 8}
WHEEL = {
    "id": "major_arcana.10",
    "name": "Wheel of Fortune",
    "type": "major_arcana",
    "number": 10,
}
TOWER = {"id": "major_arcana.16", "name": "The Tower", "type": "major_arcana", "number": 16}


def minor(rank, suit, display_rank=None):
    card = {
        "id": f"minor_arcana.{suit}.{rank}",
        "name": f"{rank.title()} of {suit.title()}",
        "type": "minor_arcana",
        "suit": suit,
        "display_suit": suit.title(),
        "rank": rank,
    }
    if display_rank:
        card["display_rank"] = display_rank
    return card


ACE_OF_CUPS = minor("ace", "cups")
THREE_OF_CUPS = minor("three", "cups")
TEN_OF_SWORDS = minor("ten", "swords")
QUEEN_OF_SWORDS = minor("queen", "swords", "Queen")
PAGE_OF_PENTACLES = minor("page", "pentacles", "Page")
KNIGHT_OF_WANDS = minor("knight", "wands", "Knight")


def tier(card, text, deck_name="Rider-Waite-Smith Tarot"):
    return CardTerms(card, deck_name).tier(Query(text))


@pytest.mark.parametrize(
    ("number", "numeral"), [(1, "i"), (4, "iv"), (9, "ix"), (14, "xiv"), (21, "xxi")]
)
def test_roman(number, numeral):
    assert roman(number) == numeral


@pytest.mark.parametrize(
    "text", ["3 of cups", "3 cups", "cups 3", "three cups", "III of Cups", "cups three"]
)
def test_a_rank_can_be_a_digit_a_word_or_a_numeral_in_any_order(text):
    assert tier(THREE_OF_CUPS, text) in (EXACT, PREFIX, WORDS)


def test_a_digit_finds_its_own_number_only():
    assert tier(ACE_OF_CUPS, "1") == WORDS
    assert tier(MAGICIAN, "1") == WORDS
    assert tier(TEN_OF_SWORDS, "1") is None
    assert tier(WHEEL, "1") is None


@pytest.mark.parametrize(("card", "text"), [(TOWER, "16"), (TOWER, "XVI"), (FOOL, "0")])
def test_a_major_is_found_by_its_number(card, text):
    assert tier(card, text) == WORDS


@pytest.mark.parametrize(
    ("card", "text"),
    [
        (THREE_OF_CUPS, "3oC"),
        (THREE_OF_CUPS, "3c"),
        (QUEEN_OF_SWORDS, "QoS"),
        (QUEEN_OF_SWORDS, "qs"),
        (TEN_OF_SWORDS, "10S"),
        (ACE_OF_CUPS, "AoC"),
        (PAGE_OF_PENTACLES, "PoP"),
        (KNIGHT_OF_WANDS, "KnW"),
    ],
)
def test_shorthand_is_an_exact_match(card, text):
    assert tier(card, text) == EXACT


def test_shorthand_names_one_card():
    assert tier(QUEEN_OF_SWORDS, "3oC") is None
    assert tier(minor("king", "wands", "King"), "KnW") is None


def test_the_name_ranks_above_a_prefix_above_words():
    assert tier(FOOL, "the fool") == EXACT
    assert tier(FOOL, "fool") == EXACT
    assert tier(WHEEL, "wheel") == PREFIX
    assert tier(WHEEL, "fortune wheel") == WORDS


@pytest.mark.parametrize(
    ("card", "text"),
    [
        (PAGE_OF_PENTACLES, "coins"),
        (PAGE_OF_PENTACLES, "princess of disks"),
        (KNIGHT_OF_WANDS, "prince of rods"),
        (STRENGTH, "lust"),
        (THREE_OF_CUPS, "minor"),
        (QUEEN_OF_SWORDS, "court"),
        (TOWER, "rider"),
    ],
)
def test_synonyms_type_and_deck_rank_below_the_cards_own_words(card, text):
    assert tier(card, text) == SYNONYMS


def test_a_deck_alias_is_the_cards_own_word():
    card = dict(PAGE_OF_PENTACLES, display_suit="Coins", name="Page of Coins")
    assert tier(card, "coins page") == WORDS


def test_the_old_substring_match_still_finds_mid_word():
    assert tier(MAGICIAN, "agic") == SUBSTRING


def test_the_alone_still_finds_names_with_the():
    assert tier(FOOL, "the") == SUBSTRING
    assert tier(STRENGTH, "the") is None


def test_every_word_must_match():
    assert tier(THREE_OF_CUPS, "3 swords") is None
    assert tier(EMPRESS, "3 cups") is None


def test_an_empty_query_matches_everything():
    assert tier(TOWER, "") == EXACT
    assert tier(TOWER, "   ") == EXACT
