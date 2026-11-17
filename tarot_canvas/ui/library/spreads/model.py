from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt
from PyQt6.QtGui import QIcon

from tarot_canvas.models import library_curation as curation
from tarot_canvas.models.spreads import Spread, edited_at
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.tab_icon import MINIMAP, layout_marks, spread_icon, spread_marks
from tarot_canvas.ui.library.roles import (
    SORT_COUNT,
    SORT_NAME,
    DimmedRole,
    PinnedRole,
    PreviewRole,
    SectionRole,
    SubtitleRole,
    ToggleRole,
)
from tarot_canvas.ui.strings import SPREADS

SpreadPathRole = Qt.ItemDataRole.UserRole + 21
SpreadRole = Qt.ItemDataRole.UserRole + 22
# Whether an included spread is hidden: out of Included and the New Reading menu
SpreadHiddenRole = Qt.ItemDataRole.UserRole + 23

SORT_NEWEST = "newest"
SORT_EDITED = "edited"
SORTS = (SORT_NEWEST, SORT_NAME, SORT_COUNT, SORT_EDITED)

# Each section's heading, in the order the sections are listed
SECTION_PINNED = "section_pinned"
SECTION_MINE = "section_mine"
SECTION_INCLUDED = "section_included"


class SpreadRow(NamedTuple):
    path: Path
    spread: Spread
    thumbnail: QIcon
    edited: float
    included: bool = False
    key: str = ""  # its key in the Library's curation


class HiddenToggle(NamedTuple):
    """The quiet row after Included that shows or hides the hidden spreads"""

    count: int
    shown: bool


def _stamp(path):
    return int(path.name) if path.name.isdecimal() else 0


def _summary(spread):
    """The description's first paragraph, on one line"""
    return " ".join(spread.description.split("\n\n")[0].split())


def spread_title(spread):
    return spread.name or SPREADS["untitled"]


def _sectioned(
    rows, sort, pinned=frozenset(), hidden=frozenset(), show_hidden=False, searching=False
):
    """Pinned, the user's, then the included rows, each under its heading

    The user's and the pinned follow sort. A hidden spread is left out of Included unless a
    search or Show brings it back, and a HiddenToggle row ends Included while any is hidden
    and no search is. Ties go by name. A section with no rows has no heading.
    """
    pins = [row for row in rows if row.key in pinned]
    own = [row for row in rows if not row.included and row.key not in pinned]
    included = [row for row in rows if row.included and row.key not in pinned]
    hidden_count = sum(row.key in hidden for row in included)
    if not (searching or show_hidden):
        included = [row for row in included if row.key not in hidden]
    toggle = hidden_count and not searching
    # A packaged folder's name and mtime say nothing about when it was made or edited
    included_sort = sort if sort in (SORT_NAME, SORT_COUNT) else SORT_NAME
    sectioned = []
    for heading, members, order in (
        (SECTION_PINNED, pins, sort),
        (SECTION_MINE, own, sort),
        (SECTION_INCLUDED, included, included_sort),
    ):
        if members or (heading == SECTION_INCLUDED and toggle):
            sectioned.append(heading)
            sectioned.extend(_sorted_by(members, order))
    if toggle:
        sectioned.append(HiddenToggle(hidden_count, show_hidden))
    return sectioned


def _sorted_by(rows, sort):
    by_name = sorted(rows, key=lambda row: spread_title(row.spread).casefold())
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
    """Every spread on disk: the user's, then those that ship with the app"""

    def __init__(self, scanned=(), included=(), parent=None):
        super().__init__(parent)
        self._search = ""
        self._sort = SORT_NEWEST
        self._spreads = []
        self._pinned = frozenset()
        self._hidden = frozenset()
        self._show_hidden = False  # for this session: Show isn't remembered
        self._rows = []  # a SpreadRow, a HiddenToggle, or the key of a section's heading
        self._hold(scanned, included)
        self._rebuild()

    def set_spreads(self, scanned, included=()):
        self.beginResetModel()
        self._hold(scanned, included)
        self._rebuild()
        self.endResetModel()

    def _hold(self, scanned, included):
        unit = card_unit_size()
        self._spreads = [
            SpreadRow(path, spread, spread_thumbnail(spread, unit), edited_at(path), key=path.name)
            for path, spread in scanned
        ] + [
            SpreadRow(
                path,
                spread,
                spread_thumbnail(spread, unit),
                0.0,
                included=True,
                key=curation.INCLUDED_PREFIX + path.name,
            )
            for path, spread in included
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

    def toggle_hidden(self):
        """Show the hidden spreads, dimmed in place, or put them away again"""
        self.beginResetModel()
        self._show_hidden = not self._show_hidden
        self._rebuild()
        self.endResetModel()

    def has_items(self):
        """Whether any row is a spread or the hidden ones' row, rather than a heading"""
        return any(not isinstance(row, str) for row in self._rows)

    def _rebuild(self):
        self._pinned = frozenset(curation.spread_pins())
        self._hidden = frozenset(curation.spread_hides())
        shown = [
            row for row in self._spreads if not self._search or _matches(row.spread, self._search)
        ]
        self._rows = _sectioned(
            shown,
            self._sort,
            self._pinned,
            self._hidden,
            show_hidden=self._show_hidden,
            searching=bool(self._search),
        )

    def spread_at(self, path):
        """The spread in folder path, whether or not the search shows it"""
        return next((row.spread for row in self._spreads if row.path == path), None)

    def index_for_path(self, path):
        for number, row in enumerate(self._rows):
            if isinstance(row, SpreadRow) and row.path == path:
                return self.index(number, 0)
        return QModelIndex()

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def flags(self, index):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return Qt.ItemFlag.NoItemFlags
        if isinstance(self._rows[index.row()], HiddenToggle):
            # Clicked or Entered, never selected
            return Qt.ItemFlag.ItemIsEnabled
        if not isinstance(self._rows[index.row()], SpreadRow):
            # Drawn by the delegate, but never selected, focused or activated
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        row = self._rows[index.row()]
        if isinstance(row, HiddenToggle):
            if role == ToggleRole:
                return True
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
                key = "hidden_collapse" if row.shown else "hidden_show"
                return SPREADS[key].format(count=row.count)
            return None
        if not isinstance(row, SpreadRow):
            if role == SectionRole:
                return True
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
                return SPREADS[row]
            return None

        path, spread, thumbnail = row.path, row.spread, row.thumbnail

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return spread_title(spread)
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
        if role == PinnedRole:
            return row.key in self._pinned
        if role in (SpreadHiddenRole, DimmedRole):
            # Pinned wins over a hand-edit that also hides; a spread of one's own isn't hidden
            return row.included and row.key in self._hidden and row.key not in self._pinned
        return None


def spread_thumbnail(spread, unit):
    return spread_icon(layout_marks(spread_marks(spread, unit), MINIMAP.max_fill))
