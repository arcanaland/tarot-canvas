from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tests.conftest import MINIMAL_DECK_PATH


def open_card_view(qtbot, deck):
    card = next(c for c in deck.get_all_cards() if c.get("image"))
    tab = CardViewTab(card=card, deck=deck)
    qtbot.addWidget(tab)
    return tab


def test_opening_a_card_view_writes_nothing_to_the_notes_store(qtbot, notes_base):
    deck = TarotDeck(str(MINIMAL_DECK_PATH))

    open_card_view(qtbot, deck)

    assert not notes_base.exists()


def test_a_card_with_notes_lists_them_without_touching_other_cards(qtbot, notes_base):
    deck = TarotDeck(str(MINIMAL_DECK_PATH))
    card = next(c for c in deck.get_all_cards() if c.get("image"))

    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000_A_Note.md").write_text("# A Note\n\nbody\n", encoding="utf-8")

    tab = open_card_view(qtbot, deck)

    assert tab.notes_tab.list_model.rowCount() == 1
    assert tab.notes_tab.list_model.index(0, 0).data() == "A Note"
    assert sorted(p.name for p in notes_base.iterdir()) == [card["id"]]
