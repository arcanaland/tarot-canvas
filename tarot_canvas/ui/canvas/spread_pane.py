from PyQt6.QtCore import (
    QAbstractListModel,
    QItemSelectionModel,
    QModelIndex,
    QRect,
    QSize,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QFont, QFontMetrics, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.side_pane import SidePane
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import subtle_fill
from tarot_canvas.ui.strings import SPREADS
from tarot_canvas.ui.widgets.heading_edit import heading_edit
from tarot_canvas.ui.widgets.placeholder_message import PlaceholderMessage
from tarot_canvas.ui.widgets.reorder_list import GRIP_WIDTH, ReorderListView, paint_grip

MEANING_LINES = 6
USAGE_LINES = 4
# Room for "88"
NUMBER_TEXT = "88"

NumberRole = Qt.ItemDataRole.UserRole + 1
MeaningRole = Qt.ItemDataRole.UserRole + 2


def text_box(hint, lines):
    box = QPlainTextEdit()
    box.setPlaceholderText(hint)
    box.setTabChangesFocus(True)
    box.setFixedHeight(box.fontMetrics().lineSpacing() * lines + 2 * box.frameWidth() + 8)
    return box


class PositionModel(QAbstractListModel):
    """A spread's slots as rows, over the list the tab keeps them in"""

    # The numbering changed by a move
    moved = pyqtSignal()

    def __init__(self, slots, parent=None):
        super().__init__(parent)
        self._slots = slots

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._slots)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        slot = self._slots[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return slot.label
        if role == NumberRole:
            return slot.number
        if role == MeaningRole:
            return slot.meaning
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return SPREADS["slot_row"].format(number=slot.number, label=slot.label)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        slot = self._slots[index.row()]
        if role == Qt.ItemDataRole.EditRole:
            slot.set_label(value)
        elif role == MeaningRole:
            slot.meaning = value
        else:
            return False
        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        )

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def moveRows(self, source_parent, source, count, destination_parent, destination):
        if count != 1 or not self.beginMoveRows(
            source_parent, source, source, destination_parent, destination
        ):
            return False
        slot = self._slots.pop(source)
        self._slots.insert(destination - 1 if destination > source else destination, slot)
        self.endMoveRows()
        self._renumber()
        self.moved.emit()
        return True

    def index_of(self, slot):
        return self.index(self._slots.index(slot)) if slot in self._slots else QModelIndex()

    def append(self, slot):
        row = len(self._slots)
        self.beginInsertRows(QModelIndex(), row, row)
        self._slots.append(slot)
        self.endInsertRows()

    def remove_unplaced(self):
        """Drop the rows of slots no longer on the canvas, and number the rest"""
        for row in reversed(range(len(self._slots))):
            if self._slots[row].scene() is None:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._slots[row]
                self.endRemoveRows()
        self._renumber()

    def _renumber(self):
        for row, slot in enumerate(self._slots):
            if slot.number != row + 1:
                slot.set_number(row + 1)
                self.dataChanged.emit(self.index(row), self.index(row))


class PositionDelegate(QStyledItemDelegate):
    """A slot's grip and number, then its label over its meaning, or room for its editor"""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def _fonts(self, option, selected):
        title = QFont(option.font)
        title.setBold(selected)
        return title, typography.font(typography.Role.SMALL)

    def _line_heights(self, option):
        title, small = self._fonts(option, False)
        return QFontMetrics(title).height(), QFontMetrics(small).height()

    def _number_rect(self, option):
        """Beside the grip, one row's lines high"""
        title_height, small_height = self._line_heights(option)
        return QRect(
            option.rect.left() + units.SMALL_SPACING + GRIP_WIDTH,
            option.rect.top() + units.LARGE_SPACING,
            QFontMetrics(self._fonts(option, True)[0]).horizontalAdvance(NUMBER_TEXT),
            title_height + small_height,
        )

    def sizeHint(self, option, index):
        editor = self.view.indexWidget(index)
        if editor is not None:
            height = editor.sizeHint().height()
        else:
            height = sum(self._line_heights(option))
        return QSize(units.GRID_UNIT, height + 2 * units.LARGE_SPACING)

    def _content_rect(self, option):
        """Right of the number, inside the row's margins"""
        margin = units.LARGE_SPACING
        rect = option.rect.adjusted(0, margin, -margin, -margin)
        rect.setLeft(self._number_rect(option).right() + 1 + margin)
        return rect

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(self._content_rect(option))

    def paint(self, painter, option, index):
        painter.save()
        palette = option.palette
        # The open row is the selected one. Its fields keep their own colours, so a tint
        # marks it and not the highlight
        if self.view.indexWidget(index) is not None:
            painter.fillRect(option.rect, subtle_fill(palette))
        else:
            self._paint_text(painter, option, index)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        number = self._number_rect(option)
        grip = QRect(option.rect.left() + units.SMALL_SPACING, number.top(), GRIP_WIDTH, 0)
        grip.setBottom(number.bottom())
        paint_grip(painter, grip, palette)
        painter.setFont(self._fonts(option, selected)[0])
        painter.setPen(palette.text().color())
        painter.drawText(number, int(Qt.AlignmentFlag.AlignCenter), str(index.data(NumberRole)))
        painter.restore()

    def title_rect(self, option, has_meaning):
        """The label's line, level with the number when no meaning sits under it"""
        title_height, small_height = self._line_heights(option)
        content = self._content_rect(option)
        top = content.top() + (0 if has_meaning else small_height // 2)
        return QRect(content.left(), top, content.width(), title_height)

    def _paint_text(self, painter, option, index):
        title_font, small_font = self._fonts(option, False)
        meaning = " ".join(index.data(MeaningRole).split())
        title = self.title_rect(option, bool(meaning))

        _draw(
            painter,
            title,
            index.data(Qt.ItemDataRole.DisplayRole),
            title_font,
            option.palette.text().color(),
        )
        if meaning:
            _draw(
                painter,
                QRect(
                    title.left(), title.bottom() + 1, title.width(), self._line_heights(option)[1]
                ),
                meaning,
                small_font,
                option.palette.placeholderText().color(),
            )


def _draw(painter, rect, text, font, colour):
    painter.setFont(font)
    painter.setPen(colour)
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width()),
    )


class PositionEditor(QWidget):
    """One slot's fields, in its row"""

    label_edited = pyqtSignal(str)
    meaning_edited = pyqtSignal(str)
    # -1 is earlier, 1 later
    step_requested = pyqtSignal(int)

    def __init__(self, label, meaning, parent=None):
        super().__init__(parent)
        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText(SPREADS["label_hint"])
        self.label_edit.textChanged.connect(self.label_edited)

        self.meaning_edit = text_box(SPREADS["meaning_hint"], MEANING_LINES)
        self.meaning_edit.setPlainText(meaning)
        self.meaning_edit.textChanged.connect(self._on_meaning_edited)

        self.earlier_button = self._step_button("go-up", SPREADS["move_earlier"], -1)
        self.later_button = self._step_button("go-down", SPREADS["move_later"], 1)

        top = QHBoxLayout()
        top.setSpacing(units.SMALL_SPACING)
        top.addWidget(self.label_edit, 1)
        top.addWidget(self.earlier_button)
        top.addWidget(self.later_button)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(units.SMALL_SPACING)
        column.addLayout(top)
        column.addWidget(self.meaning_edit)

        self.setTabOrder(self.label_edit, self.meaning_edit)
        self.setTabOrder(self.meaning_edit, self.earlier_button)
        self.setTabOrder(self.earlier_button, self.later_button)

    def _step_button(self, icon, tooltip, step):
        button = QToolButton()
        button.setIcon(QIcon.fromTheme(icon))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(True)
        button.clicked.connect(lambda: self.step_requested.emit(step))
        return button

    def set_can_step(self, earlier, later):
        self.earlier_button.setEnabled(earlier)
        self.later_button.setEnabled(later)

    @pyqtSlot()
    def _on_meaning_edited(self):
        self.meaning_edited.emit(self.meaning_edit.toPlainText())


class SpreadPane(SidePane):
    """A spread's name, its slots with the selected one open for editing, and its description"""

    # Anything here that the file keeps
    edited = pyqtSignal()
    slot_chosen = pyqtSignal(int)

    def __init__(self, positions, add_slot_action, parent=None):
        super().__init__(parent)
        self.positions = positions
        self.editor = None
        self._open_slot = None

        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)

        self.name_edit = heading_edit(SPREADS["name_hint"])
        self.name_edit.setAccessibleName(SPREADS["name_title"])
        self.add_slot_button = QToolButton()
        self.add_slot_button.setDefaultAction(add_slot_action)
        self.add_slot_button.setAutoRaise(True)
        heading = QHBoxLayout()
        margin = units.LARGE_SPACING
        heading.setContentsMargins(margin, margin, margin, margin)
        heading.addWidget(self.name_edit, 1)
        heading.addWidget(self.add_slot_button)
        self.body.addLayout(heading)

        self.list_view = self._build_list()
        self.placeholder = PlaceholderMessage(
            "view-grid", SPREADS["slots_empty"], helpful_action=add_slot_action
        )
        empty_page = QWidget()
        empty_column = QVBoxLayout(empty_page)
        empty_column.addStretch(1)
        empty_column.addWidget(self.placeholder)
        empty_column.addStretch(1)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.list_view)
        self.stack.addWidget(empty_page)
        self.body.addWidget(self.stack, 1)
        self._build_usage()

        self.positions.rowsInserted.connect(self._on_rows_changed)
        self.positions.rowsRemoved.connect(self._on_rows_changed)
        self.positions.rowsMoved.connect(self._on_rows_changed)
        self._on_rows_changed()

    def _build_list(self):
        view = ReorderListView()
        view.setModel(self.positions)
        self.delegate = PositionDelegate(view)
        view.setItemDelegate(self.delegate)

        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setAlternatingRowColors(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.selectionModel().selectionChanged.connect(self._on_row_selected)
        return view

    def _build_usage(self):
        seam = QFrame()
        seam.setFrameShape(QFrame.Shape.HLine)
        seam.setFrameShadow(QFrame.Shadow.Plain)
        self.body.addWidget(seam)

        self.usage_button = QToolButton()
        self.usage_button.setText(SPREADS["usage_title"])
        self.usage_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.usage_button.setAutoRaise(True)
        self.usage_button.clicked.connect(lambda: self.set_usage_open(not self.usage_open()))

        self.usage_edit = text_box(SPREADS["usage_hint"], USAGE_LINES)
        self.usage_edit.setAccessibleName(SPREADS["usage_title"])
        self.usage_edit.textChanged.connect(self.edited)

        column = QVBoxLayout()
        margin = units.LARGE_SPACING
        column.setContentsMargins(margin, units.SMALL_SPACING, margin, units.SMALL_SPACING)
        column.setSpacing(units.SMALL_SPACING)
        column.addWidget(self.usage_button, alignment=Qt.AlignmentFlag.AlignLeft)
        column.addWidget(self.usage_edit)
        self.body.addLayout(column)
        self.set_usage_open(True)

    def usage_open(self):
        return not self.usage_edit.isHidden()

    def set_usage_open(self, wanted):
        self.usage_edit.setHidden(not wanted)
        self.usage_button.setIcon(QIcon.fromTheme("arrow-down" if wanted else "arrow-right"))

    def usage(self):
        return self.usage_edit.toPlainText()

    def set_document(self, name, usage):
        self.name_edit.setText(name)
        self.usage_edit.setPlainText(usage)

    def show_selected(self, slot):
        """Select slot's row and open it, or with None no row"""
        selection = self.list_view.selectionModel()
        if slot is None:
            selection.clear()
            self._close_row()
            return

        index = self.positions.index_of(slot)
        if not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        # Reselecting keeps the editor, and the focus in it
        if slot is not self._open_slot:
            self._close_row()
            self._open_row(slot, index)
        self.list_view.scrollTo(index)

    def _open_row(self, slot, index):
        self.editor = PositionEditor(slot.label, slot.meaning)
        self.editor.label_edited.connect(self._on_label_edited)
        self.editor.meaning_edited.connect(self._on_meaning_edited)
        self.editor.step_requested.connect(self._step_open_row)
        self._open_slot = slot
        self.list_view.setIndexWidget(index, self.editor)
        self.delegate.sizeHintChanged.emit(index)
        self._sync_steps()

    def _close_row(self):
        if self.editor is None:
            return
        index = self.positions.index_of(self._open_slot)
        self.editor.hide()
        self.editor = self._open_slot = None
        self.list_view.setIndexWidget(index, None)
        self.delegate.sizeHintChanged.emit(index)

    def focus_label(self):
        self.editor.label_edit.setFocus()
        self.editor.label_edit.selectAll()

    def focus_meaning(self):
        self.editor.meaning_edit.setFocus()

    def _edit(self, value, role):
        self.positions.setData(self.positions.index_of(self._open_slot), value, role)
        self.edited.emit()

    @pyqtSlot(str)
    def _on_label_edited(self, text):
        self._edit(text, Qt.ItemDataRole.EditRole)

    @pyqtSlot(str)
    def _on_meaning_edited(self, text):
        self._edit(text, MeaningRole)

    @pyqtSlot(int)
    def _step_open_row(self, step):
        self.list_view.step_row(self.positions.index_of(self._open_slot).row(), step)

    def _sync_steps(self):
        if self.editor is not None:
            row = self.positions.index_of(self._open_slot).row()
            self.editor.set_can_step(row > 0, row < self.positions.rowCount() - 1)

    @pyqtSlot()
    def _on_rows_changed(self):
        self.stack.setCurrentIndex(0 if self.positions.rowCount() else 1)
        self._sync_steps()

    @pyqtSlot()
    def _on_row_selected(self):
        rows = self.list_view.selectionModel().selectedRows()
        if len(rows) == 1:
            self.slot_chosen.emit(rows[0].row())
