"""A saved canvas's pane, and what any kept reading needs to name its cards and decks"""

from collections import Counter
from datetime import datetime

from PyQt6.QtCore import (
    QDate,
    QDateTime,
    QTime,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.ui import units
from tarot_canvas.ui.canvas.reading_note import ReadingNote
from tarot_canvas.ui.canvas.reading_pane import (
    DATE_ICON,
    DateLine,
    FactLines,
    QuestionBox,
    fact_indent,
)
from tarot_canvas.ui.canvas.side_pane import SidePane
from tarot_canvas.ui.icons import CANVAS_ICON
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.utils.dates import format_qdatetime
from tarot_canvas.utils.logger import logger

# How long a kept reading stays still before it is written
AUTOSAVE_MS = 1000


def now():
    """The local time to the second, with its zone"""
    return datetime.now().astimezone().replace(microsecond=0)


def deck_key(deck):
    """How a reading names deck: its identifier, else its name"""
    if deck is None:
        return ""
    return deck.get_identifier() or deck.get_name()


def find_deck(key, decks):
    """The deck a reading names, by identifier, then by name, or None"""
    if not key:
        return None
    for deck in decks:
        if deck.get_identifier() == key:
            return deck
    return next((deck for deck in decks if deck.get_name() == key), None)


def resolve_deck(key, decks, reference):
    """The deck a reading names, else the reference deck"""
    deck = find_deck(key, decks)
    if deck is None:
        logger.warning(f"No deck {key!r} is installed, so the reading shows the reference deck")
        return reference
    if deck.get_identifier() != key:
        logger.info(f"Reading deck {key!r} matched by name")
    return deck


def default_deck(keys):
    """The deck most of a reading's cards name: the one the rest are told apart from"""
    return Counter(keys).most_common(1)[0][0] if keys else ""


def item_deck_key(item):
    """How a reading names canvas item's deck: as the reading it was restored from did, which
    holds while that deck is missing and another stands in, else by the deck it shows"""
    kept = getattr(item, "kept_card", None)
    if kept is not None and kept.deck:
        return kept.deck
    return deck_key(item.deck)


def reading_card(item, key, reversed=None, **fields):
    """A ReadingCard for canvas item, from deck key, where it lies now"""
    # What this version doesn't read rides on the card it was restored from
    kept = getattr(item, "kept_card", None)
    return ReadingCard(
        id=item.card_data["id"],
        reversed=item.is_reversed() if reversed is None else reversed,
        deck=key,
        x=item.pos().x(),
        y=item.pos().y(),
        z=item.zValue(),
        rotation=item.orient,
        extra=kept.extra if kept is not None else {},
        layout_extra=kept.layout_extra if kept is not None else {},
        **fields,
    )


def resolve_decks(cards, decks, reference):
    """{key: deck} for every deck ReadingCards cards name"""
    keys = dict.fromkeys(card.deck for card in cards)
    return {key: resolve_deck(key, decks, reference) for key in keys}


def cards_of(items, unrestored=()):
    """(default deck, ReadingCards) for canvas items in stacking order, then the ReadingCards that
    could not be laid out, as they were read"""
    ordered = [
        item for item in sorted(items, key=lambda item: item.zValue()) if item.card_data.get("id")
    ]
    keys = [item_deck_key(item) for item in ordered]
    cards = tuple(reading_card(item, key) for item, key in zip(ordered, keys, strict=True))
    return default_deck(keys + [card.deck for card in unrestored]), cards + tuple(unrestored)


def local_qdatetime(when):
    local = when.astimezone()
    return QDateTime(
        QDate(local.year, local.month, local.day), QTime(local.hour, local.minute, local.second)
    )


def reading_label(question, when):
    """The Question, else the Date"""
    return question or format_qdatetime(local_qdatetime(when))


class SavedCanvasPane(SidePane):
    """The Question, the Date and the note of a saved canvas"""

    def __init__(self, tab, path, reading):
        super().__init__()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        margin = units.LARGE_SPACING

        self.question_edit = QuestionBox(READINGS["question_hint"])
        self.question_edit.setText(reading.question)
        heading = QHBoxLayout()
        heading.setContentsMargins(margin, margin, margin, margin)
        heading.addWidget(self.question_edit, 1)
        self.body.addLayout(heading)

        self.date_line = DateLine(self, local_qdatetime(reading.date))
        self.date_text = self.date_line.text
        self.date_edit = self.date_line.editor
        self.facts = FactLines()
        # Where a spread reading names its spread
        self.spread_label = QLabel(READINGS["sandbox_canvas"])
        self.spread_label.setWordWrap(True)
        self.spread_label.setIndent(fact_indent())
        self.facts.add(QIcon.fromTheme(CANVAS_ICON), self.spread_label)
        self.facts.add(QIcon.fromTheme(DATE_ICON), self.date_text, self.date_edit, None)
        self.body.addWidget(self.facts)

        self.note = ReadingNote(tab, path, AUTOSAVE_MS)
        self.body.addWidget(self.note, 1)
        # Shift+Tab from the Question reaches the Date
        QWidget.setTabOrder(self.date_text, self.question_edit)
        QWidget.setTabOrder(self.question_edit, self.note.editor)


def new_reading():
    """A reading done now, with nothing in it yet"""
    return Reading(date=now())
