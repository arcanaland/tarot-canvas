from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QVBoxLayout

from tarot_canvas.models import spreads, staged_delete
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.settings import (
    LIBRARY_SPREADS_SORT_DEFAULT,
    LIBRARY_SPREADS_SORT_KEY,
    get_settings,
)
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_model import SORT_COUNT, SORT_NAME
from tarot_canvas.ui.library.list_page import LibraryListPage
from tarot_canvas.ui.library.spread_details_pane import SpreadDetails, SpreadDetailsPane
from tarot_canvas.ui.library.spread_row_delegate import SpreadRowDelegate
from tarot_canvas.ui.library.spreads_model import (
    SORT_EDITED,
    SORT_NEWEST,
    SpreadPathRole,
    SpreadRole,
    SpreadsListModel,
)
from tarot_canvas.ui.strings import LIBRARY, SPREADS, notes_text
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.utils.logger import logger

SORT_CHOICES = [
    (SPREADS["sort_newest"], SORT_NEWEST),
    (LIBRARY["sort_name"], SORT_NAME),
    (LIBRARY["sort_count"], SORT_COUNT),
    (SPREADS["sort_edited"], SORT_EDITED),
]


class SpreadsPage(LibraryListPage):
    """Every spread the user has saved, then those that ship with the app"""

    # A row was double-clicked or Entered: the pane opens even if the user closed it
    details_requested = pyqtSignal()
    # A row was clicked or reached by the keyboard: the pane opens unless the user closed it
    row_chosen = pyqtSignal()
    edit_requested = pyqtSignal(object)  # the spread's folder
    duplicate_requested = pyqtSignal(object)  # the spread's folder
    delete_requested = pyqtSignal(object)  # the spread's folder

    def __init__(self, parent=None, base=None):
        super().__init__(
            SpreadsListModel(spreads.scan(base), spreads.scan_included()),
            SpreadRowDelegate,
            SpreadDetailsPane(),
            parent,
        )
        self._base = base  # tests point the index somewhere else
        self._programmatic = 0  # nesting depth of selection the user didn't make
        # The view's clicked follows the release that opened the row's menu
        self._menu_click = False
        self.list_model.set_sort(
            get_settings().value(LIBRARY_SPREADS_SORT_KEY, LIBRARY_SPREADS_SORT_DEFAULT, type=str)
        )
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)
        self.row_delegate.menuRequested.connect(self._on_menu_requested)
        self.list_view.pressed.connect(self._on_pressed)
        self.list_view.clicked.connect(self._on_clicked)
        self.list_view.selectionModel().currentChanged.connect(self._on_keyboard_current)
        self.details_pane.edit_requested.connect(self.edit_requested)

        # (folder, staged path) of a delete that can still be undone
        self.staged = None

        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), notes_text("undo"), self)
        self.undo_action.triggered.connect(self.undo_delete)

        # Hidden, it takes no room, margins included
        message_row = QVBoxLayout()
        margin = units.LARGE_SPACING
        message_row.setContentsMargins(margin, margin, margin, 0)
        self.message = InlineMessage(close_text=notes_text("dismiss"))
        self.message.dismissed.connect(self.commit_pending_delete)
        message_row.addWidget(self.message)
        self.layout().insertLayout(0, message_row)

        spread_events().spreads_changed.connect(self.refresh)

        # Closing the window closes no tab, so quitting is the last chance to commit
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.commit_pending_delete)

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
        self._menu_click = False

    def _on_clicked(self, index):
        if self._menu_click:
            self._menu_click = False
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

        # A built-in's Edit would be its Duplicate: a tab that saves as a new spread
        included = spreads.is_included(path)
        if not included:
            add(SPREADS["edit"], "document-edit", self.edit_requested)
        add(SPREADS["duplicate"], "edit-duplicate", self.duplicate_requested)
        if not included:
            menu.addSeparator()
            add(SPREADS["delete"], "edit-delete", self.delete_requested)
        return menu

    def _show_row_menu(self, index, global_pos):
        menu = self.row_menu(index) if index.isValid() else None
        if menu is not None:
            menu.exec(global_pos)
            menu.deleteLater()

    def _on_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        self._show_row_menu(index, self.list_view.viewport().mapToGlobal(pos))

    def _on_menu_requested(self, index, global_pos):
        self._menu_click = True
        self._show_row_menu(index, global_pos)

    # -- deleting, undoably -------------------------------------------------

    def delete(self, path):
        """Take the spread out of every view now; remove its folder once Undo is gone"""
        if spreads.is_included(path):
            logger.error(f"Refusing to delete included spread {path}")
            return

        # One Undo at a time: the delete it offered becomes final
        self.commit_pending_delete()

        try:
            staged = staged_delete.stage(path)
        except OSError as error:
            logger.error(f"Could not delete spread {path}: {error}")
            self.message.show_message(SPREADS["delete_failed"])
            return

        self.staged = (Path(path), staged)
        spread_events().spreads_changed.emit()
        self.message.show_message(SPREADS["deleted_message"], [self.undo_action])

    @pyqtSlot()
    def undo_delete(self):
        if self.staged is None:
            return

        path, staged = self.staged
        self.staged = None
        self.message.hide()

        try:
            staged_delete.restore(staged, path)
        except OSError as error:
            logger.error(f"Could not restore spread {path}: {error}")
            self.message.show_message(SPREADS["restore_failed"])
            return

        spread_events().spreads_changed.emit()
        self.select(path)

    @pyqtSlot()
    def commit_pending_delete(self):
        """Make the staged delete final"""
        if self.staged is None:
            return

        _path, staged = self.staged
        self.staged = None
        self.message.hide()

        try:
            staged_delete.commit(staged)
        except OSError as error:
            # Left where it is, the folder can still be recovered by hand
            logger.error(f"Could not remove deleted spread {staged}: {error}")
