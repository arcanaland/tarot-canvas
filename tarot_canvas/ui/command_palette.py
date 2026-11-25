from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QVBoxLayout,
)

from tarot_canvas.models.card_search import CardTerms, LabelTerms, Query
from tarot_canvas.models.deck_choices import deck_choices
from tarot_canvas.models.deck_types import CardKind
from tarot_canvas.ui import commands, typography
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.strings import PALETTE, without_mnemonic

THUMBNAIL_SIZE = QSize(25, 40)
COMMAND_ICON_SIZE = QSize(16, 16)
CARD_ROW_HEIGHT = 60
ROW_MARGIN = 5
TRAILING_SPACING = 12
FAINT_ALPHA = 0.6
# The card and deck of a card's row, and the Row of every row
CARD_ROLE = Qt.ItemDataRole.UserRole
ROW_ROLE = Qt.ItemDataRole.UserRole + 1
COMMAND_PREFIX = ">"

# Shared by every palette, so reopening one decodes nothing
_THUMBNAILS = CoverCache(capacity=128)

# Command ids most recently run from a palette first, for as long as the app runs
RECENT_LIMIT = 5
_RECENT = []


def remember(command_id):
    if command_id in _RECENT:
        _RECENT.remove(command_id)
    _RECENT.insert(0, command_id)
    del _RECENT[RECENT_LIMIT:]


@dataclass(frozen=True)
class Row:
    """What a row shows: a card's art or a command's icon or check mark, then its words"""

    title: str
    trailing: tuple[str, ...]  # right-aligned, in order
    subtitle: str = ""
    card: object = None  # a card's row draws its art, or leaves the room empty
    icon: QIcon | None = None
    checked: bool | None = None  # a checkable command's state
    radio: bool = False


def card_row(card, deck, hint):
    if card.kind is CardKind.MINOR:
        kind = f"{(card.suit_key or '').title()} {(card.rank_key or '').title()}"
    else:
        kind = card.kind.value.replace("_", " ").title()
    return Row(card.display_name, (hint,), f"{kind} - {deck.metadata.name}", card=card)


def command_row(action, where):
    command = commands.by_id(action.objectName())
    group = action.actionGroup()
    return Row(
        without_mnemonic(action.text()),
        (where, commands.key_text(command.shows or command.id)),
        icon=action.icon(),
        checked=action.isChecked() if action.isCheckable() else None,
        radio=group is not None and group.isExclusive(),
    )


class RowDelegate(QStyledItemDelegate):
    """Paints a Row; a card's art is decoded only once its row is painted"""

    def _small(self):
        return typography.font(typography.Role.SMALL)

    def sizeHint(self, option, index):
        row = index.data(ROW_ROLE)
        if row.card is not None:
            return QSize(0, CARD_ROW_HEIGHT)
        height = max(QFontMetrics(option.font).height(), COMMAND_ICON_SIZE.height())
        return QSize(0, height + 2 * ROW_MARGIN)

    def paint(self, painter, option, index):
        row = index.data(ROW_ROLE)
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, widget)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        palette = option.palette
        ink = palette.highlightedText().color() if selected else palette.text().color()
        faint = QColor(ink)
        faint.setAlphaF(FAINT_ALPHA)

        painter.save()
        rect = option.rect.adjusted(ROW_MARGIN, ROW_MARGIN, -ROW_MARGIN, -ROW_MARGIN)
        lead = QRect(rect.left(), rect.top(), THUMBNAIL_SIZE.width(), rect.height())
        if row.card is not None:
            ratio = widget.devicePixelRatioF() if widget else 1.0
            pixmap = _THUMBNAILS.get(row.card.default_image(), THUMBNAIL_SIZE, ratio)
            if pixmap is not None:
                size = pixmap.deviceIndependentSize().toSize()
                target = QRect(QPoint(), size)
                target.moveCenter(lead.center())
                painter.drawPixmap(target, pixmap)
        elif row.checked is not None:
            self._paint_mark(painter, style, option, lead, row)
        elif row.icon is not None and not row.icon.isNull():
            target = QRect(QPoint(), COMMAND_ICON_SIZE)
            target.moveCenter(lead.center())
            row.icon.paint(painter, target)

        small = self._small()
        right = rect.right()
        painter.setFont(small)
        painter.setPen(faint)
        for text in reversed(row.trailing):
            if not text:
                continue
            width = QFontMetrics(small).horizontalAdvance(text)
            painter.drawText(
                QRect(right - width, rect.top(), width, rect.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            right -= width + TRAILING_SPACING

        text = QRect(lead.right() + TRAILING_SPACING, rect.top(), 0, rect.height())
        text.setRight(right)
        title_font = QFont(option.font)
        title_font.setBold(row.card is not None)
        if row.subtitle:
            title_rect, subtitle_rect = text, QRect(text)
            title_rect.setBottom(text.center().y())
            subtitle_rect.setTop(text.center().y())
            painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignTop, row.subtitle)
            title_flags = Qt.AlignmentFlag.AlignBottom
        else:
            title_rect, title_flags = text, Qt.AlignmentFlag.AlignVCenter
        painter.setFont(title_font)
        painter.setPen(ink)
        elided = QFontMetrics(title_font).elidedText(
            row.title, Qt.TextElideMode.ElideRight, title_rect.width()
        )
        painter.drawText(title_rect, title_flags, elided)
        painter.restore()

    @staticmethod
    def _paint_mark(painter, style, option, lead, row):
        """The style's check box or radio button, drawn as a picture of the action's state"""
        Metric, Primitive, State = QStyle.PixelMetric, QStyle.PrimitiveElement, QStyle.StateFlag
        metric = Metric.PM_ExclusiveIndicatorWidth if row.radio else Metric.PM_IndicatorWidth
        size = style.pixelMetric(metric, None, option.widget)
        mark = QStyleOptionButton()
        mark.palette = option.palette
        mark.rect = QRect(0, 0, size, size)
        mark.rect.moveCenter(lead.center())
        mark.state = State.State_Enabled | (State.State_On if row.checked else State.State_Off)
        primitive = (
            Primitive.PE_IndicatorRadioButton if row.radio else Primitive.PE_IndicatorCheckBox
        )
        style.drawPrimitive(primitive, mark, painter, option.widget)


class ResultItem(QListWidgetItem):
    """A row that sorts by search tier, then by its place in the list it came from"""

    def __init__(self, terms, position, action=None):
        super().__init__()
        self.terms = terms
        self.position = position
        self.action = action
        self.order = (False, 0, 0, position)

    def rank(self, query, commanding):
        """Where the row sorts for a query; first, whether it misses"""
        if (self.action is not None) != commanding:
            return (True, 0, 0, self.position)
        tier = self.terms.tier(query)
        lead = 0
        if self.action is not None and not query:
            name = self.action.objectName()
            lead = _RECENT.index(name) if name in _RECENT else len(_RECENT)
        return (tier is None, tier or 0, lead, self.position)

    def __lt__(self, other):
        return self.order < other.order


class CommandPalette(QDialog):
    card_selected = pyqtSignal(object, object)  # Card, Deck

    def __init__(self, parent=None, active_tab_type=None, command_actions=()):
        """command_actions: (QAction, where it lives) for each command it may run"""
        super().__init__(parent)
        self.setWindowTitle(PALETTE["title"])
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        # Store active tab type to determine behavior
        self.active_tab_type = active_tab_type
        # The action to trigger once the palette has closed
        self.chosen_action = None

        # Remove window decorations for a cleaner look
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        self.setup_ui()
        self.load_cards()
        self.load_commands(command_actions)
        self.filter_results()

        # Escape closes the dialog
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.close)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(PALETTE["search"])
        self.search_input.textChanged.connect(self.filter_results)
        layout.addWidget(self.search_input)

        # What Enter does to a card
        action_text = (
            PALETTE["add_to_canvas"]
            if self.active_tab_type == "canvas"
            else PALETTE["open_card_view"]
        )
        self.hint_label = QLabel(PALETTE["hint"].format(action=action_text))
        self.hint_label.setStyleSheet("color: #666; font-style: italic;")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.hint_label)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.setItemDelegate(RowDelegate(self.results_list))
        self.results_list.itemActivated.connect(self.on_item_activated)
        layout.addWidget(self.results_list)

        # Set focus to search input
        self.search_input.setFocus()

    def load_cards(self):
        """Every visible deck's cards, pinned decks first, each in deck order"""
        pinned, rest = deck_choices()
        self.cards = [(card, deck) for deck in pinned + rest for card in deck.cards]
        self.build_results()

    def build_results(self):
        """One row per card; filtering hides rows rather than rebuilding them"""
        hint = PALETTE["add_to_canvas"] if self.active_tab_type == "canvas" else PALETTE["open"]
        for position, (card, deck) in enumerate(self.cards):
            item = ResultItem(CardTerms(card, deck.metadata.name), position)
            item.setData(CARD_ROLE, (card, deck))
            item.setData(ROW_ROLE, card_row(card, deck, hint))
            self.results_list.addItem(item)

    def load_commands(self, command_actions):
        """One row per command, shown only while the search starts with >"""
        for position, (action, where) in enumerate(command_actions):
            item = ResultItem(LabelTerms(without_mnemonic(action.text())), position, action)
            item.setData(ROW_ROLE, command_row(action, where))
            self.results_list.addItem(item)

    def visible_rows(self):
        return [
            row
            for row in range(self.results_list.count())
            if not self.results_list.isRowHidden(row)
        ]

    def select_first_visible(self):
        rows = self.visible_rows()
        self.results_list.setCurrentRow(rows[0] if rows else -1)

    def filter_results(self):
        """Hide the rows that don't match, and rank the rest best first"""
        text = self.search_input.text().lstrip()
        commanding = text.startswith(COMMAND_PREFIX)
        query = Query(text.removeprefix(COMMAND_PREFIX) if commanding else text)
        self.hint_label.setHidden(commanding)

        items = [self.results_list.item(row) for row in range(self.results_list.count())]
        for item in items:
            item.order = item.rank(query, commanding)

        self.results_list.sortItems()
        for item in items:
            item.setHidden(item.order[0])

        self.select_first_visible()

    def step_selection(self, step):
        """Move the selection by one visible row, wrapping at either end"""
        rows = self.visible_rows()
        if not rows:
            return
        current = self.results_list.currentRow()
        if current not in rows:
            self.results_list.setCurrentRow(rows[0])
            return
        self.results_list.setCurrentRow(rows[(rows.index(current) + step) % len(rows)])

    def on_item_activated(self, item):
        """Enter or a double-click: a card is reported now, a command once the palette closes"""
        if item.action is not None:
            remember(item.action.objectName())
            self.chosen_action = item.action
        else:
            self.card_selected.emit(*item.data(CARD_ROLE))
        self.accept()

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # If an item is selected, activate it
            current_item = self.results_list.currentItem()
            if current_item and not current_item.isHidden():
                self.on_item_activated(current_item)
        elif event.key() == Qt.Key.Key_Up:
            # Handle up key when in search input
            if self.search_input.hasFocus() and self.visible_rows():
                self.step_selection(-1)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Down:
            # Handle down key when in search input
            if self.search_input.hasFocus() and self.visible_rows():
                self.step_selection(1)
                event.accept()
                return

        # Pass unhandled events to parent
        super().keyPressEvent(event)
