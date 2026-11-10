from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models import readings
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.settings import (
    LIBRARY_READINGS_SORT_DEFAULT,
    LIBRARY_READINGS_SORT_KEY,
    get_settings,
)
from tarot_canvas.ui.library.deletable_page import DeletableListPage
from tarot_canvas.ui.library.reading_details_pane import ReadingDetailsPane
from tarot_canvas.ui.library.readings_model import (
    SORT_EDITED,
    SORT_NEWEST,
    SORT_OLDEST,
    ReadingPathRole,
    ReadingRole,
    ReadingsListModel,
)
from tarot_canvas.ui.library.section_row import SectionedRowDelegate
from tarot_canvas.ui.strings import READINGS, SPREADS

SORT_CHOICES = [
    (SPREADS["sort_newest"], SORT_NEWEST),
    (READINGS["sort_oldest"], SORT_OLDEST),
    (SPREADS["sort_edited"], SORT_EDITED),
]


class ReadingsPage(DeletableListPage):
    """Every kept reading, newest first"""

    # A row was clicked or reached by the keyboard: the pane opens unless the user closed it
    row_chosen = pyqtSignal()
    open_requested = pyqtSignal(object)  # the reading's folder
    delete_requested = pyqtSignal(object)  # the reading's folder

    def __init__(self, decks=list, reference=lambda: None, parent=None, base=None):
        self._base = base  # tests point the index somewhere else
        self._decks = decks
        self._reference = reference
        super().__init__(
            ReadingsListModel(readings.scan(base), decks(), reference()),
            SectionedRowDelegate,
            ReadingDetailsPane(),
            parent,
            changed=reading_events().readings_changed,
            texts={
                "deleted": READINGS["library_deleted_message"],
                "delete_failed": READINGS["library_delete_failed"],
                "restore_failed": READINGS["library_restore_failed"],
            },
        )
        self._programmatic = 0  # nesting depth of selection the user didn't make
        self.list_model.set_sort(
            get_settings().value(LIBRARY_READINGS_SORT_KEY, LIBRARY_READINGS_SORT_DEFAULT, type=str)
        )
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)
        self.list_view.clicked.connect(self._on_clicked)
        self.list_view.selectionModel().currentChanged.connect(self._on_keyboard_current)
        self.details_pane.open_requested.connect(self.open_requested)

        reading_events().readings_changed.connect(self.refresh)
        # A deck installed or removed names or unnames the details pane's cards
        deck_events().decks_changed.connect(self.refresh)

        self._update_empty_state()

    # -- what the library asks of a page ----------------------------------

    def search_placeholder(self):
        return READINGS["library_search_placeholder"]

    def details_toggle_tooltip(self, is_open):
        return READINGS["library_details_toggle_hide" if is_open else "library_details_toggle_show"]

    def sort_choices(self):
        return SORT_CHOICES

    def sort_tooltip(self):
        return READINGS["sort_tooltip"]

    def sort_key(self):
        return self.list_model.sort()

    def set_sort_key(self, key):
        selected = self._selected_path()
        self.list_model.set_sort(key)
        if selected is not None:
            self.select(selected)
        get_settings().setValue(LIBRARY_READINGS_SORT_KEY, self.sort_key())

    @pyqtSlot()
    def refresh(self):
        """Re-read every reading, keeping the selected one selected if it survives"""
        selected = self._selected_path()
        self.list_model.set_readings(readings.scan(self._base), self._decks(), self._reference())
        if selected is not None:
            self.select(selected)
        self._update_empty_state()
        self._refresh_details()

    def select(self, path):
        return self._select_index(self.list_model.index_for_path(path))

    # -- selection --------------------------------------------------------

    def _empty_text(self, searching):
        return READINGS["library_empty_no_match" if searching else "library_empty"]

    def _select_index(self, index):
        self._programmatic += 1
        try:
            return super()._select_index(index)
        finally:
            self._programmatic -= 1

    def _on_activated(self, index):
        path = index.data(ReadingPathRole)
        if path is not None:
            self.open_requested.emit(path)

    def _on_clicked(self, index):
        if index.data(ReadingRole) is not None:
            self.row_chosen.emit()

    def _on_keyboard_current(self, current, _previous):
        # A press makes the row current before it selects it, so this is the keyboard alone
        if (
            current.data(ReadingRole) is not None
            and self.list_view.hasFocus()
            and self.list_view.selectionModel().isSelected(current)
            and not self._programmatic
        ):
            self.row_chosen.emit()

    def _selected_path(self):
        index = self.list_view.currentIndex()
        if not index.isValid() or not self.list_view.selectionModel().isSelected(index):
            return None
        return index.data(ReadingPathRole)

    def _details_for(self, index):
        return index.data(ReadingRole)

    def _refresh_details(self):
        shown = self.details_pane.details()
        if shown is None:
            return
        self.details_pane.show_details(self.list_model.row_at(shown.path))
        self.details_changed.emit()

    # -- the row's menu -----------------------------------------------------

    def row_menu(self, index):
        path = index.data(ReadingPathRole)
        if path is None:
            return None
        menu = QMenu(self)
        menu.addAction(
            QIcon.fromTheme("document-open"),
            READINGS["library_open"],
            lambda: self.open_requested.emit(path),
        )
        menu.addSeparator()
        menu.addAction(
            QIcon.fromTheme("edit-delete"),
            READINGS["library_delete"],
            lambda: self.delete_requested.emit(path),
        )
        return menu

    def _on_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        menu = self.row_menu(index) if index.isValid() else None
        if menu is not None:
            menu.exec(self.list_view.viewport().mapToGlobal(pos))
            menu.deleteLater()
