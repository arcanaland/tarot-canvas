"""Menus that choose a deck"""

from PyQt6.QtGui import QActionGroup, QIcon
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models.deck_choices import deck_choices
from tarot_canvas.models.deck_library import DeckLibrary, deck_library
from tarot_canvas.settings import get_readings_deck, set_readings_deck
from tarot_canvas.ui.strings import LIBRARY

PIN_ICON = "window-pin"


def remembered_deck():
    """The deck the user last read with"""
    wanted = DeckLibrary.path_key(get_readings_deck())
    if wanted is not None:
        for deck in deck_library.decks():
            if DeckLibrary.path_key(deck.root_path) == wanted:
                return deck
    return deck_library.reference()


def add_pinned_heading(menu):
    menu.addSection(QIcon.fromTheme(PIN_ICON), LIBRARY["pinned_heading"])


def add_deck_actions(menu, pinned, rest, checked, chosen):
    """The decks as one exclusive group"""
    group = QActionGroup(menu)  # exclusive: the mark is the icon
    wanted = DeckLibrary.path_key(checked.root_path) if checked is not None else None
    marked = None
    if pinned:
        add_pinned_heading(menu)
    for entries in (pinned, rest):
        if entries is rest and pinned and rest:
            menu.addSeparator()
        for entry in entries:
            deck = entry[0] if isinstance(entry, tuple) else entry
            action = menu.addAction(deck.metadata.name.replace("&", "&&"))  # no mnemonic
            action.setCheckable(True)
            action.setActionGroup(group)
            if DeckLibrary.path_key(deck.root_path) == wanted:
                action.setChecked(True)
                marked = action
            action.triggered.connect(lambda _checked, entry=entry: chosen(entry))
    return marked


def deck_menu(parent, start=None, *, on_chosen=None, current=remembered_deck):
    """A menu of the decks, current() checked, refilled each time it opens

    By default choosing a deck remembers it, then calls start(), which opens the reading
    on the remembered deck; on_chosen(deck) replaces both.
    """
    if on_chosen is None:
        on_chosen = lambda deck: _remember_and_start(deck, start)  # noqa: E731
    menu = QMenu(parent)
    menu.aboutToShow.connect(lambda: _fill(menu, on_chosen, current))
    _fill(menu, on_chosen, current)
    return menu


def _fill(menu, on_chosen, current):
    menu.clear()
    for old in menu.findChildren(QActionGroup):
        old.deleteLater()
    deck = current()
    add_deck_actions(menu, *deck_choices(current=deck), deck, on_chosen)


def _remember_and_start(deck, start):
    set_readings_deck(deck.root_path)
    start()
