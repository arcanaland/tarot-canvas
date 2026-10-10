import logging

import pytest


def test_minimal_deck_loads_expected_cards(minimal_deck):
    cards = minimal_deck.get_all_cards()

    assert len(cards) == 2
    assert {c["id"] for c in cards} == {"major_arcana.00", "major_arcana.01"}

    names = {c["id"]: c["name"] for c in cards}
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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "Le Mat"
    assert by_id["major_arcana.00"]["alt_text"] == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"]["name"] == "As de Coupe"
    # A card the table does not name still composes from suit and rank.
    assert by_id["minor_arcana.cups.two"]["name"] == "Two of Cups"


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "The Fool"


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "The Fool"
    assert by_id["major_arcana.00"]["alt_text"] == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"]["name"] == "Ace of Chalices"


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "The Fool"
    assert by_id["major_arcana.00"]["alt_text"] == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"]["alt_text"] == "A hand holds a cup."


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "The Fool"
    assert by_id["major_arcana.00"]["alt_text"] == "A wanderer at a cliff edge."
    assert by_id["minor_arcana.cups.ace"]["name"] == "Ace of Chalices"


def test_artist_is_read_as_the_author_in_2_0(tmp_path):
    """2.0 renamed author to artist ."""
    from tarot_canvas.ui.library.deck_model import deck_author

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
    assert deck.get_author() == "Jane Doe"
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
    assert deck.get_identifier() == "land.arcana/deck/aquatic-tarot"
    assert deck.get_deck_id() is None


def test_a_1_0_deck_has_an_id_and_no_identifier(tmp_path):
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
    assert deck.get_deck_id() == "rider-waite-smith"
    assert deck.get_identifier() is None


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "The Fool"
    assert by_id["major_arcana.13"]["name"] == "Death"
    assert by_id["major_arcana.21"]["name"] == "The World"
    assert by_id["minor_arcana.cups.ace"]["name"] == "Ace of Cups"


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["name"] == "Le Mat"
    assert by_id["major_arcana.01"]["name"] == "The Magician"  # still canonical


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.13"]["name"] != "Death"
    assert by_id["major_arcana.13"]["name"] == "XIII"
    # A declared number is the better label for an untitled face.
    assert by_id["major_arcana.04"]["name"] == "IIII"


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.09"]["numeral"] == "VIIII"
    assert by_id["major_arcana.00"]["numeral"] is None
    assert by_id["major_arcana.01"]["numeral"] is None
    assert by_id["major_arcana.14"]["numeral"] == "XIV"
    assert by_id["major_arcana.04"]["numeral"] == "IV"
    # The number stays the slot
    assert by_id["major_arcana.09"]["number"] == 9


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.00"]["numeral"] == "0"


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
    by_id = {c["id"]: c for c in deck.get_all_cards()}
    assert by_id["major_arcana.13"]["name"] == "Time"


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
    assert _write_deck(tmp_path, toml).get_pattern() == pattern


def test_two_patterns_are_read_as_none_and_warned_about_once(tmp_path, caplog):
    toml = PATTERN_DECK + (
        'related = [{ rel = "pattern", target = "x/pattern/a" },'
        ' { rel = "pattern", target = "x/pattern/b" }]\n'
    )
    with caplog.at_level(logging.WARNING):
        deck = _write_deck(tmp_path, toml)
        deck.get_pattern()

    assert deck.get_pattern() is None
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len([w for w in warnings if "more than one pattern" in w]) == 1
