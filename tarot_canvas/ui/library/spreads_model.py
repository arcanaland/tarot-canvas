from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt
from PyQt6.QtGui import QIcon

from tarot_canvas.models.spreads import Spread, edited_at
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.tab_icon import MINIMAP, layout_marks, spread_icon, spread_marks
from tarot_canvas.ui.library.deck_model import SORT_COUNT, SORT_NAME, SubtitleRole
from tarot_canvas.ui.library.notes_model import PreviewRole
from tarot_canvas.ui.strings import SPREADS

SpreadPathRole = Qt.ItemDataRole.UserRole + 21
SpreadRole = Qt.ItemDataRole.UserRole + 22

SORT_NEWEST = "newest"
SORT_EDITED = "edited"
SORTS = (SORT_NEWEST, SORT_NAME, SORT_COUNT, SORT_EDITED)


class SpreadRow(NamedTuple):
    path: Path
    spread: Spread
    thumbnail: QIcon
    edited: float


def _stamp(path):
    return int(path.name) if path.name.isdecimal() else 0


def _summary(spread):
    """The description's first paragraph, on one line"""
    return " ".join(spread.description.split("\n\n")[0].split())


def _title(spread):
    return spread.name or SPREADS["untitled"]


def _sorted(rows, sort):
    """rows in sort's order, ties by name"""
    by_name = sorted(rows, key=lambda row: _title(row.spread).casefold())
    if sort == SORT_NAME:
        return by_name
    if sort == SORT_COUNT:
        return sorted(by_name, key=lambda row: len(row.spread.positions))
    if sort == SORT_EDITED:
        return sorted(by_name, key=lambda row: row.edited, reverse=True)
    return sorted(by_name, key=lambda row: _stamp(row.path), reverse=True)


def _slot_count(spread):
    count = len(spread.positions)
    return SPREADS["slot_count_one"] if count == 1 else SPREADS["slot_count"].format(count=count)


def _searchable(spread):
    yield spread.name
    yield spread.description
    for position in spread.positions:
        yield position.label
        yield position.meaning
    for source in spread.sources:
        yield source.get("author", "")
        yield source.get("note", "")


def _matches(spread, search):
    folded = search.casefold()
    return any(folded in str(text).casefold() for text in _searchable(spread))


class SpreadsListModel(QAbstractListModel):
    """Every spread on disk"""

    def __init__(self, scanned=(), parent=None):
        super().__init__(parent)
        self._search = ""
        self._sort = SORT_NEWEST
        self._spreads = []
        self._rows = []
        self._hold(scanned)
        self._rebuild()

    def set_spreads(self, scanned):
        self.beginResetModel()
        self._hold(scanned)
        self._rebuild()
        self.endResetModel()

    def _hold(self, scanned):
        unit = card_unit_size()
        self._spreads = [
            SpreadRow(path, spread, _thumbnail(spread, unit), edited_at(path))
            for path, spread in scanned
        ]

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
        return bool(self._rows)

    def _rebuild(self):
        shown = [
            row for row in self._spreads if not self._search or _matches(row.spread, self._search)
        ]
        self._rows = _sorted(shown, self._sort)

    def spread_at(self, path):
        """The spread in folder path, whether or not the search shows it"""
        return next((row.spread for row in self._spreads if row.path == path), None)

    def index_for_path(self, path):
        for number, row in enumerate(self._rows):
            if row.path == path:
                return self.index(number, 0)
        return QModelIndex()

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        path, spread, thumbnail, _edited = self._rows[index.row()]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return _title(spread)
        if role == Qt.ItemDataRole.DecorationRole:
            return thumbnail
        if role == SubtitleRole:
            return _slot_count(spread)
        if role == PreviewRole:
            return _summary(spread)
        if role == SpreadPathRole:
            return path
        if role == SpreadRole:
            return spread
        return None


def _thumbnail(spread, unit):
    return spread_icon(layout_marks(spread_marks(spread, unit), MINIMAP.max_fill))
