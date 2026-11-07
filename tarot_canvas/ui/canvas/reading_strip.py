"""The band under a reading's canvas: its transport, centred, and View's actions at the end. And
the keys that deal, turn and step, on the canvas and the pane's list."""

from PyQt6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QPushButton, QToolButton, QWidget

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.placement import Phase
from tarot_canvas.ui.canvas.reading_card import is_face_down
from tarot_canvas.ui.canvas.reading_marks import next_gilt
from tarot_canvas.ui.strings import COMMANDS, READINGS

BAR_PAD_PX = 6
BAR_RADIUS_PX = 12
BAR_ALPHA = 235
BAR_ICON_PX = 22
DOT_PX = 10
DOT_GAP_PX = 7
DEAL_MIN_WIDTH_PX = 180
DEAL_MIN_HEIGHT_PX = 40
# The band under the canvas the bar sits in: the canvas ends above it, so no card is ever under it
STRIP_PAD_PX = 8
STRIP_PX = DEAL_MIN_HEIGHT_PX + 2 * BAR_PAD_PX + 2 * STRIP_PAD_PX
# Narrower than this and the dots become one progress line
LINE_MIN_WIDTH_PX = 80
LINE_HEIGHT_PX = 6
# A dot for a card not yet on the table, as a share of a face-down one's
UNLANDED_ALPHA = 0.35

# Deal's icon, and the same button's when every position was filled by hand and there is nothing
# to deal: KDE's confirm, as its wizards' Finish has
DEAL_ICON = "media-playback-start"
FINISH_ICON = "dialog-ok-apply"

REVEAL_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
OPEN_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)
# The transport's keys, as the card view's Previous, Next, First and Last. The canvas's only: the
# list has its own Home and End, and moves its rows with Up and Down
TURN_KEY = Qt.Key.Key_Right
TURN_ALL_KEY = Qt.Key.Key_End
STEP_KEYS = {
    Qt.Key.Key_Left: "previous",
    Qt.Key.Key_Right: "next",
    Qt.Key.Key_Home: "first",
    Qt.Key.Key_End: "last",
}


def key_names(*keys):
    return ", ".join(
        QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText) for key in keys
    )


def _plain(event):
    """A key pressed with no modifier but the keypad's"""
    return not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier


class RevealKeys(QObject):
    """Enter or Space on the canvas or the pane's list deals, then turns the next card. On the
    list, Enter on a row whose card is face-up opens that card instead. On the canvas, Right
    turns too and End reveals the rest; once all are turned, Left, Right, Home and End step
    through the positions.

    Watched on those two only, so a space typed into the Question is still a space
    """

    def __init__(self, reading, canvas, rows):
        super().__init__(reading)
        self.reading = reading
        self.canvas = canvas
        self.rows = rows
        canvas.installEventFilter(self)
        rows.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.KeyPress or not _plain(event):
            return False
        reading = self.reading
        key = event.key()
        if watched is self.canvas and self._transport(key, event.isAutoRepeat()):
            return True
        # Enter on a turned card's row opens it, as a double-click does; Space still turns
        if watched is self.rows and key in OPEN_KEYS and reading.open_current_row():
            return True
        if key in REVEAL_KEYS and (reading.phase is Phase.STAGED or reading.can_turn()):
            # A held key deals or turns once, not a run
            if not event.isAutoRepeat():
                if reading.phase is Phase.STAGED:
                    reading.deal()
                else:
                    reading.turn_next()
            return True
        return False

    def _transport(self, key, repeat):
        """The canvas's transport keys; whether key was one"""
        reading = self.reading
        if reading.can_turn() and key in (TURN_KEY, TURN_ALL_KEY):
            if not repeat:
                if key == TURN_KEY:
                    reading.turn_next()
                else:
                    reading.turn_all()
            return True
        if reading.phase is Phase.READ and key in STEP_KEYS:
            reading.step(STEP_KEYS[key])
            return True
        return False


class ProgressDots(QWidget):
    """One dot per filled position, in turn order: filled once turned, gilt when next (or, once all
    are turned, when stepped to), hollow while face-down, faint until it has landed. Too many for
    the width, and they fold into one progress line"""

    def __init__(self, reading, parent=None):
        super().__init__(parent)
        self.reading = reading
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def sizeHint(self):
        count = max(1, len(self.reading.turn_order()))
        return QSize(count * DOT_PX + (count - 1) * DOT_GAP_PX + 4, DOT_PX + 8)

    def minimumSizeHint(self):
        return QSize(min(self.sizeHint().width(), LINE_MIN_WIDTH_PX), DOT_PX + 8)

    def as_line(self):
        """Too many positions for a dot each, at this width"""
        return self.width() < self.sizeHint().width()

    def _dot_rect(self, index):
        top = (self.height() - DOT_PX) / 2.0
        return QRectF(2 + index * (DOT_PX + DOT_GAP_PX), top, DOT_PX, DOT_PX)

    def _segment(self, index, count):
        width = (self.width() - 4) / max(1, count)
        top = (self.height() - LINE_HEIGHT_PX) / 2.0
        return QRectF(2 + index * width, top, width, LINE_HEIGHT_PX)

    def _marked(self):
        """The card whose dot is gilt: the next to turn, or the one stepped to"""
        return self.reading.next_card() or self.reading.stepped_card()

    def colours(self, card):
        """(fill, outline) of card's dot; None for neither"""
        palette = self.palette()
        if card is self._marked():
            gilt = next_gilt(palette)
            return gilt, gilt
        if not is_face_down(card):
            return palette.windowText().color(), None
        colour = QColor(palette.placeholderText().color())
        if not self.reading.has_landed(card):
            colour.setAlphaF(colour.alphaF() * UNLANDED_ALPHA)
        return None, colour

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        order = self.reading.turn_order()
        if self.as_line():
            self._paint_line(painter, order)
            return
        for index, card in enumerate(order):
            fill, outline = self.colours(card)
            rect = self._dot_rect(index).adjusted(1, 1, -1, -1)
            painter.setPen(QPen(outline, 1.5) if outline is not None else Qt.PenStyle.NoPen)
            painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

    def _paint_line(self, painter, order):
        """One track: turned filled, face-down faint, the marked one a dot"""
        marked = self._marked()
        painter.setPen(Qt.PenStyle.NoPen)
        track = QRectF(2, (self.height() - LINE_HEIGHT_PX) / 2.0, self.width() - 4, LINE_HEIGHT_PX)
        faint = QColor(self.palette().placeholderText().color())
        faint.setAlphaF(faint.alphaF() * UNLANDED_ALPHA)
        painter.setBrush(faint)
        painter.drawRoundedRect(track, LINE_HEIGHT_PX / 2, LINE_HEIGHT_PX / 2)
        painter.setBrush(self.palette().windowText().color())
        for index, card in enumerate(order):
            if card is not marked and not is_face_down(card):
                painter.drawRect(self._segment(index, len(order)))
        if marked is not None and marked in order:
            # Never thinner than a dot, however many positions share the track
            centre = self._segment(order.index(marked), len(order)).center().x()
            marker = QRectF(centre - DOT_PX / 2, (self.height() - DOT_PX) / 2, DOT_PX, DOT_PX)
            painter.setBrush(next_gilt(self.palette()))
            painter.drawEllipse(marker)


def _button(icon, words, keys, slot):
    """A transport button: its words and keys in the tooltip, its words for a screen reader"""
    button = QToolButton()
    button.setIcon(QIcon.fromTheme(icon))
    button.setIconSize(QSize(BAR_ICON_PX, BAR_ICON_PX))
    button.setToolTip(f"{words} ({key_names(*keys)})")
    button.setAccessibleName(words)
    button.setAutoRaise(True)
    button.clicked.connect(slot)
    return button


class PlayerBar(QWidget):
    """The reading's transport: Deal; then turn · progress · Reveal All; then, once every card is
    turned, previous · progress · next, stepping the selection through the positions.

    Never back in time: a reading can't be un-turned, so the steps only look again
    """

    def __init__(self, reading, parent=None):
        super().__init__(parent)
        self.reading = reading
        row = QHBoxLayout(self)
        row.setContentsMargins(BAR_PAD_PX * 2, BAR_PAD_PX, BAR_PAD_PX * 2, BAR_PAD_PX)
        row.setSpacing(BAR_PAD_PX * 2)

        # The one thing to do before the deal, so the largest control under the canvas
        self.deal = QPushButton(QIcon.fromTheme(DEAL_ICON), READINGS["deal"])
        self.deal.clicked.connect(reading.deal)
        self.deal.setIconSize(QSize(BAR_ICON_PX, BAR_ICON_PX))
        self.deal.setMinimumSize(DEAL_MIN_WIDTH_PX, DEAL_MIN_HEIGHT_PX)
        typography.apply(self.deal, typography.Role.HEADING_3)
        self.previous = _button(
            "media-skip-backward",
            COMMANDS["go_previous"].replace("&", ""),
            (Qt.Key.Key_Left,),
            lambda: reading.step("previous"),
        )
        self.turn = _button(
            "media-playback-start",
            READINGS["turn_next"],
            (Qt.Key.Key_Space, TURN_KEY),
            reading.turn_next,
        )
        self.dots = ProgressDots(reading, self)
        self.reveal = _button(
            "media-seek-forward", READINGS["turn_all"], (TURN_ALL_KEY,), reading.turn_all
        )
        self.next = _button(
            "media-skip-forward",
            COMMANDS["go_next"].replace("&", ""),
            (Qt.Key.Key_Right,),
            lambda: reading.step("next"),
        )
        for widget in (self.deal, self.previous, self.turn, self.dots, self.reveal, self.next):
            # The keys that deal and turn are the canvas's; a click must not take its focus
            widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(widget)
        self.sync()

    def sync(self):
        """Show what the reading's phase allows"""
        phase = self.reading.phase
        staged = phase is Phase.STAGED
        read = phase is Phase.READ
        self.deal.setVisible(staged)
        if staged:
            # Every position filled by hand: nothing is dealt, the reading just begins
            placed = self.reading.all_placed()
            self.deal.setText(READINGS["begin" if placed else "deal"])
            self.deal.setIcon(QIcon.fromTheme(FINISH_ICON if placed else DEAL_ICON))
        self.dots.setVisible(not staged)
        for widget in (self.turn, self.reveal):
            widget.setVisible(phase is Phase.DEALT)
        for widget in (self.previous, self.next):
            widget.setVisible(read)
        can_turn = self.reading.can_turn()
        self.turn.setEnabled(can_turn)
        self.reveal.setEnabled(can_turn)
        if read:
            self.previous.setEnabled(self.reading.can_step("previous"))
            self.next.setEnabled(self.reading.can_step("next"))
        self.dots.updateGeometry()
        self.dots.update()
        self.update()

    def paintEvent(self, event):
        # Deal stands alone; the backdrop holds the controls only once there are several
        if self.reading.phase is Phase.STAGED:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        fill = QColor(palette.window().color())
        fill.setAlpha(BAR_ALPHA)
        painter.setBrush(fill)
        painter.setPen(QPen(palette.mid().color(), 1))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), BAR_RADIUS_PX, BAR_RADIUS_PX
        )


class ReadingStrip(QWidget):
    """The band under the canvas, a widget beside the view rather than a margin inside it, so the
    canvas ends above it: the transport centred, and View's actions at the trailing end.

    View lives here, not on the rail, for the reading's whole life, so its buttons never move
    """

    def __init__(self, reading, view_actions, parent=None):
        super().__init__(parent)
        self.setFixedHeight(STRIP_PX)
        grid = QGridLayout(self)
        grid.setContentsMargins(STRIP_PAD_PX, 0, STRIP_PAD_PX, 0)
        # Equal stretch either side keeps the transport centred under the canvas
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        self.bar = PlayerBar(reading, self)
        grid.addWidget(self.bar, 0, 1, Qt.AlignmentFlag.AlignCenter)

        cluster = QWidget()
        tools = QHBoxLayout(cluster)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(0)
        tools.addStretch(1)
        # The rail's own actions, so their tooltips, keys and checked states come with them
        self.buttons = []
        for action in view_actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setIconSize(QSize(BAR_ICON_PX, BAR_ICON_PX))
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tools.addWidget(button)
            self.buttons.append(button)
        grid.addWidget(cluster, 0, 2)
        # The leading column as wide as the cluster, so the cluster can't push the transport aside
        grid.setColumnMinimumWidth(0, cluster.sizeHint().width())
