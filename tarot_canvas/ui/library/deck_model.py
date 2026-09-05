"""A list model over the loaded decks"""

from PyQt6.QtCore import QAbstractListModel, QSortFilterProxyModel, Qt

from tarot_canvas.settings import get_recent_decks

DeckRole = Qt.ItemDataRole.UserRole + 1
SubtitleRole = Qt.ItemDataRole.UserRole + 2
CoverPathRole = Qt.ItemDataRole.UserRole + 3
AuthorRole = Qt.ItemDataRole.UserRole + 4
CardCountRole = Qt.ItemDataRole.UserRole + 5
DeckPathRole = Qt.ItemDataRole.UserRole + 6
SearchRole = Qt.ItemDataRole.UserRole + 7

SORT_NAME = "name"
SORT_AUTHOR = "author"
SORT_COUNT = "count"
SORT_RECENT = "recent"

UNKNOWN_AUTHOR = "Unknown"


def deck_cover_path(deck):
    """The Fool if the deck has one, else any major arcana card with art."""
    major_arcana = deck.get_cards_by_type("major_arcana")
    for card in major_arcana:
        if card.get("number") == 0 and card.get("image"):
            return card.get("image")
    for card in major_arcana:
        if card.get("image"):
            return card.get("image")
    return None


def deck_author(deck):
    return deck._metadata.get("deck", {}).get("author", UNKNOWN_AUTHOR)


def is_majors_only(deck):
    return bool(deck.get_cards_by_type("major_arcana")) and not deck.get_cards_by_type(
        "minor_arcana"
    )


def deck_subtitle(deck, abbreviated=False):
    count = len(deck.get_all_cards())
    parts = [f"{count} cards"]
    if is_majors_only(deck):
        parts.append("majors" if abbreviated else "majors only")
    if not abbreviated:
        parts.append(deck_author(deck))
    return " • ".join(parts)


class DeckListModel(QAbstractListModel):
    def __init__(self, decks=None, parent=None):
        super().__init__(parent)
        self._decks = list(decks or [])

    def set_decks(self, decks):
        self.beginResetModel()
        self._decks = list(decks or [])
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._decks)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._decks):
            return None

        deck = self._decks[index.row()]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return deck.get_name()
        if role == DeckRole:
            return deck
        if role == SubtitleRole:
            return deck_subtitle(deck)
        if role == CoverPathRole:
            return deck_cover_path(deck)
        if role == AuthorRole:
            return deck_author(deck)
        if role == CardCountRole:
            return len(deck.get_all_cards())
        if role == DeckPathRole:
            return deck.deck_path
        if role == SearchRole:
            return f"{deck.get_name()} {deck_author(deck)}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{deck.get_name()}\n{deck_subtitle(deck)}"
        return None


class DeckFilterProxyModel(QSortFilterProxyModel):
    """Case-insensitive search over name and author."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterRole(SearchRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(True)
        self._sort_key = SORT_NAME
        self._recent = {}

    def set_sort_key(self, key):
        valid = (SORT_NAME, SORT_AUTHOR, SORT_COUNT, SORT_RECENT)
        self._sort_key = key if key in valid else SORT_NAME
        if self._sort_key == SORT_RECENT:
            self._recent = get_recent_decks()
        self.invalidate()
        self.sort(0, self.sort_order())

    def sort_order(self):
        if self._sort_key == SORT_RECENT:
            return Qt.SortOrder.DescendingOrder
        return Qt.SortOrder.AscendingOrder

    def refresh_recent(self):
        if self._sort_key == SORT_RECENT:
            self._recent = get_recent_decks()
            self.invalidate()

    def lessThan(self, left, right):
        model = self.sourceModel()
        if self._sort_key == SORT_AUTHOR:
            return self._compare_with_name_tiebreak(
                model.data(left, AuthorRole), model.data(right, AuthorRole), left, right
            )
        if self._sort_key == SORT_COUNT:
            return self._compare_with_name_tiebreak(
                model.data(left, CardCountRole), model.data(right, CardCountRole), left, right
            )
        if self._sort_key == SORT_RECENT:
            return self._compare_with_name_tiebreak(
                self._recent.get(model.data(left, DeckPathRole), 0.0),
                self._recent.get(model.data(right, DeckPathRole), 0.0),
                left,
                right,
            )
        return self._name_of(left) < self._name_of(right)

    def _compare_with_name_tiebreak(self, left_value, right_value, left, right):
        if left_value == right_value:
            name_order = self._name_of(left) < self._name_of(right)

            if self.sort_order() == Qt.SortOrder.DescendingOrder:
                return not name_order

            return name_order
        return left_value < right_value

    def _name_of(self, index):
        return (self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole) or "").casefold()
