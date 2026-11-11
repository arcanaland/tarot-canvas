from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models import spreads
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.settings import (
    LIBRARY_SPREADS_SORT_DEFAULT,
    LIBRARY_SPREADS_SORT_KEY,
    get_settings,
)
from tarot_canvas.ui.commands import set_menu_text
from tarot_canvas.ui.icons import deck_icon
from tarot_canvas.ui.library.decks.menu import deck_menu
from tarot_canvas.ui.library.deletable_page import DeletableListPage
from tarot_canvas.ui.library.roles import SORT_COUNT, SORT_NAME
from tarot_canvas.ui.library.spreads.details_pane import SpreadDetails, SpreadDetailsPane
from tarot_canvas.ui.library.spreads.model import (
    SORT_EDITED,
    SORT_NEWEST,
    SpreadPathRole,
    SpreadRole,
    SpreadsListModel,
)
from tarot_canvas.ui.library.spreads.row_delegate import SpreadRowDelegate
from tarot_canvas.ui.strings import LIBRARY, READINGS, SPREADS
from tarot_canvas.utils.logger import logger

SORT_CHOICES = [
    (SPREADS["sort_newest"], SORT_NEWEST),
    (LIBRARY["sort_name"], SORT_NAME),
    (LIBRARY["sort_count"], SORT_COUNT),
    (SPREADS["sort_edited"], SORT_EDITED),
]


class SpreadsPage(DeletableListPage):
    """Every spread the user has saved, then those that ship with the app"""

    # A row was double-clicked or Entered: the pane opens even if the user closed it
    details_requested = pyqtSignal()
    # A row was clicked or reached by the keyboard: the pane opens unless the user closed it
    row_chosen = pyqtSignal()
    edit_requested = pyqtSignal(object)  # the spread's folder
    reading_requested = pyqtSignal(object)  # the spread's folder
    duplicate_requested = pyqtSignal(object)  # the spread's folder
    delete_requested = pyqtSignal(object)  # the spread's folder

    def __init__(self, parent=None, base=None):
        super().__init__(
            SpreadsListModel(spreads.scan(base), spreads.scan_included()),
            SpreadRowDelegate,
            SpreadDetailsPane(),
            parent,
            changed=spread_events().spreads_changed,
            texts={
                "deleted": SPREADS["deleted_message"],
                "delete_failed": SPREADS["delete_failed"],
                "restore_failed": SPREADS["restore_failed"],
            },
        )
        self._base = base  # tests point the index somewhere else
        self._programmatic = 0  # nesting depth of selection the user didn't make
        # The view's clicked follows the release on a row's button
        self._button_click = False
        self.list_model.set_sort(
            get_settings().value(LIBRARY_SPREADS_SORT_KEY, LIBRARY_SPREADS_SORT_DEFAULT, type=str)
        )
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)
        self.row_delegate.menuRequested.connect(self._on_menu_requested)
        self.row_delegate.readingRequested.connect(self._on_reading_button)
        self.list_view.pressed.connect(self._on_pressed)
        self.list_view.clicked.connect(self._on_clicked)
        self.list_view.selectionModel().currentChanged.connect(self._on_keyboard_current)
        self.details_pane.edit_requested.connect(self.edit_requested)
        self.details_pane.reading_requested.connect(self.reading_requested)

        spread_events().spreads_changed.connect(self.refresh)

        self._update_empty_state()

    # -- what the library asks of a page ----------------------------------

    def search_placeholder(self):
        return SPREADS["search_placeholder"]

    def details_toggle_tooltip(self, is_open):
        return SPREADS["details_toggle_hide" if is_open else "details_toggle_show"]

    def sort_choices(self):
        return SORT_CHOICES

    def sort_tooltip(self):
        return SPREADS["sort_tooltip"]

    def sort_key(self):
        return self.list_model.sort()

    def set_sort_key(self, key):
        selected = self._selected_path()
        self.list_model.set_sort(key)
        if selected is not None:
            self.select(selected)
        get_settings().setValue(LIBRARY_SPREADS_SORT_KEY, self.sort_key())

    @pyqtSlot()
    def refresh(self):
        """Re-read every spread, keeping the selected one selected if it survives"""
        selected = self._selected_path()
        self.list_model.set_spreads(spreads.scan(self._base), spreads.scan_included())
        if selected is not None:
            self.select(selected)
        self._update_empty_state()
        self._refresh_details()

    def select(self, path):
        return self._select_index(self.list_model.index_for_path(path))

    # -- selection --------------------------------------------------------

    def _empty_text(self, searching):
        return SPREADS["empty_no_match" if searching else "empty"]

    def _select_index(self, index):
        self._programmatic += 1
        try:
            return super()._select_index(index)
        finally:
            self._programmatic -= 1

    def _on_activated(self, index):
        if self._details_for(index) is not None:
            self._show_details(index)
            self.details_requested.emit()

    def _on_pressed(self, _index):
        self._button_click = False

    def _on_clicked(self, index):
        if self._button_click:
            self._button_click = False
            return
        if index.data(SpreadRole) is not None:
            self.row_chosen.emit()

    def _on_keyboard_current(self, current, _previous):
        # A press makes the row current before it selects it, so this is the keyboard alone
        if (
            current.data(SpreadRole) is not None
            and self.list_view.hasFocus()
            and self.list_view.selectionModel().isSelected(current)
            and not self._programmatic
        ):
            self.row_chosen.emit()

    def _selected_path(self):
        index = self.list_view.currentIndex()
        if not index.isValid() or not self.list_view.selectionModel().isSelected(index):
            return None
        return index.data(SpreadPathRole)

    def _details_for(self, index):
        # A heading has no spread, and a click on it reaches here all the same
        if not index.isValid() or index.data(SpreadRole) is None:
            return None
        return SpreadDetails(index.data(SpreadPathRole), index.data(SpreadRole))

    def _refresh_details(self):
        shown = self.details_pane.details()
        if shown is None:
            return
        spread = self.list_model.spread_at(shown.path)
        self.details_pane.show_details(
            None if spread is None else SpreadDetails(shown.path, spread)
        )
        self.details_changed.emit()

    # -- the row's menu -----------------------------------------------------

    def row_menu(self, index):
        """The row's menu, or None for a heading"""
        path = index.data(SpreadPathRole)
        # A heading has no path
        if path is None:
            return None
        menu = QMenu(self)

        def add(text, icon, signal):
            action = menu.addAction(QIcon.fromTheme(icon), text)
            action.triggered.connect(lambda: signal.emit(path))
            return action

        start = add(READINGS["open"], "media-playback-start", self.reading_requested)
        set_menu_text(start, READINGS["open"], "library.start_reading")
        decks = deck_menu(menu, lambda: self.reading_requested.emit(path))
        decks.setTitle(READINGS["open_with"])
        decks.setIcon(deck_icon())
        menu.addMenu(decks)
        menu.addSeparator()

        # A built-in's Edit would be its Duplicate: a tab that saves as a new spread
        included = spreads.is_included(path)
        if not included:
            add(SPREADS["edit"], "document-edit", self.edit_requested)
        add(SPREADS["duplicate"], "edit-duplicate", self.duplicate_requested)
        if not included:
            menu.addSeparator()
            add(SPREADS["delete"], "edit-delete", self.delete_requested)
        return menu

    def start_reading(self):
        """Start a reading from the selected spread, if one is"""
        path = self._selected_path()
        if path is not None:
            self.reading_requested.emit(path)

    def _show_row_menu(self, index, global_pos):
        menu = self.row_menu(index) if index.isValid() else None
        if menu is not None:
            menu.exec(global_pos)
            menu.deleteLater()

    def _on_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        self._show_row_menu(index, self.list_view.viewport().mapToGlobal(pos))

    def _on_menu_requested(self, index, global_pos):
        self._button_click = True
        self._show_row_menu(index, global_pos)

    def _on_reading_button(self, index, _global_pos):
        self._button_click = True
        path = index.data(SpreadPathRole)
        if path is not None:
            self.reading_requested.emit(path)

    # -- deleting, undoably -------------------------------------------------

    def delete(self, path):
        if spreads.is_included(path):
            logger.error(f"Refusing to delete included spread {path}")
            return
        super().delete(path)
