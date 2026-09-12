"""A list model over the loaded decks, then the catalog's decks not yet installed"""

from PyQt6.QtCore import QAbstractListModel, QLocale, QSortFilterProxyModel, Qt, pyqtSlot

from tarot_canvas.models.catalog import available_entries
from tarot_canvas.settings import get_recent_decks
from tarot_canvas.ui.library.catalog_client import deck_catalog
from tarot_canvas.ui.library.deck_downloads import DeckState, deck_downloads
from tarot_canvas.ui.windows.deck_download_dialog import failure_text

DeckRole = Qt.ItemDataRole.UserRole + 1
SubtitleRole = Qt.ItemDataRole.UserRole + 2
CoverPathRole = Qt.ItemDataRole.UserRole + 3
AuthorRole = Qt.ItemDataRole.UserRole + 4
CardCountRole = Qt.ItemDataRole.UserRole + 5
DeckPathRole = Qt.ItemDataRole.UserRole + 6
SearchRole = Qt.ItemDataRole.UserRole + 7
StateRole = Qt.ItemDataRole.UserRole + 8
ProgressRole = Qt.ItemDataRole.UserRole + 9
EntryRole = Qt.ItemDataRole.UserRole + 10

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
    fields = deck._metadata.get("deck", {})
    return fields.get("artist") or fields.get("author") or UNKNOWN_AUTHOR


def is_majors_only(deck):
    return bool(deck.get_cards_by_type("major_arcana")) and not deck.get_cards_by_type(
        "minor_arcana"
    )


def deck_subtitle(deck, abbreviated=False):
    parts = [deck_author(deck)]
    if is_majors_only(deck):
        parts.append("majors" if abbreviated else "majors only")

    return " • ".join(parts)


class DeckListModel(QAbstractListModel):
    """Installed decks, then a ghost row per catalog entry no installed deck matches."""

    def __init__(self, decks=None, parent=None, entries=None):
        super().__init__(parent)
        self._decks = list(decks or [])
        self._entries = list(entries or [])
        self._ghosts = available_entries(self._entries, self._decks)

    def set_decks(self, decks):
        self.beginResetModel()
        self._decks = list(decks or [])
        self._ghosts = available_entries(self._entries, self._decks)
        self.endResetModel()

    def set_entries(self, entries):
        self.beginResetModel()
        self._entries = list(entries or [])
        self._ghosts = available_entries(self._entries, self._decks)
        self.endResetModel()

    @pyqtSlot(str)
    def download_changed(self, slug):
        self._ghosts_changed(lambda entry: entry.slug == slug)

    @pyqtSlot(str)
    def cover_ready(self, url):
        self._ghosts_changed(lambda entry: entry.cover == url)

    def _ghosts_changed(self, matches):
        for offset, entry in enumerate(self._ghosts):
            if matches(entry):
                index = self.index(len(self._decks) + offset, 0)
                self.dataChanged.emit(index, index)

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._decks) + len(self._ghosts)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return None

        if index.row() >= len(self._decks):
            return self._ghost_data(self._ghosts[index.row() - len(self._decks)], role)

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
        if role == StateRole:
            return DeckState.INSTALLED
        return None

    @staticmethod
    def _ghost_data(entry, role):
        # No DeckRole and no DeckPathRole: the open paths skip a row without a deck
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return entry.name
        if role == SubtitleRole:
            return QLocale().formattedDataSize(entry.package_size)
        if role == CoverPathRole:
            return deck_catalog().cover_path(entry)
        if role == AuthorRole:
            return entry.artist
        if role == CardCountRole:
            return entry.card_count
        if role == SearchRole:
            return f"{entry.name} {entry.artist}"
        if role == Qt.ItemDataRole.ToolTipRole:
            failure = deck_downloads().failure(entry.slug)
            if failure is not None:
                return failure_text(failure)
            return f"{entry.name}\n{QLocale().formattedDataSize(entry.package_size)}"
        if role == StateRole:
            return deck_downloads().state(entry.slug)
        if role == ProgressRole:
            return deck_downloads().progress(entry.slug)
        if role == EntryRole:
            return entry
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
        # Ghosts trail the installed decks whichever way the key sorts. Qt sorts
        # descending by inverting lessThan, so invert the bucket order to match.
        left_bucket, right_bucket = self._bucket(left), self._bucket(right)
        if left_bucket != right_bucket:
            if self.sort_order() == Qt.SortOrder.DescendingOrder:
                return left_bucket > right_bucket
            return left_bucket < right_bucket

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

    def _bucket(self, index):
        return 0 if self.sourceModel().data(index, EntryRole) is None else 1

    def _compare_with_name_tiebreak(self, left_value, right_value, left, right):
        if left_value == right_value:
            name_order = self._name_of(left) < self._name_of(right)

            if self.sort_order() == Qt.SortOrder.DescendingOrder:
                return not name_order

            return name_order
        return left_value < right_value

    def _name_of(self, index):
        return (self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole) or "").casefold()
