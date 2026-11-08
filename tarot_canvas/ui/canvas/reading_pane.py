"""Pane on the side of a reading"""

from PyQt6.QtCore import QEvent, QObject, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QFontMetricsF, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QTextEdit,
    QToolTip,
    QWidget,
)

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.placement import Phase
from tarot_canvas.ui.canvas.reading_card import is_face_down
from tarot_canvas.ui.canvas.reading_marks import next_gilt
from tarot_canvas.ui.canvas.side_pane import SidePane
from tarot_canvas.ui.canvas.spread_pane import (
    DescriptionBox,
    MeaningRole,
    NumberRole,
    PositionDelegate,
    _draw,
)
from tarot_canvas.ui.icons import SPREAD_ICON, deck_icon
from tarot_canvas.ui.library import units
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.ui.widgets.reorder_list import GRIP_WIDTH
from tarot_canvas.utils.dates import format_qdatetime

# The Question wraps to this many lines before it scrolls
QUESTION_LINES = 3
# The info lines' icons
INFO_ICON_PX = 16
# A row's card, as its width over its height
THUMB_RATIO = 0.58
# The next row's wash of gilt, and the bar at its leading edge
NEXT_FILL_ALPHA = 40
NEXT_BAR_PX = 3
SELECTED_ALPHA = 70
# The list's share of the pane's height against the filler under it, which gets only the rest
LIST_STRETCH = 1000


class QuestionBox(DescriptionBox):
    """The Question as the pane's heading: wrapped to three lines, then scrolled."""

    submitted = pyqtSignal()

    def __init__(self, hint):
        super().__init__(hint, QUESTION_LINES)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        typography.apply(self, typography.Role.HEADING_2)
        self.setAccessibleName(hint)
        # The line limit was measured in the default font
        margins = 2 * self.document().documentMargin()
        self._limit = QFontMetricsF(self.font()).lineSpacing() * QUESTION_LINES + margins
        self._fit()

    def text(self):
        return self.toPlainText()

    def setText(self, text):
        self.setPlainText(text)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(" ".join(source.text().split()))
            return
        super().insertFromMimeData(source)


class RowOpener(QObject):
    """Double-clicking a row opens its card."""

    def __init__(self, view, opened):
        super().__init__(view)
        self._view = view
        self._opened = opened
        self._row = None
        view.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            # Before the view selects, and so before the rows move
            index = self._view.indexAt(event.position().toPoint())
            self._row = index.row() if index.isValid() else None
        elif (
            kind == QEvent.Type.MouseButtonDblClick
            and event.button() == Qt.MouseButton.LeftButton
            and self._row is not None
        ):
            self._opened(self._row)
            return True
        return False


class ListFit(QObject):
    """Keeps the list as tall as its rows"""

    def __init__(self, view):
        super().__init__(view)
        self._view = view
        view.viewport().installEventFilter(self)
        model = view.model()
        model.rowsInserted.connect(self.fit)
        model.rowsRemoved.connect(self.fit)
        view.itemDelegate().sizeHintChanged.connect(self.fit)
        self.fit()

    def fit(self, *_):
        view = self._view
        rows = sum(view.sizeHintForRow(row) for row in range(view.model().rowCount()))
        view.setMaximumHeight(max(rows + 2 * view.frameWidth(), 1))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.fit()
        return False


class ReadingRowDelegate(PositionDelegate):
    """A position's row with its card in place of the grip"""

    def __init__(self, view, reading):
        super().__init__(view)
        self.reading = reading
        self._open_rows = set()

    # -- open rows ------------------------------------------------------------------

    def is_open(self, index):
        return index.row() in self._open_rows

    def set_open_rows(self, rows):
        """Open rows"""
        changed = self._open_rows ^ set(rows)
        self._open_rows = set(rows)
        model = self.view.model()
        for row in changed:
            self.sizeHintChanged.emit(model.index(row, 0))

    def _meaning(self, index):
        return " ".join((index.data(MeaningRole) or "").split())

    def _card(self, index):
        return self.reading.card_in(self.reading.slots()[index.row()])

    def card_line(self, index):
        """The revealed card's name + reversed"""
        card = self._card(index)
        if card is None or is_face_down(card):
            return None
        name = card.card_data.get("name") or card.card_data.get("id", "")
        return READINGS["card_reversed"].format(card=name) if card.is_reversed() else name

    def _meaning_width(self, option):
        """How wide the meaning's lines are in a row as wide as the list"""
        measured = type(option)(option)
        measured.rect = QRect(0, 0, self.view.viewport().width(), 1000)
        return self.title_rect(measured, True).width()

    def _wrapped_height(self, index, width):
        small = typography.font(typography.Role.SMALL)
        bounds = QFontMetrics(small).boundingRect(
            QRect(0, 0, max(1, width), 100000),
            int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
            self._meaning(index),
        )
        return bounds.height()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        if not self.is_open(index) or not self._meaning(index):
            return hint
        title_height, small_height = self._line_heights(option)
        meaning = self._wrapped_height(index, self._meaning_width(option))
        card = small_height if self.card_line(index) else 0
        height = title_height + card + max(small_height, meaning) + 2 * units.LARGE_SPACING
        return QSize(hint.width(), max(hint.height(), height))

    def meaning_is_hidden(self, option, index):
        """Whether a closed row doesn't show its whole meaning"""
        meaning = self._meaning(index)
        if not meaning or self.is_open(index):
            return False
        small = QFontMetrics(typography.font(typography.Role.SMALL))
        width = self.title_rect(option, True).width()
        return bool(self.card_line(index)) or small.horizontalAdvance(meaning) > width

    def helpEvent(self, event, view, option, index):
        """A closed row whose meaning is hidden gives it whole in a tooltip"""
        if event.type() == QEvent.Type.ToolTip and index.isValid():
            if self.meaning_is_hidden(option, index):
                QToolTip.showText(event.globalPos(), self._meaning(index), view)
            else:
                QToolTip.hideText()
            return True
        return super().helpEvent(event, view, option, index)

    # -- painting -------------------------------------------------------------------

    def _paint_text(self, painter, option, index):
        title_font, small_font = self._fonts(option, False)
        meaning = self._meaning(index)
        card = self.card_line(index)
        title = self.title_rect(option, bool(card or meaning))
        text = option.palette.text().color()
        _draw(painter, title, index.data(Qt.ItemDataRole.DisplayRole), title_font, text)
        small_height = self._line_heights(option)[1]
        top = title.bottom() + 1
        if card:
            _draw(
                painter,
                QRect(title.left(), top, title.width(), small_height),
                card,
                small_font,
                text,
            )
            top += small_height
        if not meaning or (card and not self.is_open(index)):
            return
        grey = option.palette.placeholderText().color()
        if not self.is_open(index):
            line = QRect(title.left(), top, title.width(), small_height)
            _draw(painter, line, meaning, small_font, grey)
            return
        painter.setFont(small_font)
        painter.setPen(grey)
        bottom = option.rect.bottom() - units.LARGE_SPACING
        painter.drawText(
            QRect(title.left(), top, title.width(), max(small_height, bottom - top)),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            meaning,
        )

    def thumb_rect(self, option):
        title_height, small_height = self._line_heights(option)
        height = title_height + small_height + 2 * (units.LARGE_SPACING - units.SMALL_SPACING)
        left = option.rect.left() + units.SMALL_SPACING + NEXT_BAR_PX
        top = option.rect.top() + units.SMALL_SPACING
        return QRect(left, top, round(height * THUMB_RATIO), height)

    def _number_rect(self, option):
        rect = super()._number_rect(option)
        rect.translate(self.thumb_rect(option).width() + NEXT_BAR_PX - GRIP_WIDTH, 0)
        return rect

    def paint(self, painter, option, index):
        slot = self.reading.slots()[index.row()]
        is_next = self.reading.is_next_slot(slot)
        palette = option.palette
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            selected = QColor(palette.highlight().color())
            selected.setAlpha(SELECTED_ALPHA)
            painter.fillRect(option.rect, selected)
        if is_next:
            gilt = next_gilt(palette)
            wash = QColor(gilt)
            wash.setAlpha(NEXT_FILL_ALPHA)
            painter.fillRect(option.rect, wash)
            bar = QRect(option.rect.left(), option.rect.top(), NEXT_BAR_PX, option.rect.height())
            painter.fillRect(bar, gilt)
        self._paint_text(painter, option, index)
        self._paint_thumb(painter, self.thumb_rect(option), self._card(index), palette)
        painter.setFont(self._fonts(option, is_next)[0])
        painter.setPen(palette.text().color())
        painter.drawText(
            self._number_rect(option),
            int(Qt.AlignmentFlag.AlignCenter),
            str(index.data(NumberRole)),
        )
        painter.restore()

    def _paint_thumb(self, painter, rect, card, palette):
        painter.save()
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        target = QRectF(rect)
        if card is None:
            painter.setPen(QPen(palette.placeholderText().color(), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = target.width() * 0.08
            painter.drawRoundedRect(target.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        else:
            face_down = is_face_down(card)
            pixmap = card.pixmap() if face_down else card.face_pixmap()
            if not face_down and card.is_reversed():
                painter.translate(target.center())
                painter.rotate(180)
                painter.translate(-target.center())
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        painter.restore()


class ReadingPane(SidePane):
    """The pane on the side of a reading canvas"""

    def __init__(self, reading, positions, spread_name, spread_description, decks, deck):
        super().__init__()
        self.reading = reading
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)

        self.question_edit = QuestionBox(READINGS["question_hint"])
        heading = QHBoxLayout()
        margin = units.LARGE_SPACING
        heading.setContentsMargins(margin, margin, margin, margin)
        heading.addWidget(self.question_edit, 1)
        self.body.addLayout(heading)

        self._build_facts(spread_name, spread_description, decks, deck)
        self.list_view = self._build_list(positions)

        # The list takes room first
        self.body.addWidget(self.list_view, LIST_STRETCH)
        filler = QWidget()
        filler.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.body.addWidget(filler, 1)

    def _build_facts(self, spread_name, spread_description, decks, deck):
        form = QWidget()
        self._grid = grid = QGridLayout(form)
        margin = units.LARGE_SPACING
        grid.setContentsMargins(margin, 0, margin, margin)
        grid.setHorizontalSpacing(units.LARGE_SPACING)
        grid.setVerticalSpacing(units.SMALL_SPACING)
        grid.setColumnStretch(1, 1)
        self._form = form

        # The spread.
        self.spread_label = QLabel(spread_name)
        self.spread_label.setWordWrap(True)
        self.spread_label.setToolTip(spread_description.strip())
        self._info_line(QIcon.fromTheme(SPREAD_ICON), self.spread_label)

        # The deck
        self.deck_combo = QComboBox()
        self.deck_combo.setFrame(False)
        self.deck_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for each in decks:
            self.deck_combo.addItem(each.get_name(), each)
            if each is deck:
                self.deck_combo.setCurrentIndex(self.deck_combo.count() - 1)
        self.deck_label = QLabel()
        self.deck_label.setWordWrap(True)
        self._info_line(deck_icon(), self.deck_combo, self.deck_label, None, control=True)

        # Reversals
        self.reversals_check = QCheckBox(READINGS["reversals"])
        self.reversals_label = QLabel()
        self.reversals_mark = self._info_line(
            QIcon.fromTheme("object-flip-vertical"),
            self.reversals_check,
            self.reversals_label,
            None,
            control=True,
        )

        # The date
        self.date_label = QLabel()
        self.date_mark = self._info_line(QIcon.fromTheme("view-calendar-day"), self.date_label)

        # Plain text starts where the deck menu's text does, so the facts line up in a column
        self.deck_combo.ensurePolished()
        option = QStyleOptionComboBox()
        self.deck_combo.initStyleOption(option)
        field = self.deck_combo.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self.deck_combo,
        )
        for label in (self.spread_label, self.deck_label, self.reversals_label, self.date_label):
            label.setIndent(field.left())
        self.body.addWidget(form)

    def _info_line(self, icon, *widgets, control=False):
        """An icon and its fact"""
        grid = self._grid
        row = grid.rowCount()
        mark = QLabel()
        mark.setPixmap(icon.pixmap(INFO_ICON_PX))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedHeight(self._form.fontMetrics().height())
        centre = Qt.AlignmentFlag.AlignVCenter if control else Qt.AlignmentFlag.AlignTop
        grid.addWidget(mark, row, 0, centre)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(units.SMALL_SPACING)
        for widget in widgets:
            if widget is None:
                line.addStretch(1)
            else:
                line.addWidget(widget)
        grid.addLayout(line, row, 1)
        return mark

    def _build_list(self, positions):
        view = QListView()
        view.setModel(positions)
        self.rows = ReadingRowDelegate(view, self.reading)
        view.setItemDelegate(self.rows)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setAlternatingRowColors(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list_fit = ListFit(view)
        return view

    def chosen_deck(self):
        return self.deck_combo.currentData()

    def sync(self, phase, decks, reversals, dealt_at, draws=True):
        """Controls while staged, enabled only while the deal will draw: once every position
        is filled by hand, neither has anything to choose. After the deal, plain text: the decks
        the reading's cards came from, one per line; whether it was dealt with reversals, unless
        nothing was dealt; and the date"""
        staged = phase is Phase.STAGED
        self.deck_combo.setVisible(staged)
        self.deck_combo.setEnabled(staged and draws)
        self.deck_label.setVisible(not staged)
        self.deck_label.setText("\n".join(deck.get_name() for deck in decks))
        self.reversals_check.setVisible(staged)
        self.reversals_check.setEnabled(staged and draws)
        told = not staged and reversals is not None
        self.reversals_mark.setVisible(staged or told)
        self.reversals_label.setVisible(told)
        self.reversals_label.setText(
            READINGS["reversals_with" if reversals else "reversals_without"]
        )
        dealt = dealt_at is not None and not staged
        self.date_mark.setVisible(dealt)
        self.date_label.setVisible(dealt)
        if dealt:
            self.date_label.setText(format_qdatetime(dealt_at))
