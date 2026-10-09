import logging

import pytest

from tarot_canvas.models.esoterica import EsotericaManager
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.settings import set_esoterica_disabled

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


THREE_LINES = """
[card."major_arcana.00".passages]
text = "These are my notes for The Fool."
"""


def text_of(reading):
    (entry,) = reading.entries
    return entry.value


@pytest.fixture
def root(tmp_path):
    return tmp_path / "primary"


def test_a_file_needs_nothing_but_a_card_table(root):
    write(root, "my-notes.toml", THREE_LINES)

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00")

    assert text_of(reading) == "These are my notes for The Fool."
    assert reading.name == "my-notes"  # the filename stem
    assert reading.author is None


def test_meta_supplies_the_display_name_and_author(root):
    write(
        root,
        "book.toml",
        '[meta]\nname = "Example Book"\nauthor = "Jane Doe"\n' + THREE_LINES,
    )

    (reading,) = EsotericaManager([root]).read_card("major_arcana.00")

    assert (reading.name, reading.author) == ("Example Book", "Jane Doe")


def test_sources_are_found_in_subdirectories(root):
    write(root, "books/deep/nested.toml", THREE_LINES)

    assert EsotericaManager([root]).read_card("major_arcana.00")


def test_minor_arcana_is_one_key_not_a_path(root):
    write(root, "notes.toml", '[card."minor_arcana.wands.ace".passages]\ntext = "Fire."\n')

    (reading,) = EsotericaManager([root]).read_card("minor_arcana.wands.ace")

    assert text_of(reading) == "Fire."


def test_a_variant_suffix_is_discarded(root):
    write(root, "notes.toml", THREE_LINES)

    assert EsotericaManager([root]).read_card("major_arcana.00:two_women")


def test_every_source_with_the_card_renders_separately(root):
    write(root, "a.toml", THREE_LINES)
    write(root, "b.toml", '[card."major_arcana.00".passages]\ntext = "Another view."\n')

    readings = EsotericaManager([root]).read_card("major_arcana.00")

    assert [r.name for r in readings] == ["a", "b"]


def fool(text):
    return f'[card."major_arcana.00".passages]\ntext = "{text}"\n'


@pytest.fixture
def roots(tmp_path):
    """Shaped like the user's root, the shared one and a bundled one, in that order"""
    return [tmp_path / "user", tmp_path / "shared", tmp_path / "bundled"]


def test_an_earlier_root_shadows_the_same_identifier_whatever_the_filename(roots):
    user, _, bundled = roots
    mine = write(user, "my-copy.toml", fool("Mine."), identifier="land.arcana/book")
    write(bundled, "books/the-book-2014.toml", fool("Bundled."), identifier="land.arcana/book")
    manager = EsotericaManager(roots)

    assert [text_of(r) for r in manager.read_card("major_arcana.00")] == ["Mine."]
    assert manager.sources["land.arcana/book"]["root"] == user

    mine.unlink()
    manager.reload()

    assert [text_of(r) for r in manager.read_card("major_arcana.00")] == ["Bundled."]
    assert manager.sources["land.arcana/book"]["root"] == bundled


def test_different_identifiers_are_two_sources_even_with_the_same_path(root, tmp_path):
    shared = tmp_path / "shared"
    write(root, "notes.toml", THREE_LINES, identifier="me/notes")
    write(shared, "notes.toml", fool("Also me."), identifier="someone-else/notes")

    assert len(EsotericaManager([root, shared]).read_card("major_arcana.00")) == 2


def test_the_same_identifier_twice_in_one_root_reads_the_first_path_and_warns(root, caplog):
    first = write(root, "a.toml", fool("First."), identifier="me/notes")
    second = write(root, "b/notes.toml", fool("Second."), identifier="me/notes")

    with caplog.at_level(logging.WARNING):
        manager = EsotericaManager([root])

    assert [text_of(r) for r in manager.read_card("major_arcana.00")] == ["First."]
    (warning,) = (r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert str(first) in warning
    assert str(second) in warning


def test_a_source_with_no_identifier_is_not_read_and_says_why(root, caplog):
    path = write(root, "anonymous.toml", THREE_LINES, identifier=None)
    write(root, "blank.toml", THREE_LINES, identifier="  ")

    with caplog.at_level(logging.WARNING):
        manager = EsotericaManager([root])

    assert manager.sources == {}
    assert manager.read_card("major_arcana.00") == []
    assert not manager.has_sources()
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert str(path) in warnings[0]
    assert "[meta].identifier" in warnings[0]


def test_the_identifier_is_stripped(root):
    write(root, "notes.toml", THREE_LINES, identifier="  me/notes ")

    assert list(EsotericaManager([root]).sources) == ["me/notes"]


ADVICE = '[card."major_arcana.00".passages]\nadvice.work = "Work."\n'
SYMBOLS = '[card."major_arcana.00".symbols.dog]\ntext = "The dog."\n'


def test_disabling_a_source_hides_it_at_once_and_enabling_brings_it_back(root):
    write(root, "a.toml", ADVICE, identifier="a")
    write(root, "b.toml", SYMBOLS, identifier="b")
    manager = EsotericaManager([root])

    set_esoterica_disabled(["b"])

    assert [r.name for r in manager.read_card("major_arcana.00")] == ["a"]
    assert manager.families_present() == {"advice"}
    assert set(manager.sources) == {"a", "b"}

    set_esoterica_disabled([])

    assert [r.name for r in manager.read_card("major_arcana.00")] == ["a", "b"]
    assert manager.families_present() == {"advice", "symbols"}


def test_with_every_source_disabled_there_are_sources_but_none_enabled(root):
    write(root, "a.toml", ADVICE, identifier="a")
    manager = EsotericaManager([root])
    assert manager.has_enabled_sources()

    set_esoterica_disabled(["a"])

    assert manager.has_sources()
    assert not manager.has_enabled_sources()
    assert manager.read_card("major_arcana.00") == []
    assert manager.families_present() == frozenset()


def test_an_unknown_identifier_in_the_disabled_list_is_harmless(root):
    write(root, "a.toml", ADVICE, identifier="a")
    manager = EsotericaManager([root])

    set_esoterica_disabled(["x/from-another-machine"])

    assert manager.has_enabled_sources()
    assert [r.name for r in manager.read_card("major_arcana.00")] == ["a"]


def test_reload_finds_a_new_file_and_says_so_once(root, qtbot):
    write(root, "a.toml", ADVICE, identifier="a")
    manager = EsotericaManager([root])
    write(root, "b.toml", SYMBOLS, identifier="b")
    emitted = []
    connection = esoterica_events().sources_changed.connect(lambda: emitted.append(True))

    try:
        with qtbot.waitSignal(esoterica_events().sources_changed, timeout=1000):
            manager.reload()
    finally:
        esoterica_events().sources_changed.disconnect(connection)

    assert emitted == [True]
    assert set(manager.sources) == {"a", "b"}
    assert manager.families_present() == {"advice", "symbols"}


def test_a_card_nobody_wrote_about_has_no_readings(root):
    write(root, "source.toml", THREE_LINES)

    assert EsotericaManager([root]).read_card("major_arcana.21") == []


def test_a_missing_root_is_not_an_error(tmp_path):
    assert EsotericaManager([tmp_path / "gone", tmp_path / "also-gone"]).sources == {}


def test_an_empty_root_has_no_sources(root):
    assert not EsotericaManager([root]).has_sources()


def test_one_readable_file_is_a_source(root):
    write(root, "my-notes.toml", THREE_LINES)

    assert EsotericaManager([root]).has_sources()


def test_a_file_in_the_older_format_is_not_a_source(root):
    write(root, "old.toml", '[meta]\nid = "old-notes"\n\n[passages]\ntext = "Old."\n')

    assert not EsotericaManager([root]).has_sources()


# [meta].related

FOOL = '[card."major_arcana.00".passages]\ntext = "The Fool."\n'


def relations(root, related, extra=""):
    write(root, "a.toml", f"[meta]\n{extra}related = {related}\n{FOOL}", identifier="a")
    source = EsotericaManager([root]).sources["a"]
    return source["pattern"], source["about"]


def related_warnings(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "[meta].related" in r.getMessage()
    ]


def test_a_source_without_related_has_no_pattern_and_is_about_nothing(root):
    write(root, "a.toml", FOOL, identifier="a")
    source = EsotericaManager([root]).sources["a"]

    assert (source["pattern"], source["about"]) == (None, frozenset())


def test_related_gives_the_pattern_and_every_about_target(root, caplog):
    with caplog.at_level(logging.WARNING):
        found = relations(
            root,
            '[{ rel = "pattern", target = "x/pattern/a" },'
            ' { rel = "about", target = "x/deck/b" },'
            ' { rel = "about", target = "x/pattern/c" },'
            ' { rel = "seating", target = "x/deck/d" }]',
        )

    assert found == ("x/pattern/a", frozenset({"x/deck/b", "x/pattern/c"}))
    assert related_warnings(caplog) == []


def test_related_that_is_not_an_array_is_not_read_and_says_so(root, caplog):
    with caplog.at_level(logging.WARNING):
        found = relations(root, '"x/pattern/a"')

    assert found == (None, frozenset())
    (warning,) = related_warnings(caplog)
    assert "a.toml" in warning


@pytest.mark.parametrize(
    "entry",
    ['"x/pattern/a"', '{ rel = "pattern" }', '{ rel = "pattern", target = "" }', "3"],
)
def test_a_malformed_entry_is_skipped_with_a_warning(root, caplog, entry):
    with caplog.at_level(logging.WARNING):
        found = relations(root, f'[{entry}, {{ rel = "about", target = "x/deck/b" }}]')

    assert found == (None, frozenset({"x/deck/b"}))
    (warning,) = related_warnings(caplog)
    assert "a.toml" in warning


def test_two_patterns_are_read_as_none_and_warned_about(root, caplog):
    with caplog.at_level(logging.WARNING):
        found = relations(
            root,
            '[{ rel = "pattern", target = "x/pattern/a" },'
            ' { rel = "pattern", target = "x/pattern/b" }]',
        )

    assert found == (None, frozenset())
    (warning,) = related_warnings(caplog)
    assert "more than one pattern" in warning


def test_an_overlay_ignores_related(root, caplog):
    with caplog.at_level(logging.WARNING):
        found = relations(
            root,
            '[{ rel = "pattern", target = "x/pattern/a" }, "malformed"]',
            extra='translates = "x/esoterica/original"\n',
        )

    assert found == (None, frozenset())
    assert related_warnings(caplog) == []
