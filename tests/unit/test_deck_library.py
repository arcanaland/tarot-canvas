import logging

import pytest

from tarot_canvas.models import deck_library as deck_library_module
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.deck_library import DeckLibrary
from tarot_canvas.models.reference_deck import ReferenceDeck


def write_deck(root, directory, name=None, identifier=None):
    path = root / directory
    path.mkdir(parents=True)
    toml = f'[deck]\nname = "{name or directory}"\nversion = "1.0"\n'
    if identifier is not None:
        toml += f'identifier = "{identifier}"\n'
    (path / "deck.toml").write_text(toml)
    return path


def names(library):
    return [deck.metadata.name for deck in library.decks()]


@pytest.fixture
def root(tmp_path, monkeypatch):
    decks = tmp_path / "decks"
    monkeypatch.setattr(deck_library_module, "get_decks_directory", lambda: [decks])
    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: False))
    return decks


def test_rescan_picks_up_an_added_deck_and_drops_a_removed_one(root):
    library = DeckLibrary()
    write_deck(root, "Aquatic")
    assert names(library) == []

    library.rescan()
    assert names(library) == ["Aquatic"]

    (root / "Aquatic" / "deck.toml").unlink()
    (root / "Aquatic").rmdir()
    library.rescan()
    assert names(library) == []


def test_rescan_emits_decks_changed_and_construction_does_not(root):
    fired = []
    deck_events().decks_changed.connect(lambda: fired.append(True))

    library = DeckLibrary()
    assert fired == []

    library.rescan()
    assert fired == [True]


def test_rescan_reloads_the_reference_deck(root, monkeypatch):
    library = DeckLibrary()
    assert library.reference() is None

    reference = write_deck(root.parent / "reference", "Rider-Waite-Smith")
    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: True))
    monkeypatch.setattr(ReferenceDeck, "get_reference_deck_path", staticmethod(lambda: reference))
    library.rescan()

    assert library.reference().metadata.name == "Rider-Waite-Smith"


def test_two_decks_with_the_same_name_are_both_listed(root):
    write_deck(root, "lotus", name="Lotus")
    write_deck(root, "lotus.bak", name="Lotus")

    assert names(DeckLibrary()) == ["Lotus", "Lotus"]


def test_two_decks_with_the_same_identifier_are_both_listed_and_warned_about(root, caplog):
    first = write_deck(root, "lotus", identifier="x/deck/lotus")
    second = write_deck(root, "lotus.bak", identifier="x/deck/lotus")

    with caplog.at_level(logging.WARNING):
        library = DeckLibrary()

    assert len(library.find_by_identifier("x/deck/lotus")) == 2
    warnings = [r.getMessage() for r in caplog.records if "share the identifier" in r.getMessage()]
    assert len(warnings) == 1
    assert str(first) in warnings[0] and str(second) in warnings[0]


def test_loading_a_path_twice_gives_the_same_deck(root):
    path = write_deck(root, "Aquatic")
    library = DeckLibrary()

    assert library.load(path) is library.load(str(path))
    assert library.load(path) is library.decks()[0]


def test_loading_a_symlink_gives_the_deck_it_points_at(root, tmp_path):
    path = write_deck(root, "Aquatic")
    link = tmp_path / "link"
    link.symlink_to(path)
    library = DeckLibrary()

    assert library.load(link) is library.load(path)


def test_rescan_builds_new_decks(root):
    path = write_deck(root, "Aquatic")
    library = DeckLibrary()
    before = library.load(path)

    library.rescan()

    assert library.load(path) is not before
