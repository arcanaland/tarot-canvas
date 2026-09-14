from PyQt6.QtGui import QFontMetricsF

SIDE_MARGIN = 10  # the page's edge to a passage
TOP_MARGIN = 5
PASSAGE_SPACING = 20  # between passages
PADDING = 18  # inside a passage: Kirigami's gridUnit
CORNER_RADIUS = 4

TITLE_PIXEL_SIZE = 16
TITLE_TO_AUTHOR = 0  # the HIG's title-to-subtitle spacing
HEADING_TO_BODY = 8  # largeSpacing; the HIG's row says smallSpacing (4). Tune by eye
BODY_LINE_HEIGHT = 1.3  # of the font's own line height
PARAGRAPH_GAP = 12  # Qt's default <p> margin, which the passages had before

MEASURE_CHARS = 85
_PROSE_SAMPLE = "the quick brown fox jumps over the lazy dog "


def measure(font):
    """The width of MEASURE_CHARS characters of prose set in `font`"""
    advance = QFontMetricsF(font).horizontalAdvance(_PROSE_SAMPLE)
    return round(advance / len(_PROSE_SAMPLE) * MEASURE_CHARS)


def column_width(font):
    """The reading column, margins and padding included"""
    return measure(font) + 2 * PADDING + 2 * SIDE_MARGIN
