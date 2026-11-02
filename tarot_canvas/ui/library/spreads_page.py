from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QVBoxLayout

from tarot_canvas.models import spreads, staged_delete
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.list_page import LibraryListPage
from tarot_canvas.ui.library.spread_details_pane import SpreadDetails, SpreadDetailsPane
from tarot_canvas.ui.library.spread_row_delegate import SpreadRowDelegate
from tarot_canvas.ui.library.spreads_model import SpreadPathRole, SpreadRole, SpreadsListModel
from tarot_canvas.ui.strings import SPREADS, notes_text
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.utils.logger import logger


class SpreadsPage(LibraryListPage):
    """Every spread the user has saved"""

    spread_activated = pyqtSignal(object)  # the spread's folder
    delete_requested = pyqtSignal(object)  # the spread's folder

    def __init__(self, parent=None, base=None):
        super().__init__(
            SpreadsListModel(spreads.scan(base)), SpreadRowDelegate, SpreadDetailsPane(), parent
        )
        self._base = base  # tests point the index somewhere else
        self.list_view.setUniformItemSizes(True)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)

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

    @pyqtSlot()
    def refresh(self):
        """Re-read every spread, keeping the selected one selected if it survives"""
        selected = self._selected_path()
        self.list_model.set_spreads(spreads.scan(self._base))
        if selected is not None:
            self.select(selected)
        self._update_empty_state()
        self._refresh_details()

    def select(self, path):
        return self._select_index(self.list_model.index_for_path(path))

    # -- selection --------------------------------------------------------

    def _empty_text(self, searching):
        return SPREADS["empty_no_match" if searching else "empty"]

    def _on_activated(self, index):
        self.spread_activated.emit(index.data(SpreadPathRole))

    def _selected_path(self):
        index = self.list_view.currentIndex()
        if not index.isValid() or not self.list_view.selectionModel().isSelected(index):
            return None
        return index.data(SpreadPathRole)

    def _details_for(self, index):
        if not index.isValid():
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
        path = index.data(SpreadPathRole)
        menu = QMenu(self)
        delete = menu.addAction(QIcon.fromTheme("edit-delete"), SPREADS["delete"])
        delete.triggered.connect(lambda: self.delete_requested.emit(path))
        return menu

    def _on_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if index.isValid():
            menu = self.row_menu(index)
            menu.exec(self.list_view.viewport().mapToGlobal(pos))
            menu.deleteLater()

    # -- deleting, undoably -------------------------------------------------

    def delete(self, path):
        """Take the spread out of every view now; remove its folder once Undo is gone"""
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
