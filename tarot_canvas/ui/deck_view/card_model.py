"""One deck's cards in display order with a heading row before each section"""

from PyQt6.QtCore import QAbstractListModel, QSortFilterProxyModel, Qt

from tarot_canvas.models.card_ids import COURTS, PIPS

KindRole = Qt.ItemDataRole.UserRole + 1
CardRole = Qt.ItemDataRole.UserRole + 2
ImagesRole = Qt.ItemDataRole.UserRole + 3
ImageRole = Qt.ItemDataRole.UserRole + 4

KIND_HEADING = "heading"
KIND_NOTE = "note"
KIND_CARD = "card"

MAJOR_ARCANA_HEADING = "Major Arcana"

RANK_ORDER = {rank: position for position, rank in enumerate(PIPS + COURTS)}


def _major_key(card):
    number = card.get("number")
    return (number is None, number or 0)


def _rank_key(card):
    return RANK_ORDER.get(card.get("rank"), len(RANK_ORDER))


def display_rows(deck):
    """(kind, text, card) per row: the majors, then each suit, each under its heading"""
    rows = []
    majors = sorted(deck.get_cards_by_type("major_arcana"), key=_major_key)
    if majors:
        rows.append((KIND_HEADING, MAJOR_ARCANA_HEADING, None))
        rows.extend((KIND_CARD, card.get("name", "Unknown"), card) for card in majors)

    suits = deck.get_suits()
    if not suits:
        reason = deck.get_exclusion_reason()
        if reason:
            rows.append((KIND_NOTE, f"Note: {reason}", None))

    for suit in suits:
        cards = sorted(deck.get_cards_by_suit(suit), key=_rank_key)
        if not cards:
            continue
        rows.append((KIND_HEADING, deck.get_display_suit_name(suit), None))
        rows.extend((KIND_CARD, card.get("name", "Unknown"), card) for card in cards)
    return rows


class CardModel(QAbstractListModel):
    """A deck's cards"""

    def __init__(self, deck, parent=None):
        super().__init__(parent)
        self._deck = deck
        self._rows = display_rows(deck)

    @property
    def deck(self):
        return self._deck

    def card_rows(self):
        """Row of each card, in order"""
        return [row for row, (kind, _, _) in enumerate(self._rows) if kind == KIND_CARD]

    def section_card_rows(self, row):
        """Rows of the cards under the heading at row"""
        rows = []
        for below in range(row + 1, len(self._rows)):
            kind = self._rows[below][0]
            if kind == KIND_HEADING:
                break
            if kind == KIND_CARD:
                rows.append(below)
        return rows

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def flags(self, index):
        if not index.isValid() or self._rows[index.row()][0] != KIND_CARD:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        kind, text, card = self._rows[index.row()]

        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.AccessibleTextRole,
        ):
            return text
        if role == KindRole:
            return kind
        if card is None:
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            # The cell elides it
            return text
        if role == CardRole:
            return card
        if role == ImagesRole:
            return card.get("images", {})
        if role == ImageRole:
            return card.get("image")
        return None


class CardFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if not self.filterRegularExpression().pattern():
            return True
        name_matches = super().filterAcceptsRow
        kind = model.index(source_row, 0, source_parent).data(KindRole)
        if kind == KIND_CARD:
            return name_matches(source_row, source_parent)
        if kind == KIND_HEADING:
            return any(
                name_matches(row, source_parent) for row in model.section_card_rows(source_row)
            )
        return False
