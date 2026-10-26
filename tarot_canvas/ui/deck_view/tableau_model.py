"""One deck's cards laid out by its structure: the majors in sevens, then a rank by suit table"""

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

from tarot_canvas.models.card_ids import COURTS, MAJOR_ARCANA_COUNT, PIPS, SUITS
from tarot_canvas.ui import typography
from tarot_canvas.ui.deck_view.card_model import (
    KIND_CARD,
    CardRole,
    KindRole,
    name_matches,
)

KIND_LABEL = "label"
KIND_GHOST = "ghost"

ROW_CARDS = "cards"
ROW_LABELS = "labels"
ROW_GAP = "gap"

DimmedRole = Qt.ItemDataRole.UserRole + 10

MAJOR_COLUMNS = 7
FOOL_OFFSET = MAJOR_COLUMNS // 2

SUIT_LABEL_ALIGNMENT = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
RANK_LABEL_ALIGNMENT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def column_count(deck):
    return max(MAJOR_COLUMNS, len(deck.get_suits()) + 1)


def rank_label(deck, rank):
    if rank in COURTS:
        return deck.get_display_court_name(rank)
    return rank.capitalize()


class TableauModel(QAbstractTableModel):
    """A grid over a CardModel: each cell is a card, a label, a ghost or nothing"""

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self._source = source
        self._find = ""
        self._cells = {}  # (row, column) -> (kind, text, source row or None)
        self._row_kinds = []
        self._to_source = {}
        self._from_source = {}
        self._columns = column_count(source.deck)
        self._build()

    # -- layout -------------------------------------------------------------

    def _build(self):
        deck = self._source.deck
        rows = self._source.card_rows()
        cards = {row: self._source.index(row, 0).data(CardRole) for row in rows}

        majors = [row for row in rows if cards[row].get("type") == "major_arcana"]
        self._build_majors(majors, cards)

        suits = deck.get_suits()
        if suits:
            minors = [row for row in rows if cards[row].get("suit")]
            self._row_kinds.append(ROW_GAP)
            self._build_minors(deck, suits, minors, cards)

        for cell, (kind, _, source_row) in self._cells.items():
            if kind == KIND_CARD:
                self._to_source[cell] = source_row
                self._from_source[source_row] = cell

    def _new_row(self, kind=ROW_CARDS):
        self._row_kinds.append(kind)
        return len(self._row_kinds) - 1

    def _put_card(self, row, column, source_row, card):
        self._cells[(row, column)] = (KIND_CARD, card.get("name", "Unknown"), source_row)

    def _build_majors(self, majors, cards):
        left = (self._columns - MAJOR_COLUMNS) // 2
        by_number, others = {}, []
        for source_row in majors:
            number = cards[source_row].get("number")
            if (
                isinstance(number, int)
                and 0 <= number < MAJOR_ARCANA_COUNT
                and number not in by_number
            ):
                by_number[number] = source_row
            else:
                others.append(source_row)

        def slot(number):
            if number == 0:
                return 0, left + FOOL_OFFSET
            return 1 + (number - 1) // MAJOR_COLUMNS, left + (number - 1) % MAJOR_COLUMNS

        for _ in range(1 + (MAJOR_ARCANA_COUNT - 1) // MAJOR_COLUMNS):
            self._new_row()
        for number in range(MAJOR_ARCANA_COUNT):
            row, column = slot(number)
            source_row = by_number.get(number)
            if source_row is None:
                self._cells[(row, column)] = (KIND_GHOST, "", None)
            else:
                self._put_card(row, column, source_row, cards[source_row])

        # Unnumbered, or numbered past XXI: sevens of their own, in number order
        others.sort(key=lambda r: (cards[r].get("number") is None, cards[r].get("number") or 0))
        for position, source_row in enumerate(others):
            if position % MAJOR_COLUMNS == 0:
                row = self._new_row()
            self._put_card(row, left + position % MAJOR_COLUMNS, source_row, cards[source_row])

    def _build_minors(self, deck, suits, minors, cards):
        # Rounded up, so a fifth suit takes the column right of the majors' last
        left = (self._columns - len(suits)) // 2

        row = self._new_row(ROW_LABELS)
        for position, suit in enumerate(suits):
            self._cells[(row, left + 1 + position)] = (
                KIND_LABEL,
                deck.get_display_suit_name(suit),
                None,
            )

        ranks = list(PIPS + COURTS)
        for source_row in minors:
            rank = cards[source_row].get("rank")
            if rank and rank not in ranks:
                ranks.append(rank)

        by_slot = {}
        for source_row in minors:
            card = cards[source_row]
            by_slot.setdefault((card.get("suit"), card.get("rank")), source_row)

        for rank in ranks:
            row = self._new_row()
            self._cells[(row, left)] = (KIND_LABEL, rank_label(deck, rank), None)
            for position, suit in enumerate(suits):
                column = left + 1 + position
                source_row = by_slot.get((suit, rank))
                if source_row is not None:
                    self._put_card(row, column, source_row, cards[source_row])
                elif suit in SUITS and rank in PIPS + COURTS:
                    self._cells[(row, column)] = (KIND_GHOST, "", None)

    # -- mapping ------------------------------------------------------------

    @property
    def deck(self):
        return self._source.deck

    def sourceModel(self):
        return self._source

    def row_kind(self, row):
        return self._row_kinds[row]

    def card_cells(self):
        """(row, column) of each card, row by row"""
        return sorted(self._to_source)

    def mapToSource(self, index):
        if not index.isValid():
            return QModelIndex()
        source_row = self._to_source.get((index.row(), index.column()))
        if source_row is None:
            return QModelIndex()
        return self._source.index(source_row, 0)

    def mapFromSource(self, source_index):
        if not source_index.isValid():
            return QModelIndex()
        cell = self._from_source.get(source_index.row())
        if cell is None:
            return QModelIndex()
        return self.index(*cell)

    # -- find ---------------------------------------------------------------

    def set_find(self, text):
        if text == self._find:
            return
        self._find = text
        for row, column in self.card_cells():
            index = self.index(row, column)
            self.dataChanged.emit(index, index, [DimmedRole])

    # -- the model ----------------------------------------------------------

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._row_kinds)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else self._columns

    def flags(self, index):
        if (index.row(), index.column()) not in self._to_source:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        cell = self._cells.get((index.row(), index.column()))
        if cell is None:
            return None
        kind, text, source_row = cell

        if kind == KIND_CARD:
            if role == DimmedRole:
                return bool(self._find) and not name_matches(text, self._find)
            return self._source.index(source_row, 0).data(role)

        if role == KindRole:
            return kind
        if kind != KIND_LABEL:
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return text
        suit_label = self._row_kinds[index.row()] == ROW_LABELS
        if role == Qt.ItemDataRole.FontRole:
            return typography.font(
                typography.Role.HEADING_3 if suit_label else typography.Role.SMALL
            )
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return SUIT_LABEL_ALIGNMENT if suit_label else RANK_LABEL_ALIGNMENT
        return None
