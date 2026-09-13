"""A passage's measurements, shared by the real passages and their ghosts so they can't drift.

After the KDE HIG: title and author are one group (hig/layout_and_nav.md:45), and long text
is capped at about 85 characters a line, with wider views centring it rather than
stretching it (hig/text_and_labels.md:86). The padding inside a passage is a Kirigami gridUnit.
"""

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
# Near enough to English prose's mix of letters and spaces to turn characters into pixels
_PROSE_SAMPLE = "the quick brown fox jumps over the lazy dog "


def measure(font):
    """The width of MEASURE_CHARS characters of prose set in `font`"""
    advance = QFontMetricsF(font).horizontalAdvance(_PROSE_SAMPLE)
    return round(advance / len(_PROSE_SAMPLE) * MEASURE_CHARS)


def column_width(font):
    """The reading column, margins and padding included"""
    return measure(font) + 2 * PADDING + 2 * SIDE_MARGIN
