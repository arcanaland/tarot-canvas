import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter, QPalette

from tarot_canvas.models.coverage import CellState
from tarot_canvas.ui.library.coverage_strip import (
    GRID_MAX_CELL_WIDTH,
    RUN_GAP,
    RUNS,
    cell_rects,
    grid_cell_rects,
    grid_label_width,
    minimum_width,
    paint_coverage_grid,
    paint_coverage_strip,
)
from tests.conftest import THEME_COLOURS

HEIGHT = 10


@pytest.fixture(params=sorted(THEME_COLOURS))
def list_palette(request, qapp):
    """A list view's palette: Text over Base, light and dark"""
    text, base = THEME_COLOURS[request.param]
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Text, QColor(*text))
    palette.setColor(QPalette.ColorRole.Base, QColor(*base))
    return palette


def paint(palette, states, width):
    image = QImage(width, HEIGHT, QImage.Format.Format_ARGB32)
    background = palette.color(QPalette.ColorRole.Base)
    image.fill(background)
    painter = QPainter(image)
    paint_coverage_strip(painter, QRect(0, 0, width, HEIGHT), states, palette)
    painter.end()
    return image, background


def centre(image, cell):
    return image.pixelColor(int(cell.center().x()), HEIGHT // 2)


def test_filled_faint_and_empty_cells_differ_from_each_other(list_palette):
    states = [CellState.FILLED, CellState.FAINT, CellState.EMPTY] * 26
    width = 400
    image, _ = paint(list_palette, states, width)

    rects = cell_rects(QRect(0, 0, width, HEIGHT))
    filled, faint, empty = (centre(image, rects[i]) for i in range(3))

    assert len({filled.rgb(), faint.rgb(), empty.rgb()}) == 3


def test_an_empty_cell_is_still_drawn(list_palette):
    width = 400
    image, background = paint(list_palette, [CellState.EMPTY] * 78, width)

    (first, *_) = cell_rects(QRect(0, 0, width, HEIGHT))
    assert centre(image, first) != background


def test_the_four_gaps_between_runs_are_background(list_palette):
    width = 400
    image, background = paint(list_palette, [CellState.FILLED] * 78, width)

    rects = cell_rects(QRect(0, 0, width, HEIGHT))
    ends = [sum(RUNS[: i + 1]) for i in range(len(RUNS) - 1)]
    for end in ends:
        last, first = rects[end - 1], rects[end]
        assert first.left() - last.right() >= RUN_GAP
        gap_x = int((last.right() + first.left()) / 2)
        assert image.pixelColor(gap_x, HEIGHT // 2) == background


def test_too_narrow_for_two_pixel_cells_paints_nothing(list_palette):
    width = minimum_width() - 1
    image, background = paint(list_palette, [CellState.FILLED] * 78, width)

    assert all(image.pixelColor(x, HEIGHT // 2) == background for x in range(width))


def test_at_the_minimum_width_every_cell_is_drawn(list_palette):
    width = minimum_width()
    rects = cell_rects(QRect(0, 0, width, HEIGHT))

    assert len(rects) == 78
    assert all(rect.width() >= 2 for rect in rects)
    assert rects[-1].right() <= width


# -- the details pane's grid ------------------------------------------------


def paint_grid(palette, states, width, height=120):
    from PyQt6.QtGui import QFont

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    background = palette.color(QPalette.ColorRole.Base)
    image.fill(background)
    painter = QPainter(image)
    paint_coverage_grid(painter, QRect(0, 0, width, height), states, palette, GRID_LABELS, QFont())
    painter.end()
    return image, background


GRID_LABELS = ("M", "W", "C", "S", "P")


def test_the_grid_has_a_row_per_run_each_starting_at_one_left_edge(qapp):
    rects = grid_cell_rects(QRect(0, 0, 400, 120), 20)

    assert len(rects) == sum(RUNS)
    starts = [0, *[sum(RUNS[:i]) for i in range(1, len(RUNS))]]
    assert len({rects[i].left() for i in starts}) == 1
    assert len({rects[i].top() for i in starts}) == len(RUNS)


def test_grid_cells_are_card_shaped_and_capped(qapp):
    (first, *_) = grid_cell_rects(QRect(0, 0, 2000, 400), 20)

    assert first.width() == GRID_MAX_CELL_WIDTH
    assert first.height() > first.width()


def test_a_grid_too_narrow_paints_nothing(list_palette):
    image, background = paint_grid(list_palette, [CellState.FILLED] * 78, 60)

    assert grid_cell_rects(QRect(0, 0, 60, 120), 20) == []
    assert all(image.pixelColor(x, y) == background for x in range(60) for y in range(0, 120, 7))


def test_grid_cells_take_the_strips_colours(list_palette):
    states = [CellState.FILLED, CellState.FAINT, CellState.EMPTY] * 26
    image, _ = paint_grid(list_palette, states, 400)
    from PyQt6.QtGui import QFont, QFontMetrics

    label_width = grid_label_width(GRID_LABELS, QFontMetrics(QFont()))
    rects = grid_cell_rects(QRect(0, 0, 400, 120), label_width)
    filled, faint, empty = (
        image.pixelColor(int(rects[i].center().x()), int(rects[i].center().y())) for i in range(3)
    )

    assert len({filled.rgb(), faint.rgb(), empty.rgb()}) == 3


# -- colour ---------------------------------------------------------------


def run_starts():
    return [sum(RUNS[:i]) for i in range(len(RUNS))]


def test_each_run_is_filled_in_its_arcanas_colour(list_palette):
    from tarot_canvas.ui.card_colours import ARCANA_KEYS, CARD_COLOURS

    width = 400
    image, _ = paint(list_palette, [CellState.FILLED] * 78, width)
    rects = cell_rects(QRect(0, 0, width, HEIGHT))

    for key, start in zip(ARCANA_KEYS, run_starts(), strict=True):
        assert centre(image, rects[start]).rgb() == QColor(CARD_COLOURS[key]).rgb()


def test_uncoloured_every_run_takes_text(list_palette):
    width = 400
    image = QImage(width, HEIGHT, QImage.Format.Format_ARGB32)
    image.fill(list_palette.color(QPalette.ColorRole.Base))
    painter = QPainter(image)
    paint_coverage_strip(
        painter, QRect(0, 0, width, HEIGHT), [CellState.FILLED] * 78, list_palette, coloured=False
    )
    painter.end()
    rects = cell_rects(QRect(0, 0, width, HEIGHT))

    text = list_palette.color(QPalette.ColorRole.Text).rgb()
    assert {centre(image, rects[start]).rgb() for start in run_starts()} == {text}


def test_an_empty_cell_is_the_same_in_every_run(list_palette):
    width = 400
    image, _ = paint(list_palette, [CellState.EMPTY] * 78, width)
    rects = cell_rects(QRect(0, 0, width, HEIGHT))

    assert len({centre(image, rects[start]).rgb() for start in run_starts()}) == 1
