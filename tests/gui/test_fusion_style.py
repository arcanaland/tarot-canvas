"""The Mac's widget style: Fusion with Breeze's scrollbars and tab close cross."""

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPalette
from PyQt6.QtWidgets import QScrollBar, QStyle, QStyleOption, QStyleOptionSlider

from tarot_canvas.ui import fusion_style
from tarot_canvas.ui.fusion_style import (
    HANDLE_MIN,
    SCROLLBAR_EXTENT,
    TAB_CLOSE_ICON,
    breeze_fusion,
)
from tarot_canvas.utils.theme_manager import ICON_THEMES

SC = QStyle.SubControl
CC = QStyle.ComplexControl


@pytest.fixture
def style(qapp):
    return breeze_fusion()


@pytest.fixture
def bar(qtbot, style):
    bar = QScrollBar(Qt.Orientation.Vertical)
    bar.setStyle(style)
    bar.setRange(0, 900)
    bar.setPageStep(100)
    bar.resize(SCROLLBAR_EXTENT, 400)
    qtbot.addWidget(bar)
    return bar


def rect_of(bar, sub):
    option = QStyleOptionSlider()
    bar.initStyleOption(option)
    return bar.style().subControlRect(CC.CC_ScrollBar, option, sub, bar)


def test_it_is_fusion_underneath(style):
    assert style.baseStyle().name().lower() == "fusion"


def test_the_bar_is_thin_and_has_no_arrows(bar):
    assert bar.sizeHint().width() == SCROLLBAR_EXTENT
    assert rect_of(bar, SC.SC_ScrollBarAddLine).isEmpty()
    assert rect_of(bar, SC.SC_ScrollBarSubLine).isEmpty()
    assert rect_of(bar, SC.SC_ScrollBarGroove) == bar.rect()


def test_the_handle_is_sized_by_the_page_and_moves_with_the_value(bar):
    top = rect_of(bar, SC.SC_ScrollBarSlider)
    assert top.top() == 0
    assert top.height() == 400 * 100 // 1000

    bar.setValue(bar.maximum())
    bottom = rect_of(bar, SC.SC_ScrollBarSlider)
    assert bottom.bottom() == bar.rect().bottom()
    assert bottom.height() == top.height()


def test_a_long_document_keeps_a_grabbable_handle(bar):
    bar.setRange(0, 1_000_000)

    assert rect_of(bar, SC.SC_ScrollBarSlider).height() == HANDLE_MIN


def test_the_pages_lie_either_side_of_the_handle(bar):
    bar.setValue(450)
    slider = rect_of(bar, SC.SC_ScrollBarSlider)

    assert rect_of(bar, SC.SC_ScrollBarSubPage).bottom() == slider.top() - 1
    assert rect_of(bar, SC.SC_ScrollBarAddPage).top() == slider.bottom() + 1


def test_a_click_above_the_handle_pages_up(bar):
    bar.setValue(bar.maximum())
    option = QStyleOptionSlider()
    bar.initStyleOption(option)
    hit = bar.style().hitTestComplexControl(CC.CC_ScrollBar, option, bar.rect().topLeft(), bar)

    assert hit == SC.SC_ScrollBarSubPage


def painted(draw, side=24):
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw(painter, QRect(0, 0, side, side))
    painter.end()
    return image


def opaque(image):
    return sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha()
    )


@pytest.fixture
def bundled_icons(qapp):
    paths, name = QIcon.themeSearchPaths(), QIcon.themeName()
    QIcon.setThemeSearchPaths([ICON_THEMES])
    QIcon.setThemeName("breeze")
    yield
    QIcon.setThemeSearchPaths(paths)
    QIcon.setThemeName(name)


def test_the_tab_close_cross_is_bundled(bundled_icons):
    assert not QIcon.fromTheme(TAB_CLOSE_ICON).isNull()


@pytest.mark.parametrize("hovered", [False, True])
def test_the_tab_close_button_draws_the_cross(style, bundled_icons, hovered):
    def draw(painter, rect):
        option = QStyleOption()
        option.rect = rect
        option.palette = QPalette(QColor("white"))
        option.state = QStyle.StateFlag.State_Enabled
        if hovered:
            option.state |= QStyle.StateFlag.State_MouseOver
        style.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorTabClose, option, painter)

    image = painted(draw)

    assert opaque(image)
    # Hover fills the button's rounded rect behind the cross; at rest only the cross is drawn
    corner_inside_radius = image.pixelColor(12, 1).alpha()
    assert bool(corner_inside_radius) == hovered


def test_the_handle_darkens_on_hover():
    palette = QPalette(QColor("white"))
    rest = fusion_style.handle_colour(palette, hovered=False)
    hover = fusion_style.handle_colour(palette, hovered=True)

    assert rest.rgb() == hover.rgb() == palette.color(QPalette.ColorRole.WindowText).rgb()
    assert hover.alphaF() > rest.alphaF()
