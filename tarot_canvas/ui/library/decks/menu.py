"""Every installed deck, to start a reading with"""

from PyQt6.QtGui import QActionGroup
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models.deck_library import DeckLibrary, deck_library
from tarot_canvas.settings import get_readings_deck, set_readings_deck


def remembered_deck():
    """The deck the user last read with"""
    wanted = DeckLibrary.path_key(get_readings_deck())
    if wanted is not None:
        for deck in deck_library.decks():
            if DeckLibrary.path_key(deck.root_path) == wanted:
                return deck
    return deck_library.reference()


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
    remembered = DeckLibrary.path_key(chosen.root_path) if chosen is not None else None
    for deck in deck_library.decks():
        action = menu.addAction(deck.metadata.name.replace("&", "&&"))  # a deck name is no mnemonic
        action.setCheckable(True)
        action.setChecked(DeckLibrary.path_key(deck.root_path) == remembered)
        action.setActionGroup(group)
        action.triggered.connect(lambda _checked, path=deck.root_path: _choose(path, start))


def _choose(deck_path, start):
    set_readings_deck(deck_path)
    start()
