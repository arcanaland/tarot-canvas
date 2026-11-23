from tarot_canvas.models import library_curation
from tarot_canvas.ui.library.decks.menu import deck_menu
from tarot_canvas.ui.strings import LIBRARY
from tests.unit.test_library_model import fake_deck


def deck(name):
    return fake_deck(name, identifier=f"x/deck/{name.lower()}")


def rows(menu):
    menu.aboutToShow.emit()
    return [(action.isSeparator(), action.text()) for action in menu.actions()]


def test_a_section_heads_the_pinned_decks_only_when_one_is(qtbot, stub_deck_library):
    aurora, birch, cedar = deck("Aurora"), deck("Birch"), deck("Cedar")
    stub_deck_library.decks = lambda: [cedar, birch, aurora]
    chosen = []
    menu = deck_menu(None, on_chosen=chosen.append, current=lambda: birch)

    assert rows(menu) == [(False, "Aurora"), (False, "Birch"), (False, "Cedar")]

    library_curation.set_deck_pinned("x/deck/cedar", True)
    assert rows(menu) == [
        (True, LIBRARY["pinned_heading"]),
        (False, "Cedar"),
        (True, ""),
        (False, "Aurora"),
        (False, "Birch"),
    ]
    assert [action.text() for action in menu.actions() if action.isChecked()] == ["Birch"]

    menu.actions()[1].trigger()
    assert chosen == [cedar]
    menu.deleteLater()
