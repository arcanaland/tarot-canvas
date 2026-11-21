from PyQt6.QtCore import QPoint, QRect, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontMetrics, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
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
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.library.decks.deck_cover import DeckCover
from tarot_canvas.ui.library.decks.deck_metadata import (
    DETAIL_FIELDS,
    buy_link,
    detail_rows,
    field_value,
    format_value,
    links_for,
)
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.ui.widgets.cover_banner import (
    BANNER_PADDING,
    BANNER_SUBTEXT,
    BANNER_TEXT,
    CoverBanner,
    set_banner_text,
)
from tarot_canvas.ui.widgets.pane_text import is_link, link_html
from tarot_canvas.ui.widgets.tag_chips import TagChips, normalized_tags

MEASURE_CHARACTERS = 85

BUY_ICON = "wallet-open"

DETAILS_GAP = 2 * units.LARGE_SPACING
EDGE_MARGIN = 2 * units.LARGE_SPACING


def measure():
    """The width of a line of text, in pixels at the current font"""
    return MEASURE_CHARACTERS * max(1, QFontMetrics(QApplication.font()).averageCharWidth())


def wrapped_height(text, font, width):
    if not text or width <= 0:
        return 0
    metrics = QFontMetrics(font)
    bounds = metrics.boundingRect(QRect(0, 0, width, 1 << 20), int(Qt.TextFlag.TextWordWrap), text)
    return bounds.height()


class HeaderFrame(QWidget):
    """The cover and a text column beside it; the first section's heading rule closes it

    A subclass sets text_container's layout.
    """

    def __init__(self, deck, parent=None, cover_cache=None):
        super().__init__(parent)
        self.deck = deck
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        outer = QVBoxLayout(self)
        outer.setSpacing(units.LARGE_SPACING)

        self.row = QHBoxLayout()
        self.row.setSpacing(units.LARGE_SPACING)
        self.cover = DeckCover(cover_cache)
        self.cover.set_deck(deck)
        self.row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        self.text_container = QWidget()
        self.row.addWidget(self.text_container, 1)
        outer.addLayout(self.row)
        self.set_padding(units.LARGE_SPACING)

    def measure(self):
        return measure()

    def set_padding(self, padding):
        """Above and below; the sides are always EDGE_MARGIN"""
        self.layout().setContentsMargins(EDGE_MARGIN, padding, EDGE_MARGIN, padding)

    def align_text(self, top):
        """The text column level with the cover's top, or centred beside it"""
        self.row.setAlignment(
            self.text_container,
            Qt.AlignmentFlag.AlignTop if top else Qt.AlignmentFlag.AlignVCenter,
        )


class DetailsForm(QWidget):
    """An installed deck's metadata, a labelled row per field it has"""

    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        width = measure()
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(units.LARGE_SPACING)
        form.setVerticalSpacing(units.SMALL_SPACING)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        self.labels = {}
        for label, value, key in detail_rows(metadata):
            name = QLabel(f"{label}:")
            name.setForegroundRole(QPalette.ColorRole.PlaceholderText)
            field = (
                self._tag_chips(metadata.tags)
                if key == "tags"
                else self._field(metadata, key, value)
            )
            form.addRow(name, field)
            self.labels[key] = field
        self.setMaximumWidth(width + self.label_measure())

    @staticmethod
    def _field(metadata, key, value):
        width = measure()
        field = QLabel()
        field.setWordWrap(True)
        field.setFixedWidth(width)
        urls = links_for(key, metadata)
        if urls:
            field.setTextFormat(Qt.TextFormat.RichText)
            field.setText(link_html(format_value(field_value(metadata, key)), urls))
            field.setOpenExternalLinks(True)
            field.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        elif key == "website" and is_link(value):
            field.setText(f'<a href="{value}">{value}</a>')
            field.setOpenExternalLinks(True)
            field.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        else:
            field.setText(value)
            field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        field.setMinimumHeight(wrapped_height(value, field.font(), width))
        return field

    @staticmethod
    def _tag_chips(raw):
        width = measure()
        chips = TagChips(normalized_tags(raw), width)
        chips.setFixedWidth(width)
        chips.setMinimumHeight(chips.heightForWidth(width))
        return chips

    @staticmethod
    def label_measure():
        """Room for the label column, in pixels at the current font."""
        metrics = QFontMetrics(QApplication.font())
        widest = max(
            (metrics.horizontalAdvance(f"{label}:") for _, label in DETAIL_FIELDS),
            default=0,
        )
        return widest + 2 * units.LARGE_SPACING


class DeckHeader(HeaderFrame):
    """An installed deck's name and cover, and its metadata behind Details"""

    def __init__(self, deck, parent=None, cover_cache=None, settings=None):
        super().__init__(deck, parent, cover_cache)
        self._settings = settings if settings is not None else get_settings()
        self._banner = CoverBanner()
        self.text_container.setLayout(self._build_text_column())
        self._restore_expanded()

    # -- construction -----------------------------------------------------

    def _build_text_column(self):
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(units.LARGE_SPACING)

        self.title_label = QLabel(self.deck.metadata.name)
        typography.apply(self.title_label, typography.Role.HEADING_1, primary=True)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        title_row.addWidget(self.title_label)
        title_row.addStretch()

        self.buy_button = self._build_buy_button()
        if self.buy_button is not None:
            title_row.addWidget(self.buy_button, 0, Qt.AlignmentFlag.AlignTop)

        self.details_button = QToolButton()
        self.details_button.setText(DECK_VIEW["details"])
        self.details_button.setCheckable(True)
        self.details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_button.setToolTip(DECK_VIEW["details_tooltip"])
        self.details_button.toggled.connect(self._on_toggled)
        title_row.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(title_row)

        self.subtitle_label = QLabel(self.subtitle_text())
        typography.apply(self.subtitle_label, typography.Role.SMALL)
        self.subtitle_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.subtitle_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self.subtitle_label)

        self.details_widget = DetailsForm(self.deck.metadata)
        self.detail_labels = self.details_widget.labels
        column.addSpacing(BANNER_PADDING + DETAILS_GAP)
        column.addWidget(self.details_widget)
        return column

    def _build_buy_button(self):
        """A button to the deck's first `buy` link, labelled with its title if it has one."""
        link = buy_link(self.deck.metadata)
        if link is None:
            return None
        url, title = link
        button = QPushButton(QIcon.fromTheme(BUY_ICON), title or DECK_VIEW["buy"])
        button.setToolTip(url)
        button.clicked.connect(lambda _checked=False: QDesktopServices.openUrl(QUrl(url)))
        return button

    # -- content ----------------------------------------------------------

    def subtitle_text(self):
        parts = []
        author = self.deck.metadata.artist
        if author:
            parts.append(author)
        parts.append(DECK_VIEW["card_count"].format(count=len(self.deck.cards)))
        return " · ".join(parts)

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
        if not self.is_expanded() or not self.cover.path():
            return QRect()

        bottom = self.subtitle_label.mapTo(self, QPoint(0, self.subtitle_label.height())).y()

        return QRect(0, 0, self.width(), bottom + BANNER_PADDING)

    def paintEvent(self, event):
        rect = self.banner_rect()
        if not rect.isEmpty():
            painter = QPainter(self)
            self._banner.paint(painter, rect, self.cover.path(), self.devicePixelRatioF())
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
            DECK_VIEW["hide_metadata"] if expanded else DECK_VIEW["show_metadata"]
        )
        self.cover.set_expanded(expanded)
        self.align_text(top=expanded)
        banner = expanded and bool(self.cover.path())
        self._apply_banner_text(banner)
        self.set_padding(BANNER_PADDING if banner else units.LARGE_SPACING)
        self.update()
