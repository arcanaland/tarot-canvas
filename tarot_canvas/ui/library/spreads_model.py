from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt

from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.tab_icon import MINIMAP, layout_marks, spread_icon, spread_marks
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.library.notes_model import PreviewRole
from tarot_canvas.ui.strings import SPREADS

SpreadPathRole = Qt.ItemDataRole.UserRole + 21
SpreadRole = Qt.ItemDataRole.UserRole + 22


def _stamp(path):
    return int(path.name) if path.name.isdecimal() else 0


def _summary(spread):
    """The description's first paragraph, on one line"""
    return " ".join(spread.description.split("\n\n")[0].split())


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
    """Every spread on disk, newest first"""

    def __init__(self, scanned=(), parent=None):
        super().__init__(parent)
        self._search = ""
        self._spreads = []  # (path, spread, thumbnail)
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
            (path, spread, _thumbnail(spread, unit))
            for path, spread in sorted(scanned, key=lambda row: _stamp(row[0]), reverse=True)
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

    def has_items(self):
        return bool(self._rows)

    def _rebuild(self):
        self._rows = [
            row for row in self._spreads if not self._search or _matches(row[1], self._search)
        ]

    def spread_at(self, path):
        """The spread in folder path, whether or not the search shows it"""
        return next((spread for held, spread, _ in self._spreads if held == path), None)

    def index_for_path(self, path):
        for row, (held, _spread, _thumbnail) in enumerate(self._rows):
            if held == path:
                return self.index(row, 0)
        return QModelIndex()

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        path, spread, thumbnail = self._rows[index.row()]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return spread.name or SPREADS["untitled"]
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
