import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter, QPalette

from tarot_canvas.ui.palette import subtle_fill
from tarot_canvas.ui.tabs.card_view.ghost_passages import ghost_layout, paint_ghost_passages
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    SIDE_MARGIN,
    TOP_MARGIN,
    column_width,
)

WIDTH, HEIGHT = 300, 600


def paint(palette, dpr=1, width=WIDTH):
    """The image, pre-filled with Window, and the painter's font."""
    image = QImage(width * dpr, HEIGHT * dpr, QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(dpr)
    image.fill(palette.color(QPalette.ColorRole.Window))
    painter = QPainter(image)
    font = painter.font()
    paint_ghost_passages(painter, QRect(0, 0, width, HEIGHT), palette)
    painter.end()
    return image, font


def first_ghost_bars(font, width=WIDTH):
    """The first ghost's bars, where paint_ghost_passages puts them in a `width` rect"""
    column = min(width, column_width(font))
    left = (width - column) / 2 + SIDE_MARGIN
    bars, _ = ghost_layout(font, column - 2 * SIDE_MARGIN)
    return [bar.translated(left, TOP_MARGIN) for bar in bars]


def pixel(image, x, y):
    dpr = round(image.devicePixelRatio())
    return image.pixelColor(round(x * dpr), round(y * dpr))


def composited(over, under):
    a = over.alphaF()
    return [
        getattr(over, c)() * a + getattr(under, c)() * (1 - a) for c in ("red", "green", "blue")
    ]


@pytest.mark.parametrize("dpr", [1, 2])
def test_the_first_title_bar_shows(theme_palette, dpr):
    image, font = paint(theme_palette, dpr)

    title = first_ghost_bars(font)[0]
    inside = pixel(image, title.left() + 4, title.center().y())
    assert inside != theme_palette.color(QPalette.ColorRole.Window)


def test_between_bars_is_the_passage_fill(theme_palette):
    image, font = paint(theme_palette)

    title, author = first_ghost_bars(font)[:2]
    between = pixel(image, title.left() + 4, (title.bottom() + author.top()) / 2)
    expected = composited(
        subtle_fill(theme_palette), theme_palette.color(QPalette.ColorRole.Window)
    )
    # The fade has barely begun this near the top
    got = [between.red(), between.green(), between.blue()]
    assert got == pytest.approx(expected, abs=1)


def test_the_title_and_author_group_apart_from_the_body(qapp):
    """The HIG's grouping: nothing between title and subtitle, a gap before the content"""
    _, font = paint(QPalette())
    title, author, body = first_ghost_bars(font)[:3]

    assert author.top() - title.bottom() < body.top() - author.bottom()


def test_a_wide_view_keeps_the_ghosts_to_the_reading_column(theme_palette):
    wide = 1600
    image, font = paint(theme_palette, width=wide)
    assert column_width(font) < wide

    title = first_ghost_bars(font, wide)[0]
    background = theme_palette.color(QPalette.ColorRole.Window)
    assert pixel(image, title.left() + 4, title.center().y()) != background
    assert pixel(image, SIDE_MARGIN + 2, title.center().y()) == background
    assert pixel(image, wide - SIDE_MARGIN - 2, title.center().y()) == background


@pytest.mark.parametrize("dpr", [1, 2])
def test_the_fade_reaches_nothing_at_the_bottom_row(theme_palette, dpr):
    image, _ = paint(theme_palette, dpr)

    background = QColor(theme_palette.color(QPalette.ColorRole.Window))
    bottom = image.height() - 1
    assert all(image.pixelColor(x, bottom) == background for x in range(image.width()))


def test_painting_is_deterministic(theme_palette):
    assert paint(theme_palette)[0] == paint(theme_palette)[0]


def test_a_rect_too_small_to_hold_a_ghost_paints_nothing(theme_palette):
    image = QImage(8, 4, QImage.Format.Format_ARGB32)
    image.fill(theme_palette.color(QPalette.ColorRole.Window))
    before = QImage(image)
    painter = QPainter(image)
    paint_ghost_passages(painter, QRect(0, 0, 8, 4), theme_palette)
    painter.end()

    assert image == before
