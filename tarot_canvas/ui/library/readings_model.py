from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.readings import Reading
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.icons import CanvasIcon
from tarot_canvas.ui.canvas.saved_canvas import find_deck, local_qdatetime, reading_label
from tarot_canvas.ui.canvas.tab_icon import (
    MINIMAP,
    layout_marks,
    reading_marks,
    snapped,
    spread_icon,
)
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.library.notes_model import PreviewRole, card_name
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.utils.dates import relative_date

ReadingPathRole = Qt.ItemDataRole.UserRole + 31
ReadingRole = Qt.ItemDataRole.UserRole + 32


class ReadingRow(NamedTuple):
    path: Path
    reading: Reading
    notes: list  # of models.notes.Note, newest first
    icon: object  # a QIcon
    card_lines: tuple  # each card's name, marked when reversed


def reading_icon(reading, unit):
    """a minimap of a canvas's cards, or an empty canvas's icon"""
    marks = snapped(layout_marks(reading_marks(reading, unit), MINIMAP.max_fill))
    return spread_icon(marks) if marks else CanvasIcon()


def _row(path, reading, decks, reference, unit):
    resolved = {}
    card_lines = []
    for card in reading.cards:
        if card.deck not in resolved:
            # As the reading opens: a deck that isn't installed shows as the reference deck
            resolved[card.deck] = find_deck(card.deck, decks) or reference
        name = card_name(resolved[card.deck], card.id)
        card_lines.append(READINGS["card_reversed"].format(card=name) if card.reversed else name)
    return ReadingRow(
        path,
        reading,
        notes_model.read_directory(path),
        reading_icon(reading, unit),
        tuple(card_lines),
    )


def label(reading):
    return reading_label(reading.question, reading.date)


def newest_note_line(row):
    return notes_model.label(row.notes[0]) if row.notes else ""


def _match(row, search):
    """(whether row matches, the note line to show for it or None)"""
    folded = search.casefold()
    if folded in row.reading.question.casefold():
        return True, None
    for note in row.notes:
        if folded in notes_model.label(note).casefold():
            return True, notes_model.label(note)
        line = notes_model.matching_line(note, search)
        if line is not None:
            return True, line
    return False, None


class ReadingsListModel(QAbstractListModel):
    """Every kept reading, newest first"""

    def __init__(self, scanned=(), decks=(), reference=None, parent=None):
        super().__init__(parent)
        self._search = ""
        self._all = []
        self._rows = []  # (ReadingRow, preview line)
        self._hold(scanned, decks, reference)
        self._rebuild()

    def set_readings(self, scanned, decks=(), reference=None):
        self.beginResetModel()
        self._hold(scanned, decks, reference)
        self._rebuild()
        self.endResetModel()

    def _hold(self, scanned, decks, reference):
        decks, unit = list(decks), card_unit_size()
        self._all = [_row(path, reading, decks, reference, unit) for path, reading in scanned]

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

    def has_items(self):
        return bool(self._rows)

    def _rebuild(self):
        self._rows = []
        for row in self._all:
            if not self._search:
                self._rows.append((row, newest_note_line(row)))
                continue
            matched, line = _match(row, self._search)
            if matched:
                self._rows.append((row, line if line is not None else newest_note_line(row)))

    def row_at(self, path):
        """The reading in folder path, whether or not the search shows it"""
        return next((row for row in self._all if row.path == Path(path)), None)

    def index_for_path(self, path):
        for number, (row, _preview) in enumerate(self._rows):
            if row.path == Path(path):
                return self.index(number, 0)
        return QModelIndex()

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        row, preview = self._rows[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return label(row.reading)
        if role == SubtitleRole:
            return relative_date(local_qdatetime(row.reading.date).date())
        if role == PreviewRole:
            return preview
        if role == Qt.ItemDataRole.DecorationRole:
            return row.icon
        if role == ReadingPathRole:
            return row.path
        if role == ReadingRole:
            return row
        return None
