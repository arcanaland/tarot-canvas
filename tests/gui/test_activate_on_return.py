import pytest
from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtWidgets import QListView

from tarot_canvas.ui.activate_on_return import activate_on_return


@pytest.fixture
def view(qtbot):
    view = QListView()
    qtbot.addWidget(view)
    model = QStringListModel(["one", "two"], view)
    view.setModel(model)
    view.setCurrentIndex(model.index(1, 0))
    return view


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_return_activates_the_current_row_once_on_macos(qtbot, view, key):
    activate_on_return(view, platform="darwin")
    rows = []
    view.activated.connect(lambda index: rows.append(index.row()))

    qtbot.keyClick(view, key)

    assert rows == [1]


def test_return_without_a_current_row_activates_nothing(qtbot, view):
    activate_on_return(view, platform="darwin")
    view.setCurrentIndex(view.model().index(-1, 0))
    rows = []
    view.activated.connect(lambda index: rows.append(index.row()))

    qtbot.keyClick(view, Qt.Key.Key_Return)

    assert rows == []


def test_other_platforms_keep_qts_own_handling(view):
    children = view.children()

    activate_on_return(view, platform="linux")

    assert view.children() == children
