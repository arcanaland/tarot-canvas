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


@pytest.fixture
def root(tmp_path):
    return tmp_path / "primary"


def test_a_file_needs_nothing_but_a_card_table(root):
    write(root, "my-notes.toml", THREE_LINES)

    (passage,) = EsotericaManager([root]).get_passages_for_card("major_arcana.00")

    assert passage.text == "These are my notes for The Fool."
    assert passage.source_name == "my-notes"  # the filename stem
    assert passage.author is None


def test_meta_supplies_the_display_name_and_author(root):
    write(
        root,
        "book.toml",
        '[meta]\nname = "Tarot for Change"\nauthor = "Jessica Dore"\n' + THREE_LINES,
    )

    (passage,) = EsotericaManager([root]).get_passages_for_card("major_arcana.00")

    assert (passage.source_name, passage.author) == ("Tarot for Change", "Jessica Dore")


def test_sources_are_found_in_subdirectories(root):
    write(root, "books/deep/nested.toml", THREE_LINES)

    assert EsotericaManager([root]).get_passages_for_card("major_arcana.00")


def test_minor_arcana_is_one_key_not_a_path(root):
    write(root, "notes.toml", '[card."minor_arcana.wands.ace".passages]\ntext = "Fire."\n')

    (passage,) = EsotericaManager([root]).get_passages_for_card("minor_arcana.wands.ace")

    assert passage.text == "Fire."


def test_a_variant_suffix_is_discarded(root):
    write(root, "notes.toml", THREE_LINES)

    assert EsotericaManager([root]).get_passages_for_card("major_arcana.00:two_women")


def test_every_source_with_the_card_renders_separately(root):
    write(root, "a.toml", THREE_LINES)
    write(root, "b.toml", '[card."major_arcana.00".passages]\ntext = "Another view."\n')

    passages = EsotericaManager([root]).get_passages_for_card("major_arcana.00")

    assert [p.source_name for p in passages] == ["a", "b"]


def test_the_first_root_wins_for_the_same_relative_path(root, tmp_path):
    shared = tmp_path / "shared"
    write(root, "notes.toml", THREE_LINES)
    write(shared, "notes.toml", '[card."major_arcana.00".passages]\ntext = "Shadowed."\n')

    passages = EsotericaManager([root, shared]).get_passages_for_card("major_arcana.00")

    assert [p.text for p in passages] == ["These are my notes for The Fool."]


def test_the_same_name_under_different_paths_is_two_sources(root, tmp_path):
    shared = tmp_path / "shared"
    write(root, "notes.toml", THREE_LINES)
    write(shared, "books/notes.toml", '[card."major_arcana.00".passages]\ntext = "Also me."\n')

    assert len(EsotericaManager([root, shared]).get_passages_for_card("major_arcana.00")) == 2


@pytest.mark.parametrize(
    "content",
    [
        "not toml at all [[[",
        '[minor.arcana.cups.four]\ntext = "Bodhi tree."\n',  # holistic-tarot.toml
        '[meta]\nname = "Empty"\n',
        '[group.suits.wands.passages]\ntext = "Fire."\n',
    ],
)
def test_a_file_without_a_card_table_is_not_a_source(root, content):
    write(root, "not-a-source.toml", content)

    assert EsotericaManager([root]).sources == {}


def test_the_older_format_is_named_rather_than_silently_ignored(root, caplog):
    write(root, "old.toml", '[meta]\nid = "mine"\n\n[passages.major_arcana.00]\ntext = "Hi."\n')

    manager = EsotericaManager([root])

    assert manager.sources == {}
    assert "older esoterica format" in caplog.text


def test_an_unhandled_schema_major_is_skipped_loudly(root, caplog):
    write(root, "future.toml", '[meta]\nschema_version = "2.0"\n' + THREE_LINES)

    manager = EsotericaManager([root])

    assert manager.sources == {}
    assert "not supported" in caplog.text


def test_a_declared_1_x_schema_version_still_loads(root):
    write(root, "source.toml", '[meta]\nschema_version = "1.0"\n' + THREE_LINES)

    assert EsotericaManager([root]).get_passages_for_card("major_arcana.00")


def test_passage_keys_other_than_text_are_kept_but_not_rendered(root):
    write(
        root,
        "source.toml",
        '[card."major_arcana.00".passages]\ntext = "Body."\nreversed = "Upside down."\n'
        '\n[card."major_arcana.00".correspondences]\nelement = "air"\n',
    )

    manager = EsotericaManager([root])
    target = manager.sources["source.toml"]["cards"]["major_arcana.00"]

    assert target["passages"]["reversed"] == "Upside down."
    assert target["correspondences"] == {"element": "air"}
    assert [p.text for p in manager.get_passages_for_card("major_arcana.00")] == ["Body."]


def test_a_card_nobody_wrote_about_has_no_passages(root):
    write(root, "source.toml", THREE_LINES)

    assert EsotericaManager([root]).get_passages_for_card("major_arcana.21") == []


def test_a_missing_root_is_not_an_error(tmp_path):
    assert EsotericaManager([tmp_path / "gone", tmp_path / "also-gone"]).sources == {}
