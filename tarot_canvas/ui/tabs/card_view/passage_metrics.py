import html

from PyQt6.QtGui import QFontMetricsF

SIDE_MARGIN = 10  # the page's edge to a passage
TOP_MARGIN = 5
PASSAGE_SPACING = 20  # between passages
PADDING = 18  # inside a passage: Kirigami's gridUnit
CORNER_RADIUS = 4

TITLE_TO_AUTHOR = 0  # the HIG's title-to-subtitle spacing
HEADING_TO_BODY = 8  # largeSpacing; the HIG's row says smallSpacing (4). Tune by eye
# The source line and lead to the first row: as far as the frame's edge is from them, and
# further than rows are from each other, so they read as the frame's header
HEADER_TO_ROWS = PADDING
BODY_LINE_HEIGHT = 1.3  # of the font's own line height
PARAGRAPH_GAP = 12  # Qt's default <p> margin, which the passages had before
LIST_ITEM_GAP = 3  # between a list's items, such as a source's questions. Tune by eye
FOLD_INDENT = 16  # a fold inside a fold, such as one group among the groups. Tune by eye

MEASURE_CHARS = 85
_PROSE_SAMPLE = "the quick brown fox jumps over the lazy dog "


def line_height_css():
    return f"line-height: {round(BODY_LINE_HEIGHT * 100)}%"


def body_html(text):
    """Plain text as rich text: paragraphs at blank lines, line breaks at newlines.

    Escaped first: it came from a file the app doesn't control.
    """
    return "".join(
        f'<p style="margin: {PARAGRAPH_GAP if i else 0}px 0 0 0; {line_height_css()}">'
        + paragraph.replace("\n", "<br>")
        + "</p>"
        for i, paragraph in enumerate(html.escape(text).split("\n\n"))
    )


def measure(font):
    """The width of MEASURE_CHARS characters of prose set in `font`"""
    advance = QFontMetricsF(font).horizontalAdvance(_PROSE_SAMPLE)
    return round(advance / len(_PROSE_SAMPLE) * MEASURE_CHARS)


def column_width(font):
    """The reading column, margins and padding included"""
    return measure(font) + 2 * PADDING + 2 * SIDE_MARGIN
