"""A saved canvas's pane, and what any kept reading needs to name its cards and decks"""

from collections import Counter
from datetime import datetime

from PyQt6.QtCore import (
    QDate,
    QDateTime,
    QEvent,
    QPointF,
    Qt,
    QTime,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QIcon, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionFocusRect,
    QStylePainter,
    QWidget,
)

from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.ui.canvas.reading_note import ReadingNote
from tarot_canvas.ui.canvas.reading_pane import DATE_ICON, FactLines, QuestionBox, fact_indent
from tarot_canvas.ui.canvas.side_pane import SidePane
from tarot_canvas.ui.library import units
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


def reading_card(item, key, reversed=None, **fields):
    """A ReadingCard for canvas item, from deck key, where it lies now"""
    return ReadingCard(
        id=item.card_data["id"],
        reversed=item.is_reversed() if reversed is None else reversed,
        deck=key,
        x=item.pos().x(),
        y=item.pos().y(),
        z=item.zValue(),
        rotation=item.orient,
        **fields,
    )


def resolve_decks(cards, decks, reference):
    """{key: deck} for every deck ReadingCards cards name"""
    keys = dict.fromkeys(card.deck for card in cards)
    return {key: resolve_deck(key, decks, reference) for key in keys}


def cards_of(items):
    """(default deck, ReadingCards) for canvas items, in stacking order"""
    ordered = [
        item for item in sorted(items, key=lambda item: item.zValue()) if item.card_data.get("id")
    ]
    keys = [deck_key(item.deck) for item in ordered]
    cards = tuple(reading_card(item, key) for item, key in zip(ordered, keys, strict=True))
    return default_deck(keys), cards


def local_qdatetime(when):
    local = when.astimezone()
    return QDateTime(
        QDate(local.year, local.month, local.day), QTime(local.hour, local.minute, local.second)
    )


def reading_label(question, when):
    """The Question, else the Date"""
    return question or format_qdatetime(local_qdatetime(when))


class FactButton(QLabel):
    """A fact that is also a button: a click, Return or Space activates it"""

    activated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.activated.emit()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hasFocus():
            painter = QStylePainter(self)
            option = QStyleOptionFocusRect()
            option.initFrom(self)
            option.backgroundColor = self.palette().window().color()
            painter.drawPrimitive(QStyle.PrimitiveElement.PE_FrameFocusRect, option)


def open_calendar(edit):
    """Open edit's calendar as a click on its arrow does, which is the only way Qt has"""
    option = QStyleOptionComboBox()
    option.initFrom(edit)
    option.editable = True
    option.subControls = QStyle.SubControl.SC_All
    arrow = edit.style().subControlRect(
        QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, edit
    )
    at = QPointF(arrow.center())
    left = Qt.MouseButton.LeftButton
    for kind, held in (
        (QEvent.Type.MouseButtonPress, left),
        (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
    ):
        event = QMouseEvent(
            kind, at, edit.mapToGlobal(at), left, held, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(edit, event)


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

        # The Date reads as a fact, and is edited only when asked to be
        when = local_qdatetime(reading.date)
        self.date_text = FactButton()
        self.date_text.setIndent(fact_indent())
        self.date_text.setToolTip(READINGS["date_tooltip"])
        self.date_text.activated.connect(self.edit_date)
        self.date_edit = QDateTimeEdit(when)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setToolTip(READINGS["date_tooltip"])
        self.date_edit.hide()
        self.date_edit.dateTimeChanged.connect(self._show_date)
        self.date_edit.editingFinished.connect(self._date_edited)
        QApplication.instance().focusChanged.connect(self._focus_moved)
        self._show_date(when)
        self.facts = FactLines()
        self.facts.add(QIcon.fromTheme(DATE_ICON), self.date_text, self.date_edit, None)
        self.body.addWidget(self.facts)

        self.note = ReadingNote(tab, path, AUTOSAVE_MS)
        self.body.addWidget(self.note, 1)
        # Shift+Tab from the Question reaches the Date
        QWidget.setTabOrder(self.date_text, self.question_edit)
        QWidget.setTabOrder(self.question_edit, self.note.editor)

    @pyqtSlot(QDateTime)
    def _show_date(self, when):
        text = format_qdatetime(when)
        self.date_text.setText(text)
        self.date_text.setAccessibleName(text)

    @pyqtSlot()
    def edit_date(self):
        """Swap the Date's text for its editor, with the calendar open"""
        self.date_text.hide()
        self.date_edit.show()
        self.facts.layout().activate()
        self.date_edit.setFocus()
        open_calendar(self.date_edit)

    @pyqtSlot()
    def _date_edited(self):
        # The calendar taking focus ends an edit too, but the user isn't done
        if QApplication.activePopupWidget() is None:
            self._close_date_edit()

    @pyqtSlot(QWidget, QWidget)
    def _focus_moved(self, _old, new):
        """Focus leaving the editor and its calendar for another widget closes it"""
        if new is None:
            return
        for inside in (self.date_edit, self.date_edit.calendarWidget()):
            if new is inside or inside.isAncestorOf(new):
                return
        self._close_date_edit()

    def _close_date_edit(self):
        if self.date_edit.isHidden():
            return
        refocus = self.date_edit.hasFocus()
        self.date_edit.hide()
        self.date_text.show()
        if refocus:
            self.date_text.setFocus()


def new_reading():
    """A reading done now, with nothing in it yet"""
    return Reading(date=now())
