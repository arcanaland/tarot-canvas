import logging

import pytest

from tarot_canvas.models.deck_types import Card, CardKind, DeckLink, DeckMetadata


def test_minimal_deck_loads_expected_cards(minimal_deck):
    cards = minimal_deck.cards

    assert len(cards) == 2
    assert {c.canonical_id for c in cards} == {"major_arcana.00", "major_arcana.01"}

    names = {c.canonical_id: c.display_name for c in cards}
    assert names["major_arcana.00"] == "The Fool"
    assert names["major_arcana.01"] == "The Magician"


def _write_deck(root, deck_toml, names=None, name_file="en.toml"):
    """A deck directory with one major arcanum and one minor, image-less."""
    (root / "h1200" / "major_arcana").mkdir(parents=True)
    (root / "h1200" / "minor_arcana" / "cups").mkdir(parents=True)
    (root / "deck.toml").write_text(deck_toml, encoding="utf-8")
    if names is not None:
        (root / "names").mkdir()
        (root / "names" / name_file).write_text(names, encoding="utf-8")
    from tarot_canvas.models.deck import TarotDeck

    return TarotDeck(str(root))


def test_cards_table_supplies_names_a_deck_prints_on_its_artwork(tmp_path):
    """Schema 2.0 source layer: `[cards]` names, with no name file at all."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Printed Names"
        version = "1.0"

        [cards."major_arcana.00"]
        name = "Le Mat"
        alt_text = "A wanderer at a cliff edge."

        [cards."minor_arcana.cups.ace"]
        name = "As de Coupe"
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "Le Mat"
    assert by_id["major_arcana.00"].alt_text == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"].display_name == "As de Coupe"
    # A card the table does not name still composes from suit and rank.
    assert by_id["minor_arcana.cups.two"].display_name == "Two of Cups"


def test_a_name_file_outranks_the_cards_table(tmp_path):
    """The translation catalogue wins over the source layer (deck spec 7.2)."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Both Layers"
        version = "1.0"

        [cards."major_arcana.00"]
        name = "Le Mat"
        """,
        names="""
        [name.card.major_arcana]
        00 = "The Fool"
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "The Fool"


def test_schema_2_0_name_files_nest_under_their_facet(tmp_path):
    """1.0's `[major_arcana]` is 2.0's `[name.card.major_arcana]`."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Faceted"
        version = "1.0"
        """,
        names="""
        [name.card.major_arcana]
        00 = "The Fool"

        [name.card.minor_arcana.cups]
        ace = "Ace of Chalices"

        [alt_text.card.major_arcana]
        00 = "A wanderer at a cliff edge."
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "The Fool"
    assert by_id["major_arcana.00"].alt_text == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"].display_name == "Ace of Chalices"


def test_a_2_0_name_file_with_only_alt_text_is_still_2_0(tmp_path):
    """The manifest's schema_version decides the shape, not a `[name]` table."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Names In The Manifest"
        version = "1.0"

        [cards."major_arcana.00"]
        name = "The Fool"
        """,
        names="""
        [metadata.alt_text]
        license = "MIT"

        [alt_text.card.major_arcana]
        00 = "A wanderer at a cliff edge."

        [alt_text.card.minor_arcana.cups]
        ace = "A hand holds a cup."
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "The Fool"
    assert by_id["major_arcana.00"].alt_text == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"].alt_text == "A hand holds a cup."


def test_schema_1_0_name_files_still_load(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "1.0"
        name = "Legacy"
        version = "1.0"
        """,
        names="""
        [major_arcana]
        00 = "The Fool"

        [minor_arcana.cups]
        ace = "Ace of Chalices"

        [alt_text.major_arcana]
        00 = "A wanderer at a cliff edge."
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "The Fool"
    assert by_id["major_arcana.00"].alt_text == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"].display_name == "Ace of Chalices"


def test_artist_is_read_as_the_author_in_2_0(tmp_path):
    """2.0 renamed author to artist ."""
    from tarot_canvas.ui.library.decks.model import deck_author

    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Renamed"
        version = "1.0"
        artist = "Jane Doe"
        """,
    )
    assert deck.metadata.artist == "Jane Doe"
    assert deck_author(deck) == "Jane Doe"


def test_identifier_is_read_from_a_2_0_deck(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        identifier = "land.arcana/deck/aquatic-tarot"
        name = "Aquatic Tarot"
        version = "2.0"
        """,
    )
    assert deck.metadata.identifier == "land.arcana/deck/aquatic-tarot"


def test_a_1_0_id_is_not_an_identifier(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "1.0"
        id = "rider-waite-smith"
        name = "Rider-Waite-Smith"
        version = "1.1"
        """,
    )
    assert deck.metadata.identifier is None


def test_a_1_0_author_is_the_artist(tmp_path):
    deck = _write_deck(tmp_path, '[deck]\nname = "Old"\nauthor = "Pamela Colman Smith"\n')
    assert deck.metadata.artist == "Pamela Colman Smith"


def test_a_2_0_deck_carries_what_libarcana_does_not_model_yet(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Example Tarot"
        copyright = "Copyright (c) 2026 Jane Doe"
        published_date = 2020-05-04
        tags = ["scenic", " ", "modern"]
        related = [{ rel = "pattern", target = "x/pattern/marseille" }]
        links = [
            { rel = "homepage", url = "https://example.com/" },
            { rel = "buy", url = " https://example.com/shop ", title = "Buy from the artist" },
            { rel = "artist", url = "ftp://example.com" },
            { url = "https://example.com/no-rel" },
        ]
        """,
    )
    metadata = deck.metadata
    assert metadata.copyright == "Copyright (c) 2026 Jane Doe"
    assert metadata.published_date == "2020-05-04"
    assert metadata.pattern == "x/pattern/marseille"
    assert metadata.tags == ("scenic", "modern")
    assert metadata.links == (
        DeckLink("homepage", "https://example.com/"),
        DeckLink("buy", "https://example.com/shop", "Buy from the artist"),
    )


def test_absent_fields_are_none_and_the_name_has_a_fallback(tmp_path):
    deck = _write_deck(tmp_path, '[deck]\nversion = ""\n')
    assert deck.metadata == DeckMetadata(name="Unknown Deck")


def test_a_suit_with_every_card_excluded_is_excluded(minimal_deck):
    assert [(suit.key, suit.excluded) for suit in minimal_deck.suits] == [
        ("wands", True),
        ("cups", True),
        ("swords", True),
        ("pentacles", True),
    ]
    assert minimal_deck.exclusion_reason.startswith("Test fixture")


def test_a_suit_is_named_by_its_alias(tmp_path):
    deck = _write_deck(tmp_path, '[deck]\nname = "A"\n\n[aliases.suits]\ncups = "Chalices"\n')
    names = {suit.key: suit.name for suit in deck.suits}
    assert names["cups"] == "Chalices"
    assert names["wands"] == "Wands"
    assert not any(suit.excluded for suit in deck.suits)


def test_canonical_majors_need_no_declaration(tmp_path):
    """Appendix C is the terminal step, so an RWS-seated deck restates nothing."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Bare"
        version = "1.0"
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "The Fool"
    assert by_id["major_arcana.13"].display_name == "Death"
    assert by_id["major_arcana.21"].display_name == "The World"
    assert by_id["minor_arcana.cups.ace"].display_name == "Ace of Cups"


def test_a_deck_name_outranks_the_canonical_one(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Own Words"
        version = "1.0"

        [cards]
        "major_arcana.00" = { name = "Le Mat" }
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].display_name == "Le Mat"
    assert by_id["major_arcana.01"].display_name == "The Magician"  # still canonical


def test_an_unnamed_face_is_not_given_a_canonical_name(tmp_path):
    """`unnamed` truncates the chain, so no later step may invent a name."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Untitled Death"
        version = "1.0"

        [cards]
        "major_arcana.13" = { unnamed = true }
        "major_arcana.04" = { unnamed = true, number = "IIII" }
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.13"].display_name != "Death"
    assert by_id["major_arcana.13"].display_name == "XIII"
    # A declared number is the better label for an untitled face.
    assert by_id["major_arcana.04"].display_name == "IIII"


def test_a_major_shows_the_numeral_its_face_prints(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Numerals"
        version = "1.0"

        [cards]
        "major_arcana.00" = { unnumbered = true }
        "major_arcana.01" = { unnumbered = true, number = "I" }
        "major_arcana.04" = { number = 4 }
        "major_arcana.09" = { number = "VIIII" }
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.09"].number == "VIIII"
    assert by_id["major_arcana.00"].number is None
    assert by_id["major_arcana.01"].number is None
    assert by_id["major_arcana.14"].number == "XIV"
    assert by_id["major_arcana.04"].number == "IV"
    # The number stays the slot
    assert by_id["major_arcana.09"].position == 9


def test_an_undeclared_zero_is_printed_as_zero(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Zero"
        version = "1.0"
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.00"].number == "0"


def test_a_supplied_name_is_used_where_the_face_prints_none(tmp_path):
    """A name the deck has from the booklet, not one invented for it."""
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Booklet"
        version = "1.0"

        [cards]
        "major_arcana.13" = { unnamed = true, supplied_name = { text = "Time", lang = "en", source = "booklet" } }
        """,
    )
    by_id = {c.canonical_id: c for c in deck.cards}
    assert by_id["major_arcana.13"].display_name == "Time"


PATTERN_DECK = """
[deck]
schema_version = "2.0"
name = "Patterned"
version = "1.0"
"""


@pytest.mark.parametrize(
    ("related", "pattern"),
    [
        ('[{ rel = "pattern", target = "x/pattern/a" }]', "x/pattern/a"),
        (
            '[{ rel = "about", target = "x/deck/b" }, { rel = "pattern", target = "x/pattern/a" }]',
            "x/pattern/a",
        ),
        (None, None),
        ('"x/pattern/a"', None),
        ('["x/pattern/a"]', None),
        ('[{ rel = "pattern" }]', None),
        ('[{ rel = "pattern", target = "" }]', None),
        ('[{ rel = "pattern", target = 3 }]', None),
        ('[{ rel = "companion", target = "x/deck/b" }]', None),
    ],
)
def test_the_pattern_is_the_target_of_the_one_pattern_relation(tmp_path, related, pattern):
    toml = PATTERN_DECK + (f"related = {related}\n" if related is not None else "")
    assert _write_deck(tmp_path, toml).metadata.pattern == pattern


def test_two_patterns_are_read_as_none_and_warned_about_once(tmp_path, caplog):
    toml = PATTERN_DECK + (
        'related = [{ rel = "pattern", target = "x/pattern/a" },'
        ' { rel = "pattern", target = "x/pattern/b" }]\n'
    )
    with caplog.at_level(logging.WARNING):
        deck = _write_deck(tmp_path, toml)

    assert deck.metadata.pattern is None
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len([w for w in warnings if "more than one pattern" in w]) == 1


def test_suits_come_in_canonical_order_not_alphabetical(full_deck):
    assert [suit.key for suit in full_deck.suits] == ["wands", "cups", "swords", "pentacles"]


def test_a_suit_outside_the_canonical_four_comes_last(full_deck):
    cards = full_deck.cards
    first_sword = next(i for i, card in enumerate(cards) if card.suit_key == "swords")
    star = Card(
        canonical_id="minor_arcana.stars.ace",
        kind=CardKind.MINOR,
        display_name="Ace of Stars",
        suit_key="stars",
        rank_key="ace",
    )
    full_deck._cards = (*cards[:first_sword], star, *cards[first_sword:])

    assert [suit.key for suit in full_deck.suits] == [
        "wands",
        "cups",
        "swords",
        "pentacles",
        "stars",
    ]
