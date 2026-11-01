import pytest
from PyQt6.QtCore import QAbstractListModel, QMimeData, QPoint, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QAbstractItemView

from tarot_canvas.ui.widgets.reorder_list import ReorderListView


class Rows(QAbstractListModel):
    def __init__(self, names, fixed=(), refuse=False):
        super().__init__()
        self.names = list(names)
        self.fixed = fixed
        self.refuse = refuse
        self.removed = []

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.names)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        return self.names[index.row()] if role == Qt.ItemDataRole.DisplayRole else None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self.names[index.row()] not in self.fixed:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def moveRows(self, source_parent, source, count, destination_parent, destination):
        if self.refuse or not self.beginMoveRows(
            source_parent, source, source, destination_parent, destination
        ):
            return False
        name = self.names.pop(source)
        self.names.insert(destination - 1 if destination > source else destination, name)
        self.endMoveRows()
        return True

    def removeRows(self, row, count, parent=None):
        self.removed.append(row)
        return False


def make_view(qtbot, model):
    view = ReorderListView()
    qtbot.addWidget(view)
    view.setModel(model)
    view.resize(200, 300)
    view.show()
    qtbot.waitExposed(view)
    return view


def upper(view, row):
    rect = view.visualRect(view.model().index(row))
    return QPoint(rect.center().x(), rect.top() + 1)


def lower(view, row):
    rect = view.visualRect(view.model().index(row))
    return QPoint(rect.center().x(), rect.bottom() - 1)


def drop(view, row, point):
    view.setCurrentIndex(view.model().index(row))
    event = QDropEvent(
        QPointF(point),
        Qt.DropAction.MoveAction,
        QMimeData(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.dropEvent(event)
    return event


def press(qtbot, view, key, modifier=Qt.KeyboardModifier.AltModifier):
    qtbot.keyClick(view, key, modifier)


@pytest.mark.parametrize(
    "source, side, target, after",
    [
        (0, lower, 2, "bcad"),
        (0, upper, 2, "bacd"),
        (3, upper, 1, "adbc"),
        (3, lower, 1, "abdc"),
    ],
)
def test_a_drop_lands_by_the_half_of_the_row_it_is_on(qtbot, source, side, target, after):
    model = Rows("abcd")
    view = make_view(qtbot, model)

    drop(view, source, side(view, target))

    assert "".join(model.names) == after


def test_a_drop_below_the_last_row_lands_last(qtbot):
    model = Rows("abc")
    view = make_view(qtbot, model)

    drop(view, 0, QPoint(10, 290))

    assert model.names == list("bca")


@pytest.mark.parametrize("side", [upper, lower])
def test_dropping_a_row_on_itself_changes_nothing(qtbot, side):
    model = Rows("abc")
    view = make_view(qtbot, model)

    drop(view, 1, side(view, 1))

    assert model.names == list("abc")


def test_dropping_next_to_itself_changes_nothing(qtbot):
    model = Rows("abc")
    view = make_view(qtbot, model)

    drop(view, 1, upper(view, 2))
    drop(view, 1, lower(view, 0))

    assert model.names == list("abc")


def test_a_row_without_the_drag_flag_is_not_moved(qtbot):
    model = Rows("abc", fixed="a")
    view = make_view(qtbot, model)

    drop(view, 0, lower(view, 2))

    assert model.names == list("abc")


def test_a_refused_move_leaves_the_order(qtbot):
    model = Rows("abc", refuse=True)
    view = make_view(qtbot, model)

    drop(view, 0, lower(view, 2))

    assert model.names == list("abc")


def test_a_drop_is_not_reported_as_a_move(qtbot):
    # startDrag would remove the dragged row from the model
    model = Rows("abc")
    view = make_view(qtbot, model)

    event = drop(view, 0, lower(view, 2))

    assert event.isAccepted()
    assert event.dropAction() != Qt.DropAction.MoveAction


def test_the_model_says_what_can_be_picked_up(qtbot):
    view = make_view(qtbot, Rows("abc"))

    assert view.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove
    assert view.defaultDropAction() == Qt.DropAction.MoveAction
    assert view.showDropIndicator()


def test_alt_down_and_alt_up_move_the_current_row(qtbot):
    model = Rows("abc")
    view = make_view(qtbot, model)
    view.setCurrentIndex(model.index(0))

    press(qtbot, view, Qt.Key.Key_Down)
    assert model.names == list("bac")
    assert view.currentIndex().row() == 1

    press(qtbot, view, Qt.Key.Key_Down)
    assert model.names == list("bca")
    assert view.currentIndex().row() == 2

    press(qtbot, view, Qt.Key.Key_Up)
    assert model.names == list("bac")
    assert view.currentIndex().row() == 1


def test_alt_arrows_stop_at_the_ends(qtbot):
    model = Rows("ab")
    view = make_view(qtbot, model)

    view.setCurrentIndex(model.index(0))
    press(qtbot, view, Qt.Key.Key_Up)
    assert model.names == list("ab")

    view.setCurrentIndex(model.index(1))
    press(qtbot, view, Qt.Key.Key_Down)
    assert model.names == list("ab")


def test_alt_arrows_leave_a_row_without_the_drag_flag(qtbot):
    model = Rows("abc", fixed="a")
    view = make_view(qtbot, model)
    view.setCurrentIndex(model.index(0))

    press(qtbot, view, Qt.Key.Key_Down)

    assert model.names == list("abc")


def test_a_plain_arrow_only_moves_the_cursor(qtbot):
    model = Rows("abc")
    view = make_view(qtbot, model)
    view.setCurrentIndex(model.index(0))

    press(qtbot, view, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)

    assert model.names == list("abc")
    assert view.currentIndex().row() == 1
