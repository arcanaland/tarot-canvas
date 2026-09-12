import pytest

from tarot_canvas.models import deck_manager as deck_manager_module
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.deck_manager import DeckManager
from tarot_canvas.models.reference_deck import ReferenceDeck


def write_deck(root, name):
    path = root / name
    path.mkdir(parents=True)
    (path / "deck.toml").write_text(f'[deck]\nname = "{name}"\nversion = "1.0"\n')
    return path


@pytest.fixture
def root(tmp_path, monkeypatch):
    decks = tmp_path / "decks"
    monkeypatch.setattr(deck_manager_module, "get_decks_directory", lambda: [decks])
    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: False))
    return decks


def test_rescan_picks_up_an_added_deck_and_drops_a_removed_one(root):
    manager = DeckManager()
    write_deck(root, "Aquatic")
    assert manager.get_deck_names() == []

    manager.rescan()
    assert manager.get_deck_names() == ["Aquatic"]

    (root / "Aquatic" / "deck.toml").unlink()
    (root / "Aquatic").rmdir()
    manager.rescan()
    assert manager.get_deck_names() == []


def test_rescan_emits_decks_changed_and_construction_does_not(root):
    fired = []
    deck_events().decks_changed.connect(lambda: fired.append(True))

    manager = DeckManager()
    assert fired == []

    manager.rescan()
    assert fired == [True]


def test_rescan_reloads_the_reference_deck(root, monkeypatch):
    manager = DeckManager()
    assert manager.get_reference_deck() is None

    reference = write_deck(root.parent / "reference", "Rider-Waite-Smith")
    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: True))
    monkeypatch.setattr(ReferenceDeck, "get_reference_deck_path", staticmethod(lambda: reference))
    manager.rescan()

    assert manager.get_reference_deck().get_name() == "Rider-Waite-Smith"
