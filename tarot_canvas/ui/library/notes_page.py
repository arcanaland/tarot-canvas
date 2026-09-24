from PyQt6.QtCore import QItemSelectionModel, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListView,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.library.deselect import deselect_on_empty_click_or_escape
from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_details import CardNotesDetails
from tarot_canvas.ui.library.notes_details_pane import NotesDetailsPane
from tarot_canvas.ui.library.notes_model import (
    CardIdRole,
    NotesListModel,
    card_cover_path,
    card_name,
)
from tarot_canvas.ui.notes_text import text as notes_text


class NotesPage(QWidget):
    card_activated = pyqtSignal(str)  # the canonical card id
    note_activated = pyqtSignal(str, str)  # the canonical card id, the note's path
    details_changed = pyqtSignal()

    def __init__(self, deck=None, parent=None, base=None):
        super().__init__(parent)
        self._base = base  # tests point the index somewhere else
        self._deck = deck

        self.list_model = NotesListModel(notes_model.scan(self._base), deck, parent=self)
        self.list_view = self._build_list()

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setEnabled(False)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.list_view, 1)
        column.addWidget(self.empty_label)

        self.details_pane = NotesDetailsPane()
        self.details_pane.open_card_requested.connect(self.card_activated)
        self.details_pane.open_note_requested.connect(self.note_activated)

        note_events().notes_changed.connect(self.refresh)

        self._update_empty_state()

    def _build_list(self):
        view = QListView()
        view.setModel(self.list_model)
        self.row_delegate = NoteRowDelegate(view)
        view.setItemDelegate(self.row_delegate)

        view.setViewMode(QListView.ViewMode.ListMode)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setUniformItemSizes(True)
        view.setAlternatingRowColors(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setMouseTracking(True)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        view.activated.connect(self._on_activated)
        view.clicked.connect(self._show_details)
        view.selectionModel().currentChanged.connect(self._on_current_changed)
        deselect_on_empty_click_or_escape(view)
        return view

    # -- what the library asks of a page ----------------------------------

    def set_search(self, text):
        self.list_model.set_search(text)
        self._update_empty_state()

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
                self.list_view.selectionModel().setCurrentIndex(
                    index, QItemSelectionModel.SelectionFlag.ClearAndSelect
                )
                return True
        return False

    # -- selection --------------------------------------------------------

    def _on_current_changed(self, current, _previous):
        if current.isValid():
            self._show_details(current)

    def _on_activated(self, index):
        card_id = index.data(CardIdRole)
        if card_id:
            self.card_activated.emit(card_id)

    def _current_card_id(self):
        index = self.list_view.currentIndex()
        return index.data(CardIdRole) if index.isValid() else None

    def _show_details(self, index):
        self._show_card(index.data(CardIdRole))

    def _show_card(self, card_id):
        details = self._details_for_card(card_id)
        if details is not None:
            self.details_pane.show_details(details)
            self.details_changed.emit()

    def _details_for_card(self, card_id):
        if not card_id:
            return None
        return CardNotesDetails(
            card_id=card_id,
            name=card_name(self._deck, card_id) or None,
            cover_path=card_cover_path(self._deck, card_id),
            notes=tuple(self.list_model.notes_for(card_id)),
        )

    def _refresh_details(self):
        shown = self.details_pane.details()
        if shown is not None:
            self._show_card(shown.card_id)

    def _update_empty_state(self):
        empty = self.list_model.rowCount() == 0
        if empty:
            key = "empty_no_match" if self.list_model.search() else "empty_nothing_written"
            self.empty_label.setText(notes_text(key))
        self.empty_label.setVisible(empty and bool(self.empty_label.text()))
        self.list_view.setVisible(not empty)
