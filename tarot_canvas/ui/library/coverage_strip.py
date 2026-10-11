"""A source's coverage as 78 cells"""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPalette

from tarot_canvas.models.coverage import CellState
from tarot_canvas.ui.card_colours import ARCANA_KEYS, CARD_COLOURS
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import with_alpha

# Majors, then wands, cups, swords and pentacles, in canonical order
RUNS = (22, 14, 14, 14, 14)
RUN_GAP = 4
MIN_CELL_WIDTH = 2
# From this width a cell is drawn a pixel narrower, so neighbours read as separate cells
SEPARATED_CELL_WIDTH = 4

FAINT_ALPHA = 0.30
EMPTY_ALPHA = 0.10


def minimum_width():
    return sum(RUNS) * MIN_CELL_WIDTH + (len(RUNS) - 1) * RUN_GAP


def cell_width(width):
    return (width - (len(RUNS) - 1) * RUN_GAP) / sum(RUNS)


def cell_rects(rect):
    width = cell_width(rect.width())
    if width < MIN_CELL_WIDTH:
        return []
    drawn = width - 1 if width >= SEPARATED_CELL_WIDTH else width

    rects = []
    left = float(rect.left())
    for run in RUNS:
        for _ in range(run):
            rects.append(QRectF(left, rect.top(), drawn, rect.height()))
            left += width
        left += RUN_GAP

    return rects


def cell_colours(palette, coloured=True):
    text = palette.text().color()
    empty = with_alpha(text, EMPTY_ALPHA)
    colours = []
    for key, run in zip(ARCANA_KEYS, RUNS, strict=True):
        base = QColor(CARD_COLOURS[key]) if coloured else text
        state_colours = {
            CellState.FILLED: base,
            CellState.FAINT: with_alpha(base, FAINT_ALPHA),
            CellState.EMPTY: empty,
        }
        colours.extend([state_colours] * run)
    return colours


def paint_coverage_strip(painter, rect, states, palette, coloured=True):
    rects = cell_rects(rect)
    if not rects:
        return
    colours = cell_colours(palette, coloured)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for cell, state, cell_colour in zip(rects, states, colours, strict=False):
        painter.fillRect(cell, cell_colour[state])
    painter.restore()


# The details pane's grid: a labelled row per run, of card-shaped cells
GRID_CELL_GAP = 2
GRID_ROW_GAP = 4
GRID_LABEL_GAP = 8
GRID_MIN_CELL_WIDTH = 4
GRID_MAX_CELL_WIDTH = 12


def grid_label_width(labels, metrics):
    return max((metrics.horizontalAdvance(label) for label in labels), default=0)


def grid_cell_size(width, label_width):
    """A cell's (width, height) for a grid `width` wide, or None when it would be too narrow"""
    longest = max(RUNS)
    cells = width - label_width - GRID_LABEL_GAP - (longest - 1) * GRID_CELL_GAP
    cell_w = min(GRID_MAX_CELL_WIDTH, cells // longest)
    if cell_w < GRID_MIN_CELL_WIDTH:
        return None
    return cell_w, round(cell_w * units.COVER_ASPECT)


def grid_height(width, label_width):
    size = grid_cell_size(width, label_width)
    if size is None:
        return 0
    return len(RUNS) * size[1] + (len(RUNS) - 1) * GRID_ROW_GAP


def grid_cell_rects(rect, label_width):
    """One QRectF per cell, row by row, or none when `rect` is too narrow"""
    size = grid_cell_size(rect.width(), label_width)
    if size is None:
        return []
    cell_w, cell_h = size
    rects = []
    top = float(rect.top())
    for run in RUNS:
        left = float(rect.left() + label_width + GRID_LABEL_GAP)
        for _ in range(run):
            rects.append(QRectF(left, top, cell_w, cell_h))
            left += cell_w + GRID_CELL_GAP
        top += cell_h + GRID_ROW_GAP
    return rects


def paint_coverage_grid(painter, rect, states, palette, labels, font, hovered=None):
    metrics = QFontMetrics(font)
    label_width = grid_label_width(labels, metrics)
    rects = grid_cell_rects(rect, label_width)
    if not rects:
        return

    colours = cell_colours(palette)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)

    for cell, state, cell_colour in zip(rects, states, colours, strict=False):
        painter.fillRect(cell, cell_colour[state])
    if hovered is not None and 0 <= hovered < len(rects):
        painter.fillRect(rects[hovered], palette.color(QPalette.ColorRole.Highlight))
    painter.setFont(font)
    painter.setPen(palette.color(QPalette.ColorRole.PlaceholderText))
    first = 0
    for label, run in zip(labels, RUNS, strict=False):
        row = rects[first]
        label_rect = QRectF(rect.left(), row.top(), label_width, row.height())
        painter.drawText(
            label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label
        )
        first += run

    painter.restore()
