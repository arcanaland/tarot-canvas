"""One deck's cards in display order with a heading row before each section"""

from PyQt6.QtCore import QAbstractListModel, QSortFilterProxyModel, Qt

from tarot_canvas.models.card_ids import COURTS, PIPS
from tarot_canvas.models.card_search import CardTerms, Query
from tarot_canvas.models.deck_types import CardKind
from tarot_canvas.models.deck_writer import BACK
from tarot_canvas.ui.library.decks.model import back_image
from tarot_canvas.ui.strings import DECK_VIEW

KindRole = Qt.ItemDataRole.UserRole + 1
CardRole = Qt.ItemDataRole.UserRole + 2
# A heading's canonical suit, when the deck names the suit something else
CanonicalRole = Qt.ItemDataRole.UserRole + 3
# The back's image, or None
BackPathRole = Qt.ItemDataRole.UserRole + 4
# A card's canonical ID, or BACK; what the deck writer calls the slot
SlotIdRole = Qt.ItemDataRole.UserRole + 5
# A created deck's slot with no image yet; never true in a deck not created here
EmptySlotRole = Qt.ItemDataRole.UserRole + 6

KIND_HEADING = "heading"
KIND_NOTE = "note"
KIND_CARD = "card"
KIND_BACK = "back"


def is_slot(index):
    """A card or the back, in this model or a view's model over it"""
    return index.isValid() and index.data(KindRole) in (KIND_CARD, KIND_BACK)


RANK_ORDER = {rank: position for position, rank in enumerate(PIPS + COURTS)}


def _major_key(card):
    return (card.position is None, card.position or 0)


def _rank_key(card):
    return RANK_ORDER.get(card.rank_key, len(RANK_ORDER))


def shown_suits(deck):
    return [suit for suit in deck.suits if not suit.excluded]


def canonical_suit(suit):
    """The specification's name for suit, or None when the deck's name is already it"""
    canonical = suit.key.capitalize()
    return None if suit.name.casefold() == canonical.casefold() else canonical


def canonical_heading(name, canonical):
    """A suit heading as one string: the deck's name, then the canonical one"""
    if canonical is None:
        return name
    return f"{name} {DECK_VIEW['canonical_suit'].format(suit=canonical)}"


def display_rows(deck, back=False):
    """(kind, text, card, canonical) per row: the majors, then each suit under its heading,
    then the back if asked for

    canonical is set only on the heading of a suit the deck renames.
    """
    rows = []
    majors = sorted(deck.cards_of_kind(CardKind.MAJOR), key=_major_key)
    if majors:
        rows.append((KIND_HEADING, DECK_VIEW["major_arcana"], None, None))
        rows.extend((KIND_CARD, card.display_name, card, None) for card in majors)

    suits = shown_suits(deck)
    if not suits:
        reason = deck.exclusion_reason
        if reason:
            rows.append((KIND_NOTE, DECK_VIEW["note"].format(reason=reason), None, None))

    for suit in suits:
        cards = sorted(deck.cards_in_suit(suit.key), key=_rank_key)
        if not cards:
            continue
        rows.append((KIND_HEADING, suit.name, None, canonical_suit(suit)))
        rows.extend((KIND_CARD, card.display_name, card, None) for card in cards)

    if back:
        rows.append((KIND_HEADING, DECK_VIEW["back"], None, None))
        rows.append((KIND_BACK, DECK_VIEW["back"], None, None))
    return rows


class CardModel(QAbstractListModel):
    """A deck's cards"""

    def __init__(self, deck, parent=None, editable=False):
        super().__init__(parent)
        self._editable = editable
        self._deck = deck
        self._rows = display_rows(deck, back=editable)
        self._back = back_image(deck) if editable else None
        self._terms = {}

    @property
    def deck(self):
        return self._deck

    def set_deck(self, deck):
        self.beginResetModel()
        self._deck = deck
        self._rows = display_rows(deck, back=self._editable)
        self._back = back_image(deck) if self._editable else None
        self._terms = {}
        self.endResetModel()

    def back_row(self):
        return next(
            (row for row, (kind, *_) in enumerate(self._rows) if kind == KIND_BACK),
            None,
        )

    def row_of(self, slot_id):
        """The row of the card, or the back, the writer calls slot_id; None if there is none"""
        for row in range(len(self._rows)):
            if self._slot_id(row) == slot_id:
                return row
        return None

    def _slot_id(self, row):
        kind, _text, card, _canonical = self._rows[row]
        if kind == KIND_BACK:
            return BACK
        return card.canonical_id if kind == KIND_CARD else None

    def card_rows(self):
        """Row of each card, in order"""
        return [row for row, (kind, *_) in enumerate(self._rows) if kind == KIND_CARD]

    def matches(self, row, query):
        """Whether the card at row is found by query"""
        if self._rows[row][0] != KIND_CARD:
            return False
        terms = self._terms.get(row)
        if terms is None:
            terms = self._terms[row] = CardTerms(self._rows[row][2], self._deck.metadata.name)
        return terms.tier(query) is not None

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
        if not index.isValid() or self._rows[index.row()][0] not in (KIND_CARD, KIND_BACK):
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        kind, text, card, canonical = self._rows[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return text
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return canonical_heading(text, canonical)
        if role == KindRole:
            return kind
        if role == CanonicalRole:
            return canonical
        if role == SlotIdRole:
            return self._slot_id(index.row())
        if role == EmptySlotRole:
            if not self._editable or kind not in (KIND_CARD, KIND_BACK):
                return False
            return not (self._back if kind == KIND_BACK else card.default_image())
        if kind == KIND_BACK:
            if role == BackPathRole:
                return self._back
            if role == Qt.ItemDataRole.ToolTipRole:
                return text
            return None
        if card is None:
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            # The cell elides it
            return text
        if role == CardRole:
            return card
        return None


class CardFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._find = Query("")

    def set_find(self, text):
        self._find = Query(text)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if not self._find:
            return True

        def found(row):
            return model.matches(row, self._find)

        kind = model.index(source_row, 0, source_parent).data(KindRole)
        if kind == KIND_CARD:
            return found(source_row)
        if kind == KIND_HEADING:
            return any(found(row) for row in model.section_card_rows(source_row))
        return False
