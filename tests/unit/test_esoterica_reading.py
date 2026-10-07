import logging
import tomllib

import pytest

from tarot_canvas.models.esoterica import (
    Entry,
    EsotericaManager,
    _flatten,
    groups_for,
)
from tarot_canvas.models.esoterica_registry import PASSAGES, SYMBOLS, Role

FROM_PATH = object()


def write(root, relative_path, text, identifier=FROM_PATH):
    """A source file. Only a source with an identifier is read, so each gets one from its
    path unless the test names one, or passes None for a file without"""
    if identifier is FROM_PATH:
        identifier = f"test/{relative_path}"
    if identifier is not None:
        line = f'identifier = "{identifier}"'
        if "[meta]" in text:
            text = text.replace("[meta]", f"[meta]\n{line}", 1)
        else:
            text = f"[meta]\n{line}\n{text}"
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
        [symbols]
        b.text = "b"
        a.text = "a"

        [passages]
        shadow = "s"
        keywords = ["k"]
        light = "l"
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
        "b",
        "a",
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


# The symbols slot


def test_each_symbol_is_one_entry_in_file_order_with_its_printed_heading():
    target = tomllib.loads(
        """
        [symbols.the_sun]
        label = "The Sun"
        text = "Warmth."

        [symbols.a_dog]
        text = "Loyalty."
        """
    )

    assert _flatten(target) == (
        Entry(SYMBOLS, "the_sun", Role.SYMBOLS, "Warmth.", "The Sun"),
        Entry(SYMBOLS, "a_dog", Role.SYMBOLS, "Loyalty."),
    )
    assert _flatten(target)[1].label is None


def test_a_symbol_without_text_or_that_is_not_a_table_is_skipped():
    target = tomllib.loads(
        """
        [symbols]
        loose = "Not a table."
        untitled = { label = "No text" }
        blank = { text = "  " }
        listed = { text = ["Not", "a string"] }
        kept = { text = "Kept.", x_other = "ignored" }
        """
    )

    assert keys(_flatten(target)) == ["kept"]


@pytest.mark.parametrize("label", ['""', '"  "', "3", '["The Sun"]'])
def test_a_blank_or_non_string_label_is_no_label(label):
    target = tomllib.loads(f'symbols.sun = {{ text = "Warmth.", label = {label} }}')

    (entry,) = _flatten(target)
    assert entry.label is None


def test_the_marseille_image_is_a_symbol_and_sorts_after_the_symbols():
    target = tomllib.loads(
        """
        [passages]
        x_marseille_image = "Two batons."
        advice.fortune_telling = "Soon."

        [symbols.globe]
        text = "The world."
        """
    )

    entries = _flatten(target)

    assert keys(entries) == ["globe", "x_marseille_image", "advice.fortune_telling"]
    assert entries[1] == Entry(PASSAGES, "x_marseille_image", Role.SYMBOLS, "Two batons.")


LEGACY_SYMBOLS = """
[card."major_arcana.00".passages]
text = "Fool."
symbols.dog = "The dog."

[card."major_arcana.01".passages]
symbols.wand = "The wand."

[group.all.passages]
symbols.sky = "The sky."
"""


def test_the_draft_spelling_of_symbols_is_not_read(root):
    write(root, "book.toml", LEGACY_SYMBOLS)
    manager = EsotericaManager([root])

    (fool,) = manager.read_card("major_arcana.00")

    assert keys(fool.entries) == ["text"]
    assert fool.groups == ()
    assert manager.read_card("major_arcana.01") == []
    assert manager.families_present() == frozenset()


def test_the_draft_spelling_warns_once_per_file(root, caplog):
    write(root, "a.toml", LEGACY_SYMBOLS)
    write(root, "b.toml", LEGACY_SYMBOLS)
    write(root, "c.toml", '[card."major_arcana.00".symbols.dog]\ntext = "The dog."\n')

    with caplog.at_level(logging.WARNING):
        EsotericaManager([root])

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert [w.split(":")[0] for w in warnings] == [str(root / "a.toml"), str(root / "b.toml")]
    assert all("symbols.<name>" in w for w in warnings)


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

[card."minor_arcana.cups.queen".symbols]
cup = { text = "Closed, ornate.", label = "The Cup" }
shore = { text = "Between land and sea." }

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
        "cup",
        "shore",
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
    assert [(e.slot, e.role, e.label) for e in court.entries if e.slot == SYMBOLS] == [
        (SYMBOLS, Role.SYMBOLS, "The Cup"),
        (SYMBOLS, Role.SYMBOLS, None),
    ]


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

        [card."major_arcana.00".symbols.dog]
        text = "The dog."
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


# The families the show menu can offer


def test_an_essay_source_has_no_families(root):
    write(root, "a.toml", '[card."major_arcana.00".passages]\ntext = "Prose."\n')

    assert EsotericaManager([root]).families_present() == frozenset()


def test_families_are_found_on_any_card_and_in_any_group(root):
    write(
        root,
        "a.toml",
        """
        [card."major_arcana.00".passages]
        advice.work = "Work."
        [card."minor_arcana.cups.two".correspondences]
        element = "water"
        [group.ranks.queen.passages]
        advice.timing = "Soon."
        """,
    )
    write(
        root,
        "b.toml",
        """
        [card."major_arcana.18".passages]
        text = "Prose."
        [group.custom.lunar]
        cards = ["major_arcana.18"]
        symbols.moon.text = "The moon."
        """,
    )

    assert EsotericaManager([root]).families_present() == {
        "advice",
        "correspondences",
        "divinatory",
        "symbols",
        "groups",
    }


def test_a_source_with_only_symbols_has_the_symbols_family(root):
    write(root, "a.toml", '[card."major_arcana.00".symbols.dog]\ntext = "The dog."\n')

    assert EsotericaManager([root]).families_present() == {"symbols"}


def test_a_group_can_have_symbols(root):
    write(
        root,
        "a.toml",
        """
        [card."major_arcana.00".passages]
        text = "Fool."

        [group.arcana.major.symbols.crown]
        label = "The Crown"
        text = "Rule."
        """,
    )

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00")

    (group,) = reading.groups
    assert group.group == "arcana.major"
    assert group.entries == (Entry(SYMBOLS, "crown", Role.SYMBOLS, "Rule.", "The Crown"),)


def test_a_group_with_nothing_renderable_is_not_a_family(root):
    write(
        root,
        "a.toml",
        '[card."major_arcana.00".passages]\ntext = "Prose."\n'
        '[group.all.passages]\nx_unknown = "Only this."\n',
    )

    manager = EsotericaManager([root])
    assert manager.has_sources()
    assert manager.families_present() == frozenset()
