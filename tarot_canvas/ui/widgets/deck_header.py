"""The deck-level header shown inline at the top of a deck view tab.

Replaces the modal "Deck Info" dialog. Collapsed, the header is an identity strip —
cover, title, subtitle — carrying the same grammar as the library delegate, so a deck
reads as the same object in the grid and in its own tab. `Details` discloses the rest of
the `[deck]` table, led by the description and then licence and attribution, since those
are the ones a deck's licence may actually oblige the app to surface.

The cover shrinks with the disclosure: at the library's own cover size it would be the
tallest thing in the collapsed strip by a factor of two, and the header would be mostly
the empty column beside it.
"""

from PyQt6.QtCore import QDate, QLocale, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFontMetrics,
    QImageReader,
    QPainter,
    QPalette,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.settings import (
    DECK_HEADER_EXPANDED_DEFAULT,
    DECK_HEADER_EXPANDED_KEY,
    get_settings,
)
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_model import deck_cover_path

TITLE_SCALE = 1.3
SUBTITLE_SCALE = 0.85

#: The HIG's ~85-character measure, applied to the detail values.
MEASURE_CHARACTERS = 85

#: Cover-well width when collapsed, in grid units. Expanded, the well is the library's
#: own small cover.
COLLAPSED_COVER_UNITS = 3

#: `[deck]` keys the collapsed rows already show, so the details form omits them.
COLLAPSED_KEYS = ("name", "author")

#: Keys rendered in this order, with these labels, ahead of the generic tail.
DETAIL_FIELDS = (
    ("description", "Description"),
    ("license", "License"),
    ("attribution", "Attribution"),
    ("publisher", "Publisher"),
    ("website", "Website"),
    ("created_date", "Created"),
    ("updated_date", "Updated"),
    ("tags", "Tags"),
    ("id", "Identifier"),
    ("version", "Version"),
    ("schema_version", "Schema version"),
)

#: Keys whose values are dates and are rendered in the reader's locale.
DATE_KEYS = ("created_date", "updated_date")

#: Vertical padding inside the banner, above the title and below the subtitle. Larger
#: than the collapsed strip's, which stays tight on purpose — a banner needs to read as
#: a band with room in it, where the collapsed strip is only an identity line.
BANNER_PADDING = 2 * units.LARGE_SPACING

#: Gap between the banner's bottom edge and the first row of the detail form. Without it
#: the form starts exactly where the band ends, since the band's own bottom padding is
#: measured from the subtitle.
DETAILS_GAP = 2 * units.LARGE_SPACING

#: Side margin for the header's content. Everything below the header in the deck view
#: uses the same value, so the cover's edge and the section titles line up.
EDGE_MARGIN = 2 * units.LARGE_SPACING

#: Width, in pixels, the cover is decoded to before being scaled back up. This is the
#: blur: a box filter at this radius would cost a convolution per repaint, where a
#: smooth upscale from a tiny decode costs one `QImageReader` call, cached.
BANNER_SAMPLE_WIDTH = 24

#: Opacity of the black scrim composited over the blurred cover, out of 255. This is
#: what makes the banner safe to put fixed light text on: the scrim bounds the result to
#: at most `255 - BANNER_SCRIM_ALPHA` per channel whatever the deck's artwork is, so the
#: contrast floor against `BANNER_TEXT` is a property of this constant, not of the deck.
#: See `test_the_banner_guarantees_a_contrast_floor`.
BANNER_SCRIM_ALPHA = 165

#: Text on the banner. Not palette-derived, deliberately: the scrim above owns the
#: backdrop's luminance, so the active colour scheme is the wrong source here — under a
#: light scheme its text colour would be dark-on-dark. Everything outside the banner
#: stays palette-derived.
BANNER_TEXT = QColor(255, 255, 255)
BANNER_SUBTEXT = QColor(255, 255, 255, 190)

#: The HIG asks for a contrasting outline on anything overlaid on the content area, or
#: it blends into the background under a dark scheme (`hig/displaying_content.md:62`).
BANNER_OUTLINE = QColor(255, 255, 255, 64)


def cover_size(expanded):
    """(width, height) of the cover well in the given disclosure state."""
    if expanded:
        return units.cover_size(units.DENSITY_SMALL)
    width = COLLAPSED_COVER_UNITS * units.GRID_UNIT
    return width, round(width * units.COVER_ASPECT)


def format_value(value):
    """Render one `[deck]` value as a display string, or None if it has no scalar form."""
    if value is None or isinstance(value, bool):
        return None if value is None else ("Yes" if value else "No")
    if isinstance(value, list | tuple):
        parts = [format_value(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None
    if isinstance(value, dict):
        # Sub-tables (`[deck.excluded_cards]`) have their own surfaces; a flattened
        # dump here would be noise.
        return None
    text = str(value).strip()
    return text or None


def format_date(text):
    """An ISO-8601 date in the reader's locale, or `text` unchanged if it is not one.

    Deck dates are `YYYY-MM-DD` strings in practice, but TOML also permits a bare date
    literal and nothing stops a deck writing a partial date, so anything QDate rejects
    is passed through as the deck wrote it.
    """
    date = QDate.fromString(text, Qt.DateFormat.ISODate)
    if not date.isValid():
        return text

    locale = QLocale.system()
    # The locale's own long form, minus the weekday: en_US spells it "dddd, MMMM d,
    # yyyy", and "Wednesday" says nothing useful about a deck published in 1909.
    pattern = locale.dateFormat(QLocale.FormatType.LongFormat)
    for weekday in ("dddd, ", ", dddd", "dddd ", " dddd", "dddd"):
        pattern = pattern.replace(weekday, "")
    return locale.toString(date, pattern.strip()) or text


def detail_rows(fields):
    """(label, value, key) triples for the details form, in display order.

    Known keys come first in `DETAIL_FIELDS` order; anything else the deck declares
    follows under its raw key, so a deck using a field this app predates still shows it.
    """
    rows = []
    named = set()
    for key, label in DETAIL_FIELDS:
        named.add(key)
        text = format_value(fields.get(key))
        if not text:
            continue
        if key in DATE_KEYS:
            text = format_date(text)
        rows.append((label, text, key))

    for key, value in fields.items():
        if key in named or key in COLLAPSED_KEYS:
            continue
        text = format_value(value)
        if text:
            rows.append((key, text, key))
    return rows


def wrapped_height(text, font, width):
    """The height `text` needs when word-wrapped to `width`.

    Measured directly rather than left to `heightForWidth`, which does not propagate
    reliably through the nested box layouts this header is built from — the symptom is
    a long licence or attribution clipped to one line.
    """
    if not text or width <= 0:
        return 0
    metrics = QFontMetrics(font)
    bounds = metrics.boundingRect(QRect(0, 0, width, 1 << 20), int(Qt.TextFlag.TextWordWrap), text)
    return bounds.height()


def _is_link(value):
    return value.startswith("http://") or value.startswith("https://")


class DeckHeader(QWidget):
    """Cover, title and subtitle for one deck, with the rest behind `Details`."""

    def __init__(self, deck, parent=None, cover_cache=None, settings=None):
        super().__init__(parent)
        self.deck = deck
        self._cover_cache = cover_cache or CoverCache(capacity=8)
        self._settings = settings if settings is not None else get_settings()
        self._banner_pixmaps = {}

        self._build()
        self._restore_expanded()

    # -- construction -----------------------------------------------------

    def _build(self):
        # Hug the content: the deck view gives its vertical slack to the card rows.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        outer = QVBoxLayout(self)
        # Wider at the sides than top and bottom: the banner bleeds to the view's edges,
        # so this margin is all that keeps the title off them, while the vertical margin
        # still has the separator and the card rows below to breathe against.
        outer.setContentsMargins(EDGE_MARGIN, units.LARGE_SPACING, EDGE_MARGIN, units.LARGE_SPACING)
        outer.setSpacing(units.LARGE_SPACING)

        self.row = QHBoxLayout()
        self.row.setSpacing(units.LARGE_SPACING)
        self.row.addWidget(self._build_cover(), 0, Qt.AlignmentFlag.AlignTop)

        # The text column is shorter than the cover when collapsed; it is aligned within
        # the row rather than stretched, so `_apply_expanded` can centre it against the
        # cover instead of leaving a hole under it.
        self.text_container = QWidget()
        self.text_container.setLayout(self._build_text_column())
        self.row.addWidget(self.text_container, 1)
        outer.addLayout(self.row)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        outer.addWidget(separator)

    def _build_cover(self):
        self.cover_label = QLabel()
        self.cover_label.setWordWrap(True)
        self.cover_label.setAccessibleName(f"Cover of {self.deck.get_name()}")
        self._cover_path = deck_cover_path(self.deck)
        self._apply_cover(expanded=False)
        return self.cover_label

    def _apply_cover(self, expanded):
        width, height = cover_size(expanded)
        self.cover_label.setFixedSize(width, height)

        pixmap = self._cover_cache.get(
            self._cover_path, self.cover_label.size(), self.devicePixelRatioF()
        )
        if pixmap is not None:
            self.cover_label.setPixmap(pixmap)
            self.cover_label.setAlignment(
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
            )
        else:
            self.cover_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
            self.cover_label.setText("No cover")
            self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _build_text_column(self):
        base = QApplication.font()
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(units.LARGE_SPACING)

        self.title_label = QLabel(self.deck.get_name())
        self.title_label.setFont(units.scaled_font(base, TITLE_SCALE, bold=True))
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        title_row.addWidget(self.title_label)
        title_row.addStretch()

        self.details_button = QToolButton()
        self.details_button.setText("Details")
        self.details_button.setCheckable(True)
        self.details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_button.setToolTip("Show the rest of this deck's metadata")
        self.details_button.toggled.connect(self._on_toggled)
        title_row.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(title_row)

        self.subtitle_label = QLabel(self.subtitle_text())
        self.subtitle_label.setFont(units.scaled_font(base, SUBTITLE_SCALE))
        self.subtitle_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.subtitle_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self.subtitle_label)

        self.details_widget = self._build_details()
        column.addSpacing(BANNER_PADDING + DETAILS_GAP)
        column.addWidget(self.details_widget)
        return column

    def _build_details(self):
        details = QWidget()
        form = QFormLayout(details)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(units.LARGE_SPACING)
        form.setVerticalSpacing(units.SMALL_SPACING)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        self.detail_labels = {}
        for label, value, key in detail_rows(self.deck.get_metadata_fields()):
            name = QLabel(f"{label}:")
            name.setForegroundRole(QPalette.ColorRole.PlaceholderText)

            field = QLabel()
            field.setWordWrap(True)
            field.setFixedWidth(self.measure())
            if key == "website" and _is_link(value):
                field.setText(f'<a href="{value}">{value}</a>')
                field.setOpenExternalLinks(True)
                field.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            else:
                field.setText(value)
                field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            field.setMinimumHeight(wrapped_height(value, field.font(), self.measure()))
            form.addRow(name, field)
            self.detail_labels[key] = field
        details.setMaximumWidth(self.measure() + self.details_label_measure())
        return details

    # -- content ----------------------------------------------------------

    def subtitle_text(self):
        """`author · N cards` — whichever of the two the deck actually declares.

        The version is a detail row: on the identity line it was a third of what the
        deck appeared to be, and every deck in the wild declares `1.0` or thereabouts.
        """
        parts = []
        author = self.deck.get_author()
        if author:
            parts.append(author)
        parts.append(f"{len(self.deck.get_all_cards())} cards")
        return " · ".join(parts)

    def details_label_measure(self):
        """Room for the form's label column, in pixels at the current font."""
        metrics = QFontMetrics(QApplication.font())
        widest = max(
            (metrics.horizontalAdvance(f"{label}:") for _, label in DETAIL_FIELDS),
            default=0,
        )
        return widest + 2 * units.LARGE_SPACING

    def measure(self):
        """The HIG's ~85-character line length, in pixels at the current font."""
        return MEASURE_CHARACTERS * max(1, QFontMetrics(QApplication.font()).averageCharWidth())

    def is_expanded(self):
        return self.details_button.isChecked()

    def set_expanded(self, expanded):
        self.details_button.setChecked(bool(expanded))

    def _restore_expanded(self):
        stored = self._settings.value(
            DECK_HEADER_EXPANDED_KEY, DECK_HEADER_EXPANDED_DEFAULT, type=bool
        )
        self.details_button.setChecked(bool(stored))
        # setChecked is a no-op when the stored value matches the default, so apply the
        # dependent state unconditionally.
        self._apply_expanded(self.details_button.isChecked())

    def _on_toggled(self, expanded):
        self._settings.setValue(DECK_HEADER_EXPANDED_KEY, bool(expanded))
        self._apply_expanded(expanded)

    # -- banner -----------------------------------------------------------

    def banner_rect(self):
        """The strip the banner occupies, empty when there is no banner to draw.

        Bounded to the title and subtitle: the detail form below keeps the active colour
        scheme's own background, so only two labels ever sit on non-palette colour.
        """
        if not self.is_expanded() or not self._cover_path:
            return QRect()
        bottom = self.subtitle_label.mapTo(self, QPoint(0, self.subtitle_label.height())).y()
        return QRect(0, 0, self.width(), bottom + BANNER_PADDING)

    def _banner_pixmap(self, size):
        """The cover, blurred and scrimmed, filling `size`. None if it cannot be read."""
        ratio = self.devicePixelRatioF()
        key = (size.width(), size.height(), round(ratio, 3))
        if key in self._banner_pixmaps:
            return self._banner_pixmaps[key]

        pixmap = self._render_banner(size, ratio)
        # One deck, a handful of widths as the window is resized.
        if len(self._banner_pixmaps) >= 16:
            self._banner_pixmaps.clear()
        self._banner_pixmaps[key] = pixmap
        return pixmap

    def _render_banner(self, size, ratio):
        reader = QImageReader(str(self._cover_path))
        reader.setAutoTransform(True)
        source = reader.size()
        if not source.isValid() or source.isEmpty():
            return None

        height = max(1, round(BANNER_SAMPLE_WIDTH * source.height() / source.width()))
        reader.setScaledSize(QSize(BANNER_SAMPLE_WIDTH, height))
        image = reader.read()
        if image.isNull():
            return None

        # Upscaling the tiny decode smoothly is the blur; expanding rather than fitting
        # keeps the strip filled, at the price of cropping a portrait cover hard — which
        # at this radius is a wash of the deck's colour rather than a picture of a card.
        device = QSize(max(1, round(size.width() * ratio)), max(1, round(size.height() * ratio)))
        image = image.scaled(
            device,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        offset = QPoint(
            max(0, (image.width() - device.width()) // 2),
            max(0, (image.height() - device.height()) // 2),
        )
        image = image.copy(QRect(offset, device))

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(ratio)

        painter = QPainter(pixmap)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, BANNER_SCRIM_ALPHA))
        painter.end()
        return pixmap

    def paintEvent(self, event):
        rect = self.banner_rect()
        if not rect.isEmpty():
            pixmap = self._banner_pixmap(rect.size())
            if pixmap is not None:
                painter = QPainter(self)
                painter.drawPixmap(rect, pixmap)
                painter.setPen(BANNER_OUTLINE)
                painter.drawLine(rect.bottomLeft(), rect.bottomRight())
                painter.end()
        super().paintEvent(event)

    def _apply_banner_text(self, on_banner):
        """Light text while the two labels sit on the banner, palette colours otherwise."""
        for label, colour, role in (
            (self.title_label, BANNER_TEXT, QPalette.ColorRole.WindowText),
            (self.subtitle_label, BANNER_SUBTEXT, QPalette.ColorRole.PlaceholderText),
        ):
            if on_banner:
                palette = QPalette()
                palette.setColor(QPalette.ColorRole.WindowText, colour)
                label.setForegroundRole(QPalette.ColorRole.WindowText)
                label.setPalette(palette)
            else:
                label.setPalette(QPalette())
                label.setForegroundRole(role)

    def _apply_expanded(self, expanded):
        expanded = bool(expanded)
        self.details_widget.setVisible(expanded and bool(self.detail_labels))
        self.details_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.details_button.setAccessibleDescription(
            "Hide deck metadata" if expanded else "Show deck metadata"
        )
        self._apply_cover(expanded)
        self.row.setAlignment(
            self.text_container,
            Qt.AlignmentFlag.AlignTop if expanded else Qt.AlignmentFlag.AlignVCenter,
        )
        banner = expanded and bool(self._cover_path)
        self._apply_banner_text(banner)
        padding = BANNER_PADDING if banner else units.LARGE_SPACING
        self.layout().setContentsMargins(EDGE_MARGIN, padding, EDGE_MARGIN, padding)
        self.update()
