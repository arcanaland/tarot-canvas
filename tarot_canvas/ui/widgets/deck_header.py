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
from tarot_canvas.ui.widgets.tag_chips import TagChips, normalized_tags

TITLE_SCALE = 1.3
SUBTITLE_SCALE = 0.85

MEASURE_CHARACTERS = 85

COLLAPSED_COVER_UNITS = 3

DETAIL_FIELDS = (
    ("description", "Description"),
    ("license", "License"),
    ("copyright", "Copyright"),
    ("attribution", "Attribution"),
    ("publisher", "Publisher"),
    ("website", "Website"),
    ("created_date", "Created"),
    ("updated_date", "Updated"),
    ("published_date", "Published"),
    ("tags", "Tags"),
    ("id", "Identifier"),
    ("version", "Version"),
    ("schema_version", "Schema version"),
)

DATE_KEYS = ("created_date", "updated_date", "published_date")
BANNER_PADDING = 2 * units.LARGE_SPACING
DETAILS_GAP = 2 * units.LARGE_SPACING
EDGE_MARGIN = 2 * units.LARGE_SPACING
BANNER_SAMPLE_WIDTH = 24
BANNER_SCRIM_ALPHA = 165
BANNER_TEXT = QColor(255, 255, 255)
BANNER_SUBTEXT = QColor(255, 255, 255, 190)
BANNER_OUTLINE = QColor(255, 255, 255, 64)


def cover_size(expanded):
    """(width, height) of the cover well."""
    if expanded:
        return units.cover_size(units.DENSITY_SMALL)
    width = COLLAPSED_COVER_UNITS * units.GRID_UNIT
    return width, round(width * units.COVER_ASPECT)


def format_value(value):
    if value is None or isinstance(value, bool):
        return None if value is None else ("Yes" if value else "No")

    if isinstance(value, list | tuple):
        parts = [format_value(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None

    # skip sub-tables
    if isinstance(value, dict):
        return None

    text = str(value).strip()
    return text or None


def format_date(text):
    date = QDate.fromString(text, Qt.DateFormat.ISODate)

    if not date.isValid():
        return text

    locale = QLocale.system()
    pattern = locale.dateFormat(QLocale.FormatType.LongFormat)

    for weekday in ("dddd, ", ", dddd", "dddd ", " dddd", "dddd"):
        pattern = pattern.replace(weekday, "")

    return locale.toString(date, pattern.strip()) or text


def detail_rows(fields):
    """Rows for the fields we have a label for, in DETAIL_FIELDS order.

    A `[deck]` key outside DETAIL_FIELDS is not presented. Labelling it with its
    raw TOML key read as a defect against 1.0 decks and does not survive 2.0,
    which adds `identifier`, `packager`, `pips`, `redistribution`, `derivation`
    and `license_files` to a table this widget renders in full.
    """
    rows = []
    for key, label in DETAIL_FIELDS:
        text = format_value(fields.get(key))
        if not text:
            continue
        if key in DATE_KEYS:
            text = format_date(text)
        rows.append((label, text, key))
    return rows


def wrapped_height(text, font, width):
    if not text or width <= 0:
        return 0
    metrics = QFontMetrics(font)
    bounds = metrics.boundingRect(QRect(0, 0, width, 1 << 20), int(Qt.TextFlag.TextWordWrap), text)
    return bounds.height()


def _is_link(value):
    return value.startswith("http://") or value.startswith("https://")


class DeckHeader(QWidget):
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
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(EDGE_MARGIN, units.LARGE_SPACING, EDGE_MARGIN, units.LARGE_SPACING)
        outer.setSpacing(units.LARGE_SPACING)

        self.row = QHBoxLayout()
        self.row.setSpacing(units.LARGE_SPACING)
        self.row.addWidget(self._build_cover(), 0, Qt.AlignmentFlag.AlignTop)

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
        fields = self.deck.get_metadata_fields()
        for label, value, key in detail_rows(fields):
            name = QLabel(f"{label}:")
            name.setForegroundRole(QPalette.ColorRole.PlaceholderText)

            if key == "tags":
                form.addRow(name, self._build_tag_chips(fields.get("tags")))
                continue

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

    def _build_tag_chips(self, raw):
        chips = TagChips(normalized_tags(raw), self.measure())
        chips.setFixedWidth(self.measure())
        chips.setMinimumHeight(chips.heightForWidth(self.measure()))
        self.detail_labels["tags"] = chips
        return chips

    # -- content ----------------------------------------------------------

    def subtitle_text(self):
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
        self._apply_expanded(self.details_button.isChecked())

    def _on_toggled(self, expanded):
        self._settings.setValue(DECK_HEADER_EXPANDED_KEY, bool(expanded))
        self._apply_expanded(expanded)

    # -- banner -----------------------------------------------------------

    def banner_rect(self):
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

        # upscale the tiny decode smoothly (blur)
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
