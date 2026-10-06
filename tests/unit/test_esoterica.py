import pytest

from tarot_canvas.models.esoterica import EsotericaManager


def write(root, relative_path, text):
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


def test_the_first_root_wins_for_the_same_relative_path(root, tmp_path):
    shared = tmp_path / "shared"
    write(root, "notes.toml", THREE_LINES)
    write(shared, "notes.toml", '[card."major_arcana.00".passages]\ntext = "Shadowed."\n')

    readings = EsotericaManager([root, shared]).read_card("major_arcana.00")

    assert [text_of(r) for r in readings] == ["These are my notes for The Fool."]


def test_the_same_name_under_different_paths_is_two_sources(root, tmp_path):
    shared = tmp_path / "shared"
    write(root, "notes.toml", THREE_LINES)
    write(shared, "books/notes.toml", '[card."major_arcana.00".passages]\ntext = "Also me."\n')

    assert len(EsotericaManager([root, shared]).read_card("major_arcana.00")) == 2


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
