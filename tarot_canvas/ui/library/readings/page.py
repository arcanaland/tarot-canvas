from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QMenu

from tarot_canvas.models import readings
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.settings import (
    LIBRARY_READINGS_FILTER_DEFAULT,
    LIBRARY_READINGS_FILTER_KEY,
    LIBRARY_READINGS_SORT_DEFAULT,
    LIBRARY_READINGS_SORT_KEY,
    get_settings,
)
from tarot_canvas.ui.commands import set_menu_text
from tarot_canvas.ui.library.deletable_page import DeletableListPage
from tarot_canvas.ui.library.readings.details_pane import ReadingDetailsPane
from tarot_canvas.ui.library.readings.model import (
    FILTER_ALL,
    FILTER_CANVASES,
    FILTER_READINGS,
    SORT_EDITED,
    SORT_NEWEST,
    SORT_OLDEST,
    ReadingPathRole,
    ReadingRole,
    ReadingsListModel,
    open_icon,
    open_text,
)
from tarot_canvas.ui.library.readings.row_delegate import ReadingRowDelegate
from tarot_canvas.ui.refresh_when_shown import RefreshWhenShown
from tarot_canvas.ui.strings import READINGS, SPREADS

SORT_CHOICES = [
    (SPREADS["sort_newest"], SORT_NEWEST),
    (READINGS["sort_oldest"], SORT_OLDEST),
    (SPREADS["sort_edited"], SORT_EDITED),
]

FILTER_CHOICES = [
    (READINGS["filter_all"], FILTER_ALL),
    (READINGS["filter_readings"], FILTER_READINGS),
    (READINGS["filter_canvases"], FILTER_CANVASES),
]


class ReadingsPage(DeletableListPage):
    """Every kept reading, newest first"""

    # A row was clicked or reached by the keyboard: the pane opens unless the user closed it
    row_chosen = pyqtSignal()
    open_requested = pyqtSignal(object)  # the reading's folder
    delete_requested = pyqtSignal(object)  # the reading's folder
    rename_requested = pyqtSignal(object, str)  # the reading's folder, its new Question

    def __init__(self, decks=list, reference=lambda: None, parent=None, base=None):
        self._base = base  # tests point the index somewhere else
        self._decks = decks
        self._reference = reference
        super().__init__(
            ReadingsListModel(readings.scan(base), decks(), reference()),
            ReadingRowDelegate,
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
        # The view's clicked follows the release on a row's button
        self._button_click = False
        self.list_model.set_sort(
            get_settings().value(LIBRARY_READINGS_SORT_KEY, LIBRARY_READINGS_SORT_DEFAULT, type=str)
        )
        self.list_model.set_filter(
            get_settings().value(
                LIBRARY_READINGS_FILTER_KEY, LIBRARY_READINGS_FILTER_DEFAULT, type=str
            )
        )
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)
        self.row_delegate.menuRequested.connect(self._on_menu_requested)
        # Renamed only when asked, by F2 or the menu: a double-click opens the canvas
        self.list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Queued: the rename rescans and resets the model the editor is committing to
        self.list_model.renameRequested.connect(
            self.rename_requested, Qt.ConnectionType.QueuedConnection
        )
        self.list_view.pressed.connect(self._on_pressed)
        self.list_view.clicked.connect(self._on_clicked)
        self.list_view.selectionModel().currentChanged.connect(self._on_keyboard_current)
        self.details_pane.open_requested.connect(self.open_requested)

        # Every autosave says readings changed: only a page on screen re-reads them all
        self._on_readings_changed = RefreshWhenShown(self, self.refresh)
        reading_events().readings_changed.connect(self._on_readings_changed.changed)
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

    def filter_choices(self):
        return FILTER_CHOICES

    def filter_name(self):
        return READINGS["filter_name"]

    def filter_key(self):
        return self.list_model.filter()

    def filter_tooltip(self, key):
        if key == FILTER_ALL:
            return READINGS["filter_tooltip"]
        label = next(label for label, choice in FILTER_CHOICES if choice == key)
        return READINGS["filter_tooltip_narrowed"].format(filter=label)

    def set_filter_key(self, key):
        selected = self._selected_path()
        self.list_model.set_filter(key)
        if selected is not None:
            self.select(selected)
        self._update_empty_state()
        get_settings().setValue(LIBRARY_READINGS_FILTER_KEY, self.filter_key())

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
        # A remembered filter must not make a kept entry look lost
        if self.list_model.is_hiding():
            return READINGS["library_empty_filtered"]
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

    def _on_pressed(self, _index):
        self._button_click = False

    def _on_clicked(self, index):
        if self._button_click:
            self._button_click = False
            return
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

    # -- renaming and deleting the selected row ----------------------------

    def rename_selected(self):
        """Edit the selected reading's Question in its row"""
        index = self.list_view.currentIndex()
        if self._selected_path() is None:
            return False
        self.list_view.scrollTo(index)
        self.list_view.edit(index)
        return True

    def can_delete_selected(self):
        """Only while the list has focus, so Delete in the search field stays the field's"""
        focus = QApplication.focusWidget()
        view = self.list_view
        in_list = focus is not None and (focus is view or view.isAncestorOf(focus))
        return in_list and self._selected_path() is not None

    def delete_selected(self):
        path = self._selected_path()
        if path is not None:
            self.delete_requested.emit(path)

    # -- the row's menu -----------------------------------------------------

    def row_menu(self, index):
        path = index.data(ReadingPathRole)
        row = index.data(ReadingRole)
        if path is None or row is None:
            return None
        menu = QMenu(self)
        menu.addAction(
            QIcon.fromTheme(open_icon(row)),
            open_text(row),
            lambda: self.open_requested.emit(path),
        )
        rename = menu.addAction(
            QIcon.fromTheme("edit-rename"),
            READINGS["library_rename"],
            lambda: self._rename_at(path),
        )
        set_menu_text(rename, READINGS["library_rename"], "library.rename")
        menu.addSeparator()
        menu.addAction(
            QIcon.fromTheme("edit-delete"),
            READINGS["library_delete"],
            lambda: self.delete_requested.emit(path),
        )
        return menu

    def _rename_at(self, path):
        if self.select(path):
            self.rename_selected()

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
