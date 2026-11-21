"""An installed deck's menu, on its cover and behind its details pane's ⋮"""

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models.deck_library import is_removable
from tarot_canvas.models.library_curation import is_handmade
from tarot_canvas.ui.strings import DECK_VIEW, LIBRARY, READINGS, SPREADS


def deck_row_menu(parent, deck, page):
    """A new menu for deck, whose actions are the page's"""
    menu = QMenu(parent)
    fill_deck_menu(menu, deck, page)
    return menu


def fill_deck_menu(menu, deck, page):
    """Empty menu and fill it for deck"""
    menu.clear()
    for old in menu.findChildren(QMenu):
        old.deleteLater()

    def add(text, icon, slot):
        action = menu.addAction(QIcon.fromTheme(icon), text)
        action.triggered.connect(lambda: slot(deck))
        return action

    add(LIBRARY["open"], "document-open", page.open_deck)
    if page.spread_menu is not None:
        spreads = page.spread_menu(
            menu, lambda path: page.start_reading(deck, path), page.browse_spreads_requested.emit
        )
        spreads.setTitle(READINGS["open"])
        spreads.setIcon(QIcon.fromTheme("media-playback-start"))
        menu.addMenu(spreads)
    menu.addSeparator()

    add(SPREADS["open_folder"], "document-open-folder", page.open_folder)
    if is_handmade(deck.root_path):
        add(DECK_VIEW["export"], "document-export", page.export_requested.emit)
    menu.addSeparator()

    remove = add(LIBRARY["remove_deck"], "edit-delete", page.remove)
    remove.setEnabled(is_removable(deck))
