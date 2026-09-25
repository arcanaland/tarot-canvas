import html

from PyQt6.QtCore import QPoint, QRect, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontMetrics, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
from tarot_canvas.ui.widgets.cover_banner import (
    BANNER_PADDING,
    BANNER_SUBTEXT,
    BANNER_TEXT,
    CoverBanner,
    set_banner_text,
)
from tarot_canvas.ui.widgets.tag_chips import TagChips, normalized_tags
from tarot_canvas.utils.dates import format_date

TITLE_SCALE = 1.3
SUBTITLE_SCALE = 0.85

MEASURE_CHARACTERS = 85

COLLAPSED_COVER_UNITS = 3

BUY_TEXT = "Buy Deck"
BUY_ICON = "wallet-open"

# a row per 2.0 link rel; `publisher` links join the Publisher row instead
LINK_PREFIX = "links."

DETAIL_FIELDS = (
    ("description", "Description"),
    ("license", "License"),
    ("copyright", "Copyright"),
    ("attribution", "Attribution"),
    ("publisher", "Publisher"),
    ("website", "Website"),
    ("links.homepage", "Homepage"),
    ("links.artist", "Artist"),
    ("links.buy", "Buy"),
    ("links.source", "Source"),
    ("created_date", "Created"),
    ("updated_date", "Updated"),
    ("published_date", "Published"),
    ("tags", "Tags"),
    ("id", "Identifier"),
    ("version", "Version"),
    ("schema_version", "Schema version"),
)

DATE_KEYS = ("created_date", "updated_date", "published_date")
DETAILS_GAP = 2 * units.LARGE_SPACING
EDGE_MARGIN = 2 * units.LARGE_SPACING


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


def detail_rows(fields):
    """Rows for the fields we have a label for, in DETAIL_FIELDS order.

    A `[deck]` key outside DETAIL_FIELDS is not presented. Labelling it with its
    raw TOML key read as a defect against 1.0 decks and does not survive 2.0,
    which adds `identifier`, `packager`, `pips`, `redistribution`, `derivation`
    and `license_files` to a table this widget renders in full.
    """
    rows = []
    for key, label in DETAIL_FIELDS:
        addresses = [display_address(url) for url in links_for(key, fields)]
        text = "\n".join(filter(None, [format_value(fields.get(key)), *addresses]))
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


def deck_links(fields):
    """`[deck].links` as (rel, url, title), in declared order."""
    raw = fields.get("links")
    if not isinstance(raw, list):
        return []

    links = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rel, url, title = entry.get("rel"), entry.get("url"), entry.get("title")
        if not isinstance(rel, str) or not isinstance(url, str) or not _is_link(url.strip()):
            continue
        title = title.strip() if isinstance(title, str) else ""
        links.append((rel, url.strip(), title or None))
    return links


def links_for(key, fields):
    """URLs the detail row `key` presents."""
    if key.startswith(LINK_PREFIX):
        rel = key.removeprefix(LINK_PREFIX)
    elif key == "publisher":
        rel = "publisher"
    else:
        return []
    return [url for link_rel, url, _ in deck_links(fields) if link_rel == rel]


def buy_link(fields):
    """The first `buy` link as (url, title), or None."""
    for rel, url, title in deck_links(fields):
        if rel == "buy":
            return url, title
    return None


def display_address(url):
    """`url` as shown to a reader: no scheme, no trailing slash."""
    return url.split("://", 1)[-1].rstrip("/")


def link_html(text, urls):
    """`text`, if any, then one link per URL, a line each."""
    lines = [html.escape(text)] if text else []
    lines += [
        f'<a href="{html.escape(url)}">{html.escape(display_address(url))}</a>' for url in urls
    ]
    return "<br>".join(lines)


class DeckHeader(QWidget):
    def __init__(self, deck, parent=None, cover_cache=None, settings=None):
        super().__init__(parent)
        self.deck = deck
        self._cover_cache = cover_cache or CoverCache(capacity=8)
        self._settings = settings if settings is not None else get_settings()
        self._banner = CoverBanner()

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

        self.buy_button = self._build_buy_button()
        if self.buy_button is not None:
            title_row.addWidget(self.buy_button, 0, Qt.AlignmentFlag.AlignTop)

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

    def _build_buy_button(self):
        """A button to the deck's first `buy` link, labelled with its title if it has one."""
        link = buy_link(self.deck.get_metadata_fields())
        if link is None:
            return None
        url, title = link
        button = QPushButton(QIcon.fromTheme(BUY_ICON), title or BUY_TEXT)
        button.setToolTip(url)
        button.clicked.connect(lambda _checked=False: QDesktopServices.openUrl(QUrl(url)))
        return button

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
            urls = links_for(key, fields)
            if urls:
                field.setTextFormat(Qt.TextFormat.RichText)
                field.setText(link_html(format_value(fields.get(key)), urls))
                field.setOpenExternalLinks(True)
                field.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            elif key == "website" and _is_link(value):
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

    def paintEvent(self, event):
        rect = self.banner_rect()
        if not rect.isEmpty():
            painter = QPainter(self)
            self._banner.paint(painter, rect, self._cover_path, self.devicePixelRatioF())
            painter.end()
        super().paintEvent(event)

    def _apply_banner_text(self, on_banner):
        """Light text while the two labels sit on the banner, palette colours otherwise."""
        set_banner_text(self.title_label, on_banner, BANNER_TEXT, QPalette.ColorRole.WindowText)
        set_banner_text(
            self.subtitle_label, on_banner, BANNER_SUBTEXT, QPalette.ColorRole.PlaceholderText
        )

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
