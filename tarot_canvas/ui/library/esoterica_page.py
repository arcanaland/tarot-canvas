from PyQt6.QtCore import QItemSelectionModel, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListView,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.esoterica import get_esoterica_manager
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library.deselect import deselect_on_empty_click_or_escape
from tarot_canvas.ui.library.esoterica_list_model import EsotericaListModel
from tarot_canvas.ui.library.notes_model import card_name
from tarot_canvas.ui.library.source_details_pane import SourceDetailsPane, details_for
from tarot_canvas.ui.library.source_row_delegate import SourceRowDelegate


class EsotericaPage(QWidget):
    """Every esoterica source the app found, and every file it skipped"""

    details_changed = pyqtSignal()
    # A row was activated: the pane is the only thing a source opens into
    details_requested = pyqtSignal()
    # A covered card in the pane's grid was clicked
    card_activated = pyqtSignal(str)  # the canonical card id

    def __init__(self, manager=None, deck=None, parent=None):
        super().__init__(parent)
        self._manager = manager if manager is not None else get_esoterica_manager()
        # Only names the grid's cells, as the notes page names its cards
        self._deck = deck

        self.list_model = EsotericaListModel(self._manager, parent=self)
        self.list_view = self._build_list()

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setEnabled(False)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.list_view, 1)
        column.addWidget(self.empty_label)

        self.details_pane = SourceDetailsPane()
        self.details_pane.coverage_grid.card_name = lambda card_id: card_name(self._deck, card_id)
        self.details_pane.open_card_requested.connect(self.card_activated)

        # Also how a checkbox's own write comes back, so the rows say what is now on
        esoterica_events().sources_changed.connect(self.refresh)

        self._update_empty_state()

    def _build_list(self):
        view = QListView()
        view.setModel(self.list_model)
        self.row_delegate = SourceRowDelegate(view)
        view.setItemDelegate(self.row_delegate)

        view.setViewMode(QListView.ViewMode.ListMode)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        # Not uniform: a section heading is one short line, a source two
        view.setAlternatingRowColors(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setMouseTracking(True)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        view.activated.connect(self._on_activated)
        activate_on_return(view)
        view.clicked.connect(self._show_details)
        view.selectionModel().currentChanged.connect(self._on_current_changed)
        deselect_on_empty_click_or_escape(view)
        return view

    # -- what the library asks of a page ----------------------------------

    def set_search(self, text):
        self.list_model.set_search(text)
        self._update_empty_state()

    @pyqtSlot()
    def refresh(self):
        """Rebuild the rows, keeping the selected source or file selected"""
        shown = self.details_pane.details()
        selected = self._selected_key()
        self.list_model.refresh()
        if selected is not None:
            self.select(selected)
        self._update_empty_state()
        if shown is not None:
            self._refresh_details(shown)

    def select(self, key):
        """Select a source by identifier, or a skipped file by path"""
        index = self._index_for(key)
        if not index.isValid():
            return False
        self.list_view.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        return True

    # -- selection --------------------------------------------------------

    def _index_for(self, key):
        index = self.list_model.index_for_identifier(key)
        if not index.isValid():
            index = self.list_model.index_for_path(key)
        return index

    def _selected_key(self):
        index = self.list_view.currentIndex()
        if not index.isValid() or not self.list_view.selectionModel().isSelected(index):
            return None
        details = details_for(index, self._manager)
        return None if details is None else _key_of(details)

    def _on_current_changed(self, current, _previous):
        if current.isValid():
            self._show_details(current)

    def _on_activated(self, index):
        if details_for(index, self._manager) is not None:
            self._show_details(index)
            self.details_requested.emit()

    def _show_details(self, index):
        details = details_for(index, self._manager)
        if details is not None:
            self.details_pane.show_details(details)
            self.details_changed.emit()

    def _refresh_details(self, shown):
        """Re-read what the pane shows; a source that has gone stays shown as it was"""
        index = self._index_for(_key_of(shown))
        if index.isValid():
            self._show_details(index)

    def _update_empty_state(self):
        empty = not self.list_model.has_items()
        if empty:
            key = "library.empty_no_match" if self.list_model.search() else "library.empty"
            self.empty_label.setText(label_for(key))
        self.empty_label.setVisible(empty and bool(self.empty_label.text()))
        self.list_view.setVisible(not empty)


def _key_of(details):
    return details.identifier if details.identifier is not None else details.path
