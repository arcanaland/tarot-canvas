from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.readings import READING_FILE, Reading
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
from tarot_canvas.ui.library.cards import card_name
from tarot_canvas.ui.library.roles import PreviewRole, SectionRole, SubtitleRole
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.utils.dates import format_month, relative_date

ReadingPathRole = Qt.ItemDataRole.UserRole + 31
ReadingRole = Qt.ItemDataRole.UserRole + 32

SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"
SORT_EDITED = "edited"
SORTS = (SORT_NEWEST, SORT_OLDEST, SORT_EDITED)


class ReadingRow(NamedTuple):
    path: Path
    reading: Reading
    notes: list  # of models.notes.Note, newest first
    icon: object  # a QIcon
    card_lines: tuple  # each card's name, marked when reversed
    # The spread's, decks' and cards' names, for search
    names: tuple
    edited: float  # the latest write to the reading or its notes


def reading_icon(reading, unit):
    """a minimap of a canvas's cards, or an empty canvas's icon"""
    marks = snapped(layout_marks(reading_marks(reading, unit), MINIMAP.max_fill))
    return spread_icon(marks) if marks else CanvasIcon()


def _row(path, reading, decks, reference, unit):
    resolved = {}
    card_lines, names = [], [reading.spread.name] if reading.spread is not None else []
    for card in reading.cards:
        if card.deck not in resolved:
            # As the reading opens: a deck that isn't installed shows as the reference deck
            deck = resolved[card.deck] = find_deck(card.deck, decks) or reference
            if deck is not None:
                names.append(deck.get_name())
        name = card_name(resolved[card.deck], card.id)
        names.append(name)
        card_lines.append(READINGS["card_reversed"].format(card=name) if card.reversed else name)
    notes = notes_model.read_directory(path)
    return ReadingRow(
        path,
        reading,
        notes,
        reading_icon(reading, unit),
        tuple(card_lines),
        tuple(names),
        max([_modified(path / READING_FILE), *(note.modified for note in notes)]),
    )


def _modified(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def label(reading):
    return reading_label(reading.question, reading.date)


def newest_note_line(row):
    return notes_model.label(row.notes[0]) if row.notes else ""


def _match(row, search):
    """(whether row matches, the note line to show for it or None)"""
    folded = search.casefold()
    if any(folded in text.casefold() for text in (row.reading.question, *row.names)):
        return True, None
    for note in row.notes:
        if folded in notes_model.label(note).casefold():
            return True, notes_model.label(note)
        line = notes_model.matching_line(note, search)
        if line is not None:
            return True, line
    return False, None


def _month(row):
    date = local_qdatetime(row.reading.date).date()
    return date.year(), date.month()


def _sorted(rows, sort):
    """rows in sort's order, under a heading per month when the order is by date"""
    if sort == SORT_EDITED:
        return sorted(rows, key=lambda pair: pair[0].edited, reverse=True)
    rows = sorted(rows, key=lambda pair: pair[0].reading.date, reverse=sort == SORT_NEWEST)
    sectioned, month = [], None
    for pair in rows:
        if _month(pair[0]) != month:
            month = _month(pair[0])
            sectioned.append(format_month(local_qdatetime(pair[0].reading.date).date()))
        sectioned.append(pair)
    return sectioned


class ReadingsListModel(QAbstractListModel):
    """Every kept reading, by date under a heading per month, or by when it was last edited"""

    def __init__(self, scanned=(), decks=(), reference=None, parent=None):
        super().__init__(parent)
        self._search = ""
        self._sort = SORT_NEWEST
        self._all = []
        self._rows = []  # (ReadingRow, preview line), or a month's heading
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

    def set_sort(self, sort):
        sort = sort if sort in SORTS else SORT_NEWEST
        if sort == self._sort:
            return
        self.beginResetModel()
        self._sort = sort
        self._rebuild()
        self.endResetModel()

    def sort(self):
        return self._sort

    def has_items(self):
        return any(not isinstance(row, str) for row in self._rows)

    def _rebuild(self):
        shown = []
        for row in self._all:
            if not self._search:
                shown.append((row, newest_note_line(row)))
                continue
            matched, line = _match(row, self._search)
            if matched:
                shown.append((row, line if line is not None else newest_note_line(row)))
        self._rows = _sorted(shown, self._sort)

    def row_at(self, path):
        """The reading in folder path, whether or not the search shows it"""
        return next((row for row in self._all if row.path == Path(path)), None)

    def index_for_path(self, path):
        for number, row in enumerate(self._rows):
            if not isinstance(row, str) and row[0].path == Path(path):
                return self.index(number, 0)
        return QModelIndex()

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def flags(self, index):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return Qt.ItemFlag.NoItemFlags
        if isinstance(self._rows[index.row()], str):
            # Drawn by the delegate, but never selected, focused or activated
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        if isinstance(self._rows[index.row()], str):
            if role == SectionRole:
                return True
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
                return self._rows[index.row()]
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
