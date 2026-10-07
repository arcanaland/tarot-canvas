from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from tarot_canvas.ui.tabs.card_view.fold import Fold


def make_fold(qtbot, expanded=False):
    fold = Fold("Header 2", QLabel("Inside"), expanded)
    qtbot.addWidget(fold)
    fold.show()
    return fold


def test_a_closed_fold_hides_its_content_behind_a_right_arrow(qtbot):
    fold = make_fold(qtbot)

    assert not fold.content.isVisible()
    assert fold.header.arrowType() == Qt.ArrowType.RightArrow
    assert fold.header.text() == "Header 2"


def test_clicking_the_header_opens_and_closes_it(qtbot):
    fold = make_fold(qtbot)

    with qtbot.waitSignal(fold.toggled) as opened:
        qtbot.mouseClick(fold.header, Qt.MouseButton.LeftButton)
    assert opened.args == [True]
    assert fold.content.isVisible()
    assert fold.header.arrowType() == Qt.ArrowType.DownArrow

    qtbot.mouseClick(fold.header, Qt.MouseButton.LeftButton)
    assert not fold.content.isVisible()
    assert fold.header.arrowType() == Qt.ArrowType.RightArrow


def test_a_fold_can_start_open(qtbot):
    fold = make_fold(qtbot, expanded=True)

    assert fold.is_expanded()
    assert fold.content.isVisible()
    assert fold.header.arrowType() == Qt.ArrowType.DownArrow
