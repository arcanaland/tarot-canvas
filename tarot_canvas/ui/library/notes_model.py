from PyQt6.QtCore import QAbstractListModel, Qt

from tarot_canvas.models import notes as notes_model
from tarot_canvas.ui.library.deck_model import CoverPathRole, SubtitleRole
from tarot_canvas.utils.dates import relative_date_from_timestamp

CardIdRole = Qt.ItemDataRole.UserRole + 11
NoteRole = Qt.ItemDataRole.UserRole + 13
PreviewRole = Qt.ItemDataRole.UserRole + 15

SUBTITLE_SEPARATOR = " • "


def card_in(deck, card_id):
    if deck is None:
        return None
    try:
        return deck.get_card_by_id(card_id)
    except Exception:
        return None


def card_name(deck, card_id):
    """The deck's name for the card."""
    card = card_in(deck, card_id)
    name = (card or {}).get("name")
    return name or card_id


def card_cover_path(deck, card_id):
    card = card_in(deck, card_id)
    return (card or {}).get("image")


class NotesListModel(QAbstractListModel):
    """across the whole library"""

    def __init__(self, index=None, deck=None, parent=None):
        super().__init__(parent)
        self._index = dict(index or {})
        self._deck = deck
        self._search = ""
        self._rows = []  # (note, preview line)
        self._first_lines = {}  # (path, modified) -> first body line, until the index changes
        self._rebuild()

    def set_index(self, index):
        self.beginResetModel()
        self._index = dict(index or {})
        self._first_lines.clear()
        self._rebuild()
        self.endResetModel()

    def set_deck(self, deck):
        self.beginResetModel()
        self._deck = deck
        self._rebuild()
        self.endResetModel()

    def set_search(self, search):
        search = (search or "").strip()
        if search == self._search:
            return
        self.beginResetModel()
        self._search = search
        self._rebuild()
        self.endResetModel()

    def search(self):
        return self._search

    def total_rows(self):
        return sum(len(notes) for notes in self._index.values())

    def notes_for(self, card_id):
        """Every note on a card."""
        return self._index.get(card_id, [])

    def deck(self):
        return self._deck

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def _rebuild(self):
        self._rows = []
        for notes in self._index.values():
            for note in notes:
                matched, line = self._matches(note)
                if matched:
                    preview = line if line is not None else self._first_line(note)
                    self._rows.append((note, preview))

        self._rows.sort(key=lambda row: row[0].modified, reverse=True)

    def _matches(self, note):
        if not self._search:
            return True, None

        folded = self._search.casefold()
        haystacks = [notes_model.label(note), card_name(self._deck, note.card_id)]
        if any(folded in (hay or "").casefold() for hay in haystacks):
            return True, None

        line = notes_model.matching_line(note, self._search)
        return line is not None, line

    def _first_line(self, note):
        key = (note.path, note.modified)
        if key not in self._first_lines:
            self._first_lines[key] = notes_model.first_body_line(note)
        return self._first_lines[key]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        note, preview = self._rows[index.row()]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return notes_model.label(note)
        if role == NoteRole:
            return note
        if role == CardIdRole:
            return note.card_id
        if role == CoverPathRole:
            return card_cover_path(self._deck, note.card_id)
        if role == SubtitleRole:
            return self._subtitle(note)
        if role == PreviewRole:
            return preview
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{notes_model.label(note)}\n{self._subtitle(note)}"
        return None

    def _subtitle(self, note):
        return SUBTITLE_SEPARATOR.join(
            [card_name(self._deck, note.card_id), relative_date_from_timestamp(note.modified)]
        )
