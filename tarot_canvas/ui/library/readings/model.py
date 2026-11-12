import html
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal

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
from tarot_canvas.ui.library.roles import BadgeRole, PreviewRole, SectionRole, SubtitleRole
from tarot_canvas.ui.strings import READINGS, SPREADS
from tarot_canvas.utils.dates import format_month, format_recent

ReadingPathRole = Qt.ItemDataRole.UserRole + 31
ReadingRole = Qt.ItemDataRole.UserRole + 32

SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"
SORT_EDITED = "edited"
SORTS = (SORT_NEWEST, SORT_OLDEST, SORT_EDITED)

FILTER_ALL = "all"
FILTER_READINGS = "readings"
FILTER_CANVASES = "canvases"
FILTERS = (FILTER_ALL, FILTER_READINGS, FILTER_CANVASES)


class CardRow(NamedTuple):
    # 1-based, in reading.cards, as the diagram numbers it; None on a sandbox canvas
    number: int | None
    position: str  # the spread position's label, or ""
    name: str  # "" while the card is face down
    reversed: bool  # False while the card is face down: a reversal gives it away too
    # The card's id and the deck it opens in, as the reading opens; "" and None face down
    card_id: str = ""
    deck: object = None


def card_row_text(card_row, name=None):
    """One card's row in the pane; name stands in for the card's name when given"""
    if not card_row.name:
        card = READINGS["library_face_down"]
    elif card_row.reversed:
        card = READINGS["card_reversed"].format(card=card_row.name if name is None else name)
    else:
        card = card_row.name if name is None else name
    if card_row.position:
        card = READINGS["library_card_position"].format(position=card_row.position, card=card)
    if card_row.number is None:
        return card
    return SPREADS["slot_row"].format(number=card_row.number, label=card).strip()


_NAME = "\x00"  # where the name goes; nothing a string holds, and untouched by escaping


def card_row_html(card_row, href):
    """card_row_text as rich text, its card's name a link to href; a face-down card has none"""
    if not card_row.name or card_row.deck is None:
        return html.escape(card_row_text(card_row))
    link = f'<a href="{html.escape(href)}">{html.escape(card_row.name)}</a>'
    return html.escape(card_row_text(card_row, name=_NAME)).replace(_NAME, link)


class ReadingRow(NamedTuple):
    path: Path
    reading: Reading
    notes: list  # of models.notes.Note, newest first
    icon: object  # a QIcon
    card_rows: tuple  # of CardRow, in reading.cards order
    # The spread's, decks' and turned cards' names, for search
    names: tuple
    edited: float  # the latest write to the reading or its notes


def reading_icon(reading, unit):
    """a minimap of a canvas's cards, or an empty canvas's icon"""
    marks = snapped(layout_marks(reading_marks(reading, unit), MINIMAP.max_fill))
    return spread_icon(marks) if marks else CanvasIcon()


def is_sandbox(reading):
    """A canvas laid out by hand, rather than a reading dealt from a spread"""
    return reading.spread is None


def spatial_order(cards, unit):
    """cards top to bottom, then left to right; within half a card's height is one row"""
    tolerance = unit.height() / 2
    rows, top = [], None
    for card in sorted(cards, key=lambda card: card.y):
        if top is None or card.y - top > tolerance:
            rows.append([])
            top = card.y
        rows[-1].append(card)
    return [card for row in rows for card in sorted(row, key=lambda card: card.x)]


def _position_labels(reading):
    if reading.spread is None:
        return {}
    return {position.id: position.label for position in reading.spread.positions}


def _row(path, reading, decks, reference, unit):
    resolved, labels = {}, _position_labels(reading)
    # A sandbox is found by the caption its row shows in place of a spread's name
    sandbox = is_sandbox(reading)
    card_rows = []
    names = [READINGS["sandbox_canvas"] if sandbox else reading.spread.name]
    numbers = {id(card): number for number, card in enumerate(reading.cards, start=1)}
    # A sandbox's order is only the order its cards were put down, so it is read by place
    ordered = spatial_order(reading.cards, unit) if sandbox else reading.cards
    for card in ordered:
        if card.deck not in resolved:
            # As the reading opens: a deck that isn't installed shows as the reference deck
            deck = resolved[card.deck] = find_deck(card.deck, decks) or reference
            if deck is not None:
                names.append(deck.get_name())
        # A face-down card is neither named nor found
        name = card_name(resolved[card.deck], card.id) if card.turned else ""
        if name:
            names.append(name)
        position = labels.get(card.position, "") if card.position else ""
        number = None if sandbox else numbers[id(card)]
        opens = (card.id, resolved[card.deck]) if name else ("", None)
        card_rows.append(CardRow(number, position, name, card.reversed and card.turned, *opens))
    notes = notes_model.read_directory(path)
    return ReadingRow(
        path,
        reading,
        notes,
        reading_icon(reading, unit),
        tuple(card_rows),
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


def is_unfinished(row):
    """Whether the reading still has a card face down"""
    return any(not card.turned for card in row.reading.cards)


def revealed_text(row):
    """How many cards are turned of how many, for a reading still being dealt, else None"""
    if not is_unfinished(row):
        return None
    turned = sum(1 for card in row.reading.cards if card.turned)
    return READINGS["library_revealed"].format(turned=turned, total=len(row.reading.cards))


def meta_text(row):
    """The row's and the pane's caption: when, then the spread or Sandbox Canvas"""
    reading = row.reading
    spread = READINGS["sandbox_canvas"] if is_sandbox(reading) else reading.spread.name
    when = format_recent(local_qdatetime(reading.date))
    return READINGS["library_meta"].format(when=when, spread=spread)


def open_text(row):
    return READINGS["library_resume" if is_unfinished(row) else "library_open"]


def open_icon(row):
    return "media-playback-start" if is_unfinished(row) else "document-open"


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


def _kept(row, kind):
    """Whether the filter kind lets row show"""
    if kind == FILTER_READINGS:
        return not is_sandbox(row.reading)
    if kind == FILTER_CANVASES:
        return is_sandbox(row.reading)
    return True


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

    # The reading's folder and the Question it was renamed to
    renameRequested = pyqtSignal(object, str)

    def __init__(self, scanned=(), decks=(), reference=None, parent=None):
        super().__init__(parent)
        self._search = ""
        self._sort = SORT_NEWEST
        self._filter = FILTER_ALL
        self._hidden = False  # whether the filter hides a row the search would show
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

    def set_filter(self, kind):
        kind = kind if kind in FILTERS else FILTER_ALL
        if kind == self._filter:
            return
        self.beginResetModel()
        self._filter = kind
        self._rebuild()
        self.endResetModel()

    def filter(self):
        return self._filter

    def is_hiding(self):
        """Whether the filter hides a row the search alone would show"""
        return self._hidden

    def has_items(self):
        return any(not isinstance(row, str) for row in self._rows)

    def _rebuild(self):
        # Filtered before sorting, so a month the filter empties loses its heading too
        shown, self._hidden = [], False
        for row in self._all:
            if not self._search:
                matched, line = True, None
            else:
                matched, line = _match(row, self._search)
            if not matched:
                continue
            if not _kept(row, self._filter):
                self._hidden = True
                continue
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
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        if not 0 <= index.row() < len(self._rows) or isinstance(self._rows[index.row()], str):
            return False
        row, _preview = self._rows[index.row()]
        question = " ".join(str(value).split())
        if question != row.reading.question:
            self.renameRequested.emit(row.path, question)
        # Nothing here changed: the rename, if it happens, rescans
        return False

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
        if role == Qt.ItemDataRole.EditRole:
            return row.reading.question
        if role == SubtitleRole:
            return meta_text(row)
        if role == BadgeRole:
            return revealed_text(row)
        if role == PreviewRole:
            return preview
        if role == Qt.ItemDataRole.DecorationRole:
            return row.icon
        if role == ReadingPathRole:
            return row.path
        if role == ReadingRole:
            return row
        return None
