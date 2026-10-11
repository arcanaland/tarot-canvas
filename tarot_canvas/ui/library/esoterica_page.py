from PyQt6.QtCore import pyqtSignal, pyqtSlot

from tarot_canvas.models.esoterica import get_esoterica_manager
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library.esoterica_list_model import EsotericaListModel
from tarot_canvas.ui.library.list_page import LibraryListPage
from tarot_canvas.ui.library.notes_model import card_name
from tarot_canvas.ui.library.source_details_pane import SourceDetailsPane, details_for
from tarot_canvas.ui.library.source_row_delegate import SourceRowDelegate


class EsotericaPage(LibraryListPage):
    """Every esoterica source the app found"""

    # A row was activated
    details_requested = pyqtSignal()
    # A covered card in the pane's grid was clicked
    card_activated = pyqtSignal(str)  # the canonical card id

    def __init__(self, manager=None, deck=None, parent=None):
        manager = manager if manager is not None else get_esoterica_manager()
        super().__init__(
            EsotericaListModel(manager), SourceRowDelegate, SourceDetailsPane(), parent
        )
        self._manager = manager
        # Only names the grid's cells
        self._deck = deck

        self.details_pane.coverage_grid.card_name = lambda card_id: card_name(self._deck, card_id)
        self.details_pane.open_card_requested.connect(self.card_activated)

        # Also how a checkbox's own write comes back
        esoterica_events().sources_changed.connect(self.refresh)

        self._update_empty_state()

    # -- what the library asks of a page ----------------------------------

    def search_placeholder(self):
        return label_for("library.search_placeholder")

    def details_toggle_tooltip(self, is_open):
        return label_for(
            "library.details_toggle_hide" if is_open else "library.details_toggle_show"
        )

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
            self._show_details(self._index_for(_key_of(shown)))

    def select(self, key):
        """Select a source by identifier, or a skipped file by path"""
        return self._select_index(self._index_for(key))

    # -- selection --------------------------------------------------------

    def _empty_text(self, searching):
        return label_for("library.empty_no_match" if searching else "library.empty")

    def _details_for(self, index):
        if not index.isValid():
            return None
        return details_for(index, self._manager)

    def _index_for(self, key):
        index = self.list_model.index_for_identifier(key)
        if not index.isValid():
            index = self.list_model.index_for_path(key)
        return index

    def _selected_key(self):
        index = self.list_view.currentIndex()
        if not index.isValid() or not self.list_view.selectionModel().isSelected(index):
            return None
        details = self._details_for(index)
        return None if details is None else _key_of(details)

    def _on_activated(self, index):
        if self._details_for(index) is not None:
            self._show_details(index)
            self.details_requested.emit()


def _key_of(details):
    return details.identifier if details.identifier is not None else details.path
