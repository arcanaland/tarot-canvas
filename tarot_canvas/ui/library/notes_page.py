from PyQt6.QtCore import pyqtSignal

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.library.list_page import LibraryListPage
from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_details import CardNotesDetails
from tarot_canvas.ui.library.notes_details_pane import NotesDetailsPane
from tarot_canvas.ui.library.notes_model import (
    CardIdRole,
    NotesListModel,
    card_name,
)
from tarot_canvas.ui.notes_text import text as notes_text


class NotesPage(LibraryListPage):
    card_activated = pyqtSignal(str)  # the canonical card id
    note_activated = pyqtSignal(str, str)  # the canonical card id, the note's path

    def __init__(self, deck=None, parent=None, base=None):
        super().__init__(
            NotesListModel(notes_model.scan(base), deck),
            NoteRowDelegate,
            NotesDetailsPane(),
            parent,
        )
        self._base = base  # tests point the index somewhere else
        self._deck = deck
        self.list_view.setUniformItemSizes(True)

        self.details_pane.open_card_requested.connect(self.card_activated)
        self.details_pane.open_note_requested.connect(self.note_activated)

        note_events().notes_changed.connect(self.refresh)

        self._update_empty_state()

    # -- what the library asks of a page ----------------------------------

    def search_placeholder(self):
        return notes_text("search_placeholder")

    def details_toggle_tooltip(self, is_open):
        return notes_text("details_toggle_hide" if is_open else "details_toggle_show")

    def set_deck(self, deck):
        self._deck = deck
        self.list_model.set_deck(deck)

    def refresh(self):
        """Re-read the whole corpus."""
        card_id = self._current_card_id()
        self.list_model.set_index(notes_model.scan(self._base))
        if card_id:
            self.select_card(card_id)
        self._update_empty_state()
        self._refresh_details()

    def select_card(self, card_id):
        """Select the newest note on the card."""
        for row in range(self.list_model.rowCount()):
            index = self.list_model.index(row, 0)
            if index.data(CardIdRole) == card_id:
                return self._select_index(index)
        return False

    # -- selection --------------------------------------------------------

    def _empty_text(self, searching):
        return notes_text("empty_no_match" if searching else "empty_nothing_written")

    def _on_activated(self, index):
        card_id = index.data(CardIdRole)
        if card_id:
            self.card_activated.emit(card_id)

    def _current_card_id(self):
        index = self.list_view.currentIndex()
        return index.data(CardIdRole) if index.isValid() else None

    def _details_for(self, index):
        return self._details_for_card(index.data(CardIdRole))

    def _details_for_card(self, card_id):
        if not card_id:
            return None
        return CardNotesDetails(
            card_id=card_id,
            name=card_name(self._deck, card_id) or None,
            notes=tuple(self.list_model.notes_for(card_id)),
        )

    def _refresh_details(self):
        shown = self.details_pane.details()
        if shown is not None:
            self._show(self._details_for_card(shown.card_id))
