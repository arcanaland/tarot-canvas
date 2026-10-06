import tomllib

import pytest

from tarot_canvas.models.esoterica import (
    Entry,
    EsotericaManager,
    _flatten,
    groups_for,
)
from tarot_canvas.models.esoterica_registry import Role


def write(root, relative_path, text):
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def root(tmp_path):
    return tmp_path / "primary"


def keys(entries):
    return [entry.key for entry in entries]


# Flattening


def test_entries_come_back_in_registry_order_whatever_the_file_order():
    target = tomllib.loads(
        """
        [passages]
        shadow = "s"
        keywords = ["k"]
        symbols.b = "b"
        light = "l"
        symbols.a = "a"
        advice.timing = "t"
        advice.work = "w"
        """
    )

    entries = _flatten(target)

    assert keys(entries) == [
        "keywords",
        "light",
        "shadow",
        "advice.work",
        "symbols.b",
        "symbols.a",
        "advice.timing",
    ]


def test_arrays_come_back_as_tuples():
    target = tomllib.loads('passages.keywords = ["a", "b"]\ncorrespondences.color = ["red", 1]')

    assert [entry.value for entry in _flatten(target)] == [("a", "b"), ("red", 1)]


def test_values_of_the_wrong_type_are_skipped():
    target = tomllib.loads(
        """
        [passages]
        text = 3
        light = ""
        shadow = []
        keywords = ["fine", 2]
        questions = ["fine", ""]
        theme = "kept"

        [correspondences]
        number = 4
        element = ""
        color = []
        x_born = 1979-05-27
        planet = [1, "mars", true, 2.5]
        """
    )

    assert keys(_flatten(target)) == ["theme", "number", "planet"]


def test_correspondences_keep_their_toml_types():
    target = tomllib.loads(
        "[correspondences]\nnumber = 0\nhebrew_letter_value = 1.5\nx_reversible = true\n"
    )

    assert [entry.value for entry in _flatten(target)] == [0, 1.5, True]


# Membership


def test_a_major_is_in_the_major_arcana_and_all():
    assert groups_for("major_arcana.13") == ("arcana.major", "all")


def test_a_court_card_is_in_its_suit_rank_and_class_narrowest_first():
    assert groups_for("minor_arcana.cups.queen") == (
        "suits.cups",
        "ranks.queen",
        "classes.court",
        "arcana.minor",
        "all",
    )


def test_an_ace_is_a_pip():
    groups = groups_for("minor_arcana.wands.ace")

    assert "classes.pip" in groups
    assert "classes.court" not in groups


def test_a_custom_rank_is_in_neither_class():
    assert groups_for("minor_arcana.cups.princess") == (
        "suits.cups",
        "ranks.princess",
        "arcana.minor",
        "all",
    )


CUSTOM_GROUP = """
[card."major_arcana.00".passages]
text = "Fool."

[group.custom.lunar]
cards = ["major_arcana.18", "minor_arcana.cups.queen"]

[group.custom.lunar.passages]
text = "A lunar sequence."
"""


def test_a_custom_group_applies_only_to_its_listed_cards(root):
    write(root, "book.toml", CUSTOM_GROUP)
    manager = EsotericaManager([root])

    (moon,) = manager.read_card("major_arcana.18")
    (fool,) = manager.read_card("major_arcana.00")

    assert [(g.group, g.family) for g in moon.groups] == [("custom.lunar", "custom")]
    assert fool.groups == ()


def test_a_custom_group_does_not_reach_into_another_source(root):
    write(root, "a.toml", CUSTOM_GROUP)
    write(
        root,
        "b.toml",
        """
        [card."major_arcana.18".passages]
        text = "Moon."

        [group.custom.lunar]
        cards = ["major_arcana.00"]

        [group.custom.lunar.passages]
        text = "A different group that shares a name."
        """,
    )

    a, b = EsotericaManager([root]).read_card("major_arcana.18")

    assert [g.group for g in a.groups] == ["custom.lunar"]
    assert b.groups == ()


# Reading a card

COURT_CARD = """
[meta]
name = "A Structured Book"
author = "Jane Doe"

[card."minor_arcana.cups.queen".passages]
x_mood = "An entry the registry has never heard of."
shadow = "Drowning in other people."
keywords = ["empathy", "intuition"]
personality = "Feels first."
light = "Holds space."
questions = ["What do you feel?", "Whose feeling is it?"]
advice.work = "Listen."
advice.relationships = "Listen harder."
advice.fortune_telling = "A woman with water signs."
symbols.cup = "Closed, ornate."
symbols.shore = "Between land and sea."

[card."minor_arcana.cups.queen".correspondences]
x_hebrew_letter_alt = "heh"
element = "water"
hebrew_letter_value = 5

[group.suits.cups.passages]
text = "Feeling."

[group.classes.court.passages]
theme = "People."

[group.classes.pip.passages]
theme = "Numbers."
"""


@pytest.fixture
def court(root):
    write(root, "book.toml", COURT_CARD)
    (reading,) = EsotericaManager([root]).read_card("minor_arcana.cups.queen")
    return reading


def test_a_card_reads_every_entry_in_registry_order(court):
    assert keys(court.entries) == [
        "keywords",
        "light",
        "shadow",
        "personality",
        "questions",
        "advice.relationships",
        "advice.work",
        "symbols.cup",
        "symbols.shore",
        "advice.fortune_telling",
        "element",
        "hebrew_letter_value",
        "x_hebrew_letter_alt",
        "x_mood",
    ]
    assert court.entries[0] == Entry(
        "passages", "keywords", Role.KEYWORDS, ("empathy", "intuition")
    )
    assert (court.name, court.author) == ("A Structured Book", "Jane Doe")


def test_an_unknown_key_is_kept_with_no_role_and_last(court):
    last = court.entries[-1]

    assert (last.key, last.role) == ("x_mood", None)


def test_a_card_gets_the_groups_it_is_in_narrowest_first(court):
    assert [(g.group, g.family) for g in court.groups] == [
        ("suits.cups", "suits"),
        ("classes.court", "classes"),
    ]
    assert court.groups[0].entries == (Entry("passages", "text", Role.PRINCIPAL, "Feeling."),)


def test_a_text_only_source_reads_as_one_principal_entry(root):
    write(root, "notes.toml", '[card."major_arcana.00".passages]\ntext = "Mine."\n')

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00")

    assert reading.entries == (Entry("passages", "text", Role.PRINCIPAL, "Mine."),)
    assert reading.groups == ()
    assert (reading.name, reading.author) == ("notes", None)


def test_sources_come_back_in_load_order_on_every_card(root):
    both = """
    [card."major_arcana.00".passages]
    text = "x"
    [card."major_arcana.01".passages]
    text = "y"
    """
    write(root, "b.toml", both)
    write(root, "a.toml", both)
    manager = EsotericaManager([root])

    assert [r.name for r in manager.read_card("major_arcana.00")] == ["a", "b"]
    assert [r.name for r in manager.read_card("major_arcana.01")] == ["a", "b"]


def test_an_annotating_source_is_credited_to_the_annotator(root):
    write(
        root,
        "notes.toml",
        """
        [meta]
        name = "Notes on a Classic"
        author = "The Annotator"
        relation = "annotates"

        [meta.work]
        title = "A Classic"
        author = "The Original Author"

        [card."major_arcana.00".passages]
        symbols.dog = "The dog."
        """,
    )

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00")

    assert reading.author == "The Annotator"


def test_group_content_alone_is_enough_to_read_a_card(root):
    write(
        root,
        "book.toml",
        """
        [card."major_arcana.00".passages]
        text = "Fool."

        [group.arcana.minor.passages]
        theme = "Everyday life."
        """,
    )

    (reading,) = EsotericaManager([root]).read_card("minor_arcana.swords.two")

    assert reading.entries == ()
    assert [g.group for g in reading.groups] == ["arcana.minor"]


def test_a_source_with_only_unknown_keys_for_a_card_is_not_a_reading(root):
    write(
        root,
        "book.toml",
        """
        [card."major_arcana.00".passages]
        x_mood = "Unregistered."

        [group.all.passages]
        x_mood = "Also unregistered."
        """,
    )

    assert EsotericaManager([root]).read_card("major_arcana.00") == []


def test_group_all_and_qualified_identifier_groups(root):
    write(
        root,
        "book.toml",
        """
        [card."major_arcana.00".passages]
        text = "Fool."

        [group.all.passages]
        text = "Every card."

        [group."land.arcana/spread/celtic-cross#challenge".passages]
        text = "Ignored for now."
        """,
    )

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00")

    assert [(g.group, g.family) for g in reading.groups] == [("all", "all")]


def test_reading_a_variant_reads_the_canonical_card(root):
    write(root, "notes.toml", '[card."major_arcana.00".passages]\ntext = "Mine."\n')

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00:alt")

    assert reading.entries[0].value == "Mine."


def test_a_card_no_source_mentions_reads_as_nothing(root):
    write(root, "notes.toml", '[card."major_arcana.00".passages]\ntext = "Mine."\n')

    assert EsotericaManager([root]).read_card("major_arcana.01") == []
