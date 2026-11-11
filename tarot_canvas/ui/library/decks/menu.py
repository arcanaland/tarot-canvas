"""Every installed deck, to start a reading with"""

from PyQt6.QtGui import QActionGroup
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import get_readings_deck, set_readings_deck
from tarot_canvas.ui.card_transfer import deck_path_key


def remembered_deck():
    """The deck the user last read with"""
    wanted = deck_path_key(get_readings_deck())
    if wanted is not None:
        for deck in deck_manager.get_all_decks():
            if deck_path_key(deck.deck_path) == wanted:
                return deck
    return deck_manager.get_reference_deck()


def deck_menu(parent, start):
    """A menu of the decks, the remembered one checked

    Choosing a deck remembers it, then calls start(), which opens the reading on the
    remembered deck. Refilled each time it opens, so an install or removal shows.
    """
    menu = QMenu(parent)
    menu.aboutToShow.connect(lambda: _fill(menu, start))
    _fill(menu, start)
    return menu


def _fill(menu, start):
    menu.clear()
    for old in menu.findChildren(QActionGroup):
        old.deleteLater()
    group = QActionGroup(menu)  # exclusive: the mark is the icon
    chosen = remembered_deck()
    remembered = deck_path_key(chosen.deck_path) if chosen is not None else None
    for deck in deck_manager.get_all_decks():
        action = menu.addAction(deck.get_name().replace("&", "&&"))  # a deck name is no mnemonic
        action.setCheckable(True)
        action.setChecked(deck_path_key(deck.deck_path) == remembered)
        action.setActionGroup(group)
        action.triggered.connect(lambda _checked, path=deck.deck_path: _choose(path, start))


def _choose(deck_path, start):
    set_readings_deck(deck_path)
    start()
