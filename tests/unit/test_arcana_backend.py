import logging
from pathlib import Path

import pytest

from tarot_canvas.models.deck_types import CardKind, DeckLink, DeckLoadError, DeckMetadata


def test_minimal_deck_loads_expected_cards(minimal_deck):
    cards = minimal_deck.cards

    assert len(cards) == 2
    assert {c.canonical_id for c in cards} == {"major_arcana.00", "major_arcana.01"}

    names = {c.canonical_id: c.display_name for c in cards}
    assert names["major_arcana.00"] == "The Fool"
    assert names["major_arcana.01"] == "The Magician"


def _write_deck(root, deck_toml, names=None, name_file="en.toml"):
    """A deck directory with one major arcanum and one minor, image-less."""
    (root / "h1200" / "major_arcana").mkdir(parents=True, exist_ok=True)
    (root / "h1200" / "minor_arcana" / "cups").mkdir(parents=True, exist_ok=True)
    (root / "deck.toml").write_text(deck_toml, encoding="utf-8")
    if names is not None:
        (root / "names").mkdir()
        (root / "names" / name_file).write_text(names, encoding="utf-8")
    from tarot_canvas.models.arcana_backend import load_deck

    return load_deck(str(root))


def test_metadata_drops_blank_tags_and_links_a_reader_must_not_follow(tmp_path):
    deck = _write_deck(
        tmp_path,
        """
        [deck]
        schema_version = "2.0"
        name = "Example Tarot"
        copyright = "Copyright (c) 2026 Jane Doe"
        published_date = "2020-05-04"
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
    deck = _write_deck(tmp_path, '[deck]\nschema_version = "2.0"\nname = ""\nversion = ""\n')
    assert deck.metadata == DeckMetadata(name="Unknown Deck", schema_version="2.0")


def test_a_suit_with_every_card_excluded_is_excluded(minimal_deck):
    assert [(suit.key, suit.excluded) for suit in minimal_deck.suits] == [
        ("wands", True),
        ("cups", True),
        ("swords", True),
        ("pentacles", True),
    ]
    assert minimal_deck.exclusion_reason.startswith("Test fixture")


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


def test_a_1_0_deck_reads_its_names_and_alt_text(minimal_v1_deck):
    by_id = {c.canonical_id: c for c in minimal_v1_deck.cards}
    assert set(by_id) == {"major_arcana.00", "minor_arcana.cups.ace"}
    assert by_id["major_arcana.00"].display_name == "The Fool"
    assert by_id["major_arcana.00"].alt_text == "Fixture alt text for the Fool."
    assert by_id["minor_arcana.cups.ace"].alt_text == "Fixture alt text for the Ace of Cups."
    assert minimal_v1_deck.metadata.artist == "Fixture Artist"


def test_a_1_0_website_is_not_also_a_homepage_link(minimal_v1_deck):
    assert minimal_v1_deck.metadata.website == "https://example.com/minimal-v1"
    assert minimal_v1_deck.metadata.links == ()


def test_a_deck_without_a_schema_version_raises_a_load_error(tmp_path):
    with pytest.raises(DeckLoadError) as raised:
        _write_deck(tmp_path, '[deck]\nname = "Old"\n')
    assert raised.value.code
    assert "schema_version" in raised.value.message


def test_a_major_has_no_suit_or_rank(minimal_deck):
    fool = minimal_deck.find_card("major_arcana.00")
    assert (fool.kind, fool.display_suit, fool.display_rank) == (CardKind.MAJOR, None, None)
    assert (fool.number, fool.position) == ("0", 0)


def test_a_minor_names_its_suit_and_rank(full_deck):
    ace = full_deck.find_card("minor_arcana.cups.ace")
    assert (ace.suit_key, ace.rank_key) == ("cups", "ace")
    assert (ace.display_suit, ace.display_rank, ace.display_name) == ("Cups", "Ace", "Ace of Cups")
    assert full_deck.display_rank_name("queen") == "Queen"


def test_only_the_default_variants_raster_and_scalable_faces_are_kept(tmp_path):
    for folder, name in [
        ("h1200", "00.png"),
        ("h1200", "00.jupiter.png"),
        ("h750", "00.png"),
        ("ansi32", "00.ansi"),
        ("scalable", "01.svg"),
    ]:
        (tmp_path / folder / "major_arcana").mkdir(parents=True, exist_ok=True)
        (tmp_path / folder / "major_arcana" / name).write_bytes(b"")
    deck = _write_deck(tmp_path, '[deck]\nschema_version = "2.0"\nname = "Faces"\n')

    fool = deck.find_card("major_arcana.00")
    assert [(Path(i.path).relative_to(tmp_path), i.kind, i.height) for i in fool.images] == [
        (Path("h1200/major_arcana/00.png"), "raster", 1200),
        (Path("h750/major_arcana/00.png"), "raster", 750),
    ]
    magician = deck.find_card("major_arcana.01")
    assert [(i.kind, i.height) for i in magician.images] == [("scalable", None)]


def test_a_major_beyond_the_canonical_22_is_a_card(tmp_path):
    (tmp_path / "h1200" / "major_arcana").mkdir(parents=True)
    (tmp_path / "h1200" / "major_arcana" / "22.png").write_bytes(b"")
    deck = _write_deck(
        tmp_path,
        '[deck]\nschema_version = "2.0"\nname = "More"\n\n'
        '[cards."major_arcana.22"]\nname = "The Twenty-Second"\n',
    )
    extra = deck.find_card("major_arcana.22")
    assert (extra.kind, extra.display_name, extra.position) == (
        CardKind.MAJOR,
        "The Twenty-Second",
        22,
    )
    assert extra.default_image() == str(tmp_path / "h1200" / "major_arcana" / "22.png")
