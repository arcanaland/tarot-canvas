import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from tarot_canvas.ui import typography
from tarot_canvas.ui.typography import HEADING_SCALES, Role


@pytest.fixture
def installed(qapp):
    saved = QApplication.font()
    font = QFont(saved)
    font.setPointSizeF(10)
    QApplication.setFont(font)
    typography.install(qapp)
    yield
    typography.uninstall(qapp)
    QApplication.setFont(saved)


def set_body_size(points):
    font = QFont(QApplication.font())
    font.setPointSizeF(points)
    QApplication.setFont(font)


def test_a_heading_follows_a_system_font_change(qtbot, installed):
    label = typography.apply(QLabel("Heading"), Role.HEADING_1, primary=True)
    qtbot.addWidget(label)
    label.show()

    set_body_size(14)
    qtbot.wait(1)

    assert label.font().pointSizeF() == pytest.approx(14 * HEADING_SCALES[Role.HEADING_1])
    assert label.font().weight() == QFont.Weight.DemiBold


def test_a_fixed_small_role_keeps_its_options_across_a_change(qtbot, installed):
    label = typography.apply(QLabel("major_arcana.fool"), Role.SMALL, fixed=True)
    qtbot.addWidget(label)

    set_body_size(14)
    qtbot.wait(1)

    assert label.font() == typography.font(Role.SMALL, fixed=True)


def test_reapply_all_rederives_every_role(qtbot, qapp):
    label = typography.apply(QLabel("Heading"), Role.HEADING_2)
    qtbot.addWidget(label)
    # Without the filter installed, a change is picked up only on request
    saved = QApplication.font()
    try:
        set_body_size(20)
        typography.reapply_all()
        assert label.font() == typography.font(Role.HEADING_2)
    finally:
        QApplication.setFont(saved)


def test_a_heading_follows_under_an_application_style_sheet(qtbot, installed, qapp):
    # The theme sets one, and Qt then sends ApplicationFontChange to windows only
    saved = qapp.styleSheet()
    qapp.setStyleSheet("QToolTip { padding: 1px; }")
    try:
        window = QWidget()
        label = typography.apply(QLabel("Heading", window), Role.HEADING_1)
        qtbot.addWidget(window)
        window.show()

        set_body_size(14)
        qtbot.wait(1)

        assert label.font().pointSizeF() == pytest.approx(14 * HEADING_SCALES[Role.HEADING_1])
    finally:
        qapp.setStyleSheet(saved)
