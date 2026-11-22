"""A list model over the loaded decks, then the catalog's decks not yet installed"""

from PyQt6.QtCore import QAbstractListModel, QLocale, QSortFilterProxyModel, Qt, pyqtSlot

from tarot_canvas.models import library_curation
from tarot_canvas.models.catalog import available_entries
from tarot_canvas.models.deck_types import CardKind
from tarot_canvas.models.deck_writer import BACK
from tarot_canvas.settings import get_recent_decks
from tarot_canvas.ui.catalog.client import deck_catalog
from tarot_canvas.ui.catalog.downloads import DeckState, deck_downloads
from tarot_canvas.ui.library.roles import (
    SORT_COUNT,
    SORT_NAME,
    CoverPathRole,
    DimmedRole,
    PinnedRole,
    SubtitleRole,
    ToggleRole,
)
from tarot_canvas.ui.strings import DECK_VIEW, LIBRARY, SPREADS, failure_text

DeckRole = Qt.ItemDataRole.UserRole + 1
AuthorRole = Qt.ItemDataRole.UserRole + 4
CardCountRole = Qt.ItemDataRole.UserRole + 5
DeckPathRole = Qt.ItemDataRole.UserRole + 6
SearchRole = Qt.ItemDataRole.UserRole + 7
StateRole = Qt.ItemDataRole.UserRole + 8
ProgressRole = Qt.ItemDataRole.UserRole + 9
EntryRole = Qt.ItemDataRole.UserRole + 10
HandmadeRole = Qt.ItemDataRole.UserRole + 11  # made in this app
DeckHiddenRole = Qt.ItemDataRole.UserRole + 12

# The grid's order, under every sort
PINNED_BUCKET, INSTALLED_BUCKET, TOGGLE_BUCKET, GHOST_BUCKET = range(4)

SORT_AUTHOR = "author"
SORT_RECENT = "recent"


def deck_cover_path(deck):
    """The Fool if the deck has one, else any major arcana card with art."""
    major_arcana = deck.cards_of_kind(CardKind.MAJOR)
    for card in major_arcana:
        if card.position == 0 and card.default_image():
            return card.default_image()
    for card in major_arcana:
        if card.default_image():
            return card.default_image()
    return None


def deck_author(deck):
    return deck.metadata.artist or LIBRARY["unknown_author"]


def is_majors_only(deck):
    return bool(deck.cards_of_kind(CardKind.MAJOR)) and not deck.cards_of_kind(CardKind.MINOR)


def empty_cards(deck):
    """The deck's cards with no image, in deck order"""
    return [card for card in deck.cards if not card.default_image()]


def back_image(deck):
    """The classic back's image, or None"""
    return deck.get_card_backs()[0].get("classic")


def fill_progress(deck):
    """(placed, expected) for a handmade deck's cards, not its back"""
    return sum(1 for card in deck.cards if card.default_image()), len(deck.cards)


def placed_minors(deck):
    """How many of the deck's minors have an image"""
    return sum(1 for card in deck.cards_of_kind(CardKind.MINOR) if card.default_image())


def filled_slots(deck):
    """The card IDs with an image, and the back's if it has one"""
    filled = {card.canonical_id for card in deck.cards if card.default_image()}
    if back_image(deck):
        filled.add(BACK)
    return filled


def deck_subtitle(deck, abbreviated=False, handmade=False):
    parts = [deck_author(deck)]
    if is_majors_only(deck):
        parts.append(LIBRARY["majors_short"] if abbreviated else LIBRARY["majors_only"])
    if handmade:
        placed, expected = fill_progress(deck)
        parts.append(DECK_VIEW["fill_count"].format(placed=placed, expected=expected))

    return " • ".join(parts)


class DeckListModel(QAbstractListModel):
    """Installed decks, the hidden ones' toggle, then a ghost row per catalog entry
    no installed deck matches."""

    def __init__(self, decks=None, parent=None, entries=None):
        super().__init__(parent)
        self._show_hidden = False  # for this session: Show isn't remembered
        self._entries = list(entries or [])
        self._take_decks(decks)

    def _take_decks(self, decks):
        self._decks = list(decks or [])
        self._handmade = [library_curation.is_handmade(deck.root_path) for deck in self._decks]
        pins, hides = library_curation.deck_pins(), library_curation.deck_hides()
        self._pinned = [deck.metadata.identifier in pins for deck in self._decks]
        self._hidden = [deck.metadata.identifier in hides for deck in self._decks]
        self._hidden_count = sum(self._hidden)
        self._ghosts = available_entries(self._entries, self._decks)

    def shows_hidden(self):
        return self._show_hidden

    def toggle_hidden(self):
        # A reset, so the activation that follows a click finds no row to toggle back
        self.beginResetModel()
        self._show_hidden = not self._show_hidden
        self.endResetModel()

    def set_decks(self, decks):
        self.beginResetModel()
        self._take_decks(decks)
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
                index = self.index(self._first_ghost() + offset, 0)
                self.dataChanged.emit(index, index)

    def _first_ghost(self):
        return len(self._decks) + (1 if self._hidden_count else 0)

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return self._first_ghost() + len(self._ghosts)

    def flags(self, index):
        if index.isValid() and self._is_toggle(index.row()):
            # Clicked or Entered, never selected
            return Qt.ItemFlag.ItemIsEnabled
        return super().flags(index)

    def _is_toggle(self, row):
        return len(self._decks) <= row < self._first_ghost()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return None

        if self._is_toggle(index.row()):
            return self._toggle_data(role)
        if index.row() >= self._first_ghost():
            return self._ghost_data(self._ghosts[index.row() - self._first_ghost()], role)

        deck = self._decks[index.row()]
        handmade = self._handmade[index.row()]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return deck.metadata.name
        if role == DeckRole:
            return deck
        if role == SubtitleRole:
            return deck_subtitle(deck, handmade=handmade)
        if role == CoverPathRole:
            return deck_cover_path(deck)
        if role == AuthorRole:
            return deck_author(deck)
        if role == CardCountRole:
            return fill_progress(deck)[0] if handmade else len(deck.cards)
        if role == DeckPathRole:
            return deck.root_path
        if role == SearchRole:
            return f"{deck.metadata.name} {deck_author(deck)}"
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [deck.metadata.name, deck_subtitle(deck, handmade=handmade)]
            if handmade:
                lines.append(LIBRARY["handmade_tooltip"])
            return "\n".join(lines)
        if role == StateRole:
            return DeckState.INSTALLED
        if role == HandmadeRole:
            return handmade
        if role == PinnedRole:
            return self._pinned[index.row()]
        if role in (DeckHiddenRole, DimmedRole):
            return self._hidden[index.row()]
        return None

    def _toggle_data(self, role):
        if role == ToggleRole:
            return True
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            key = "hidden_collapse" if self._show_hidden else "hidden_show"
            return SPREADS[key].format(count=self._hidden_count)
        return None

    @staticmethod
    def _ghost_data(entry, role):
        # everything but DeckRole and no DeckPathRole
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
    """Case-insensitive search over name and author, which also finds hidden decks."""

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

    def sort_key(self):
        return self._sort_key

    def sort_order(self):
        if self._sort_key == SORT_RECENT:
            return Qt.SortOrder.DescendingOrder
        return Qt.SortOrder.AscendingOrder

    def refresh_recent(self):
        if self._sort_key == SORT_RECENT:
            self._recent = get_recent_decks()
            self.invalidate()

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        index = model.index(row, 0, parent)
        searching = bool(self.filterRegularExpression().pattern())
        if index.data(ToggleRole):
            return not searching
        if not searching and index.data(DeckHiddenRole) and not model.shows_hidden():
            return False
        return super().filterAcceptsRow(row, parent)

    def lessThan(self, left, right):
        # the buckets keep their order, whichever way the sort runs
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
        if index.data(EntryRole) is not None:
            return GHOST_BUCKET
        if index.data(ToggleRole):
            return TOGGLE_BUCKET
        return PINNED_BUCKET if index.data(PinnedRole) else INSTALLED_BUCKET

    def _compare_with_name_tiebreak(self, left_value, right_value, left, right):
        if left_value == right_value:
            name_order = self._name_of(left) < self._name_of(right)

            if self.sort_order() == Qt.SortOrder.DescendingOrder:
                return not name_order

            return name_order
        return left_value < right_value

    def _name_of(self, index):
        return (self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole) or "").casefold()
