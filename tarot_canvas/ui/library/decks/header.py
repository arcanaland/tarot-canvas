import itertools

from PyQt6.QtCore import QPoint, QRect, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFontMetrics, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
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
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.covers.ghost import paint_placeholder_well
from tarot_canvas.ui.dates import format_date
from tarot_canvas.ui.icons import deck_icon
from tarot_canvas.ui.library.decks.model import created_progress, deck_cover_path, is_majors_only
from tarot_canvas.ui.strings import DECK_VIEW, license_name
from tarot_canvas.ui.widgets.cover_banner import (
    BANNER_PADDING,
    BANNER_SUBTEXT,
    BANNER_TEXT,
    CoverBanner,
    set_banner_text,
)
from tarot_canvas.ui.widgets.inline_editors import InlineLineEdit, InlineTextEdit
from tarot_canvas.ui.widgets.pane_text import display_address, is_link, link_html
from tarot_canvas.ui.widgets.tag_chips import TagChips, normalized_tags

MEASURE_CHARACTERS = 85

COLLAPSED_COVER_UNITS = 3

BUY_ICON = "wallet-open"

# a row per 2.0 link rel; `publisher` links join the Publisher row instead
LINK_PREFIX = "links."

DETAIL_FIELDS = (
    ("description", DECK_VIEW["field.description"]),
    ("license", DECK_VIEW["field.license"]),
    ("copyright", DECK_VIEW["field.copyright"]),
    ("attribution", DECK_VIEW["field.attribution"]),
    ("publisher", DECK_VIEW["field.publisher"]),
    ("website", DECK_VIEW["field.website"]),
    ("links.homepage", DECK_VIEW["field.links.homepage"]),
    ("links.artist", DECK_VIEW["field.links.artist"]),
    ("links.buy", DECK_VIEW["field.links.buy"]),
    ("links.source", DECK_VIEW["field.links.source"]),
    ("created_date", DECK_VIEW["field.created_date"]),
    ("updated_date", DECK_VIEW["field.updated_date"]),
    ("published_date", DECK_VIEW["field.published_date"]),
    ("tags", DECK_VIEW["field.tags"]),
    ("version", DECK_VIEW["field.version"]),
    ("schema_version", DECK_VIEW["field.schema_version"]),
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
        return None if value is None else (DECK_VIEW["yes"] if value else DECK_VIEW["no"])

    if isinstance(value, list | tuple):
        parts = [format_value(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None

    # skip sub-tables
    if isinstance(value, dict):
        return None

    text = str(value).strip()
    return text or None


def field_value(metadata, key):
    return None if key.startswith(LINK_PREFIX) else getattr(metadata, key)


def detail_rows(metadata):
    """Rows for the DeckMetadata fields we have a label for, in DETAIL_FIELDS order."""
    rows = []
    for key, label in DETAIL_FIELDS:
        addresses = [display_address(url) for url in links_for(key, metadata)]
        text = "\n".join(filter(None, [format_value(field_value(metadata, key)), *addresses]))
        if not text:
            continue
        if key in DATE_KEYS:
            text = format_date(text)
        elif key == "license":
            text = license_name(text)
        rows.append((label, text, key))
    return rows


def wrapped_height(text, font, width):
    if not text or width <= 0:
        return 0
    metrics = QFontMetrics(font)
    bounds = metrics.boundingRect(QRect(0, 0, width, 1 << 20), int(Qt.TextFlag.TextWordWrap), text)
    return bounds.height()


def links_for(key, metadata):
    """URLs the detail row `key` presents."""
    if key.startswith(LINK_PREFIX):
        rel = key.removeprefix(LINK_PREFIX)
    elif key == "publisher":
        rel = "publisher"
    else:
        return []
    return [link.url for link in metadata.links if link.rel == rel]


def buy_link(metadata):
    """The first `buy` link as (url, title), or None."""
    for link in metadata.links:
        if link.rel == "buy":
            return link.url, link.title
    return None


class _CoverWell(QLabel):
    """The cover, or with none an empty well"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.empty = True

    def paintEvent(self, event):
        if not self.empty:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_placeholder_well(painter, self.rect(), self.palette(), deck_icon())
        painter.end()


class DeckHeader(QWidget):
    """A deck's name, cover and metadata; a created deck's are edited where they stand"""

    fields_edited = pyqtSignal(dict)  # [deck] key: new text, "" to remove it
    add_images_requested = pyqtSignal()
    cards_chosen = pyqtSignal(bool)  # all 78, or majors only

    def __init__(self, deck, parent=None, cover_cache=None, settings=None, created=False):
        super().__init__(parent)
        self.deck = deck
        self.created = created
        self._cover_cache = cover_cache or CoverCache(capacity=8)
        self._settings = settings if settings is not None else get_settings()
        self._banner = CoverBanner()

        self._build()
        if created:
            self._apply_expanded(True)
            self.update_from(deck)
        else:
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
        self.text_container.setLayout(
            self._build_created_column() if self.created else self._build_text_column()
        )
        if self.created:
            # Down the column, then the action row
            order = [
                self.name_edit,
                self.artist_edit,
                self.description_edit,
                self.majors_radio,
                self.all_radio,
                self.add_images_button,
            ]
            for first, second in itertools.pairwise(order):
                QWidget.setTabOrder(first, second)
        self.row.addWidget(self.text_container, 1)
        outer.addLayout(self.row)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        outer.addWidget(separator)

    def _build_cover(self):
        self.cover_label = _CoverWell()
        self.cover_label.setAccessibleName(
            DECK_VIEW["cover_of"].format(name=self.deck.metadata.name)
        )
        self._cover_path = deck_cover_path(self.deck)
        self._apply_cover(expanded=False)
        return self.cover_label

    def _apply_cover(self, expanded):
        width, height = cover_size(expanded)
        self.cover_label.setFixedSize(width, height)

        pixmap = self._cover_cache.get(
            self._cover_path, self.cover_label.size(), self.devicePixelRatioF()
        )
        self.cover_label.empty = pixmap is None
        if pixmap is not None:
            self.cover_label.setPixmap(pixmap)
            self.cover_label.setAlignment(
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
            )
            self.cover_label.setAccessibleDescription("")
        else:
            self.cover_label.clear()
            self.cover_label.setAccessibleDescription(DECK_VIEW["no_cover"])
        self.cover_label.update()

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

        self.details_widget = self._build_details()
        column.addSpacing(BANNER_PADDING + DETAILS_GAP)
        column.addWidget(self.details_widget)
        return column

    def _build_created_column(self):
        """Name, artist, description, the Cards choice and the count; the actions top right"""
        self.details_button = None
        self.details_widget = None
        self.detail_labels = {}
        self.buy_button = None
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(units.SMALL_SPACING)

        title_row = QHBoxLayout()
        title_row.setSpacing(units.LARGE_SPACING)
        self.name_edit = InlineLineEdit()
        typography.apply(self.name_edit, typography.Role.HEADING_1, primary=True)
        self.name_edit.setAccessibleName(DECK_VIEW["field.name"])
        self.name_edit.setMaximumWidth(self.measure())
        self.name_edit.committed.connect(self._on_name_committed)
        self.title_label = self.name_edit
        title_row.addWidget(self.name_edit, 1, Qt.AlignmentFlag.AlignTop)
        title_row.addStretch()

        # Export… joins it here
        self.actions = QHBoxLayout()
        self.actions.setSpacing(units.SMALL_SPACING)
        self.add_images_button = QPushButton(QIcon.fromTheme("list-add"), DECK_VIEW["add_images"])
        self.add_images_button.clicked.connect(self.add_images_requested)
        self.actions.addWidget(self.add_images_button, 0, Qt.AlignmentFlag.AlignTop)
        title_row.addLayout(self.actions)
        title_row.setAlignment(self.actions, Qt.AlignmentFlag.AlignTop)
        column.addLayout(title_row)

        self.artist_edit = InlineLineEdit()
        typography.apply(self.artist_edit, typography.Role.SMALL)
        self.artist_edit.setPlaceholderText(DECK_VIEW["artist_placeholder"])
        self.artist_edit.setAccessibleName(DECK_VIEW["field.artist"])
        self.artist_edit.setMaximumWidth(self.measure())
        self.artist_edit.committed.connect(lambda text: self._commit_field("artist", text))
        column.addWidget(self.artist_edit)

        self.description_edit = InlineTextEdit()
        self.description_edit.setPlaceholderText(DECK_VIEW["description_placeholder"])
        self.description_edit.setAccessibleName(DECK_VIEW["field.description"])
        self.description_edit.setMaximumWidth(self.measure())
        self.description_edit.committed.connect(
            lambda text: self._commit_field("description", text)
        )
        column.addWidget(self.description_edit)

        column.addSpacing(units.SMALL_SPACING)
        column.addLayout(self._build_cards_choice())

        count_row = QHBoxLayout()
        count_row.setSpacing(units.LARGE_SPACING)
        self.subtitle_label = QLabel()
        typography.apply(self.subtitle_label, typography.Role.SMALL)
        self.subtitle_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        count_row.addWidget(self.subtitle_label)
        self.count_bar = QProgressBar()
        self.count_bar.setTextVisible(False)
        self.count_bar.setMaximumHeight(units.SMALL_SPACING * 2)
        self.count_bar.setMaximumWidth(self.measure() // 3)
        count_row.addWidget(self.count_bar, 1)
        count_row.addStretch(2)
        column.addLayout(count_row)
        column.addStretch()
        return column

    def _build_cards_choice(self):
        row = QHBoxLayout()
        row.setSpacing(units.LARGE_SPACING)
        label = QLabel(DECK_VIEW["cards_label"])
        row.addWidget(label)
        self.majors_radio = QRadioButton(DECK_VIEW["cards_majors_only"])
        self.all_radio = QRadioButton(DECK_VIEW["cards_all"])
        self.cards_group = QButtonGroup(self)
        self.cards_group.setExclusive(True)
        for button in (self.majors_radio, self.all_radio):
            self.cards_group.addButton(button)
            row.addWidget(button)
        label.setBuddy(self.majors_radio)
        self.cards_group.buttonClicked.connect(self._on_cards_clicked)
        row.addStretch()
        return row

    def _on_cards_clicked(self, button):
        whole = button is self.all_radio
        if whole != (not is_majors_only(self.deck)):
            # Until the reload, so a second click can't queue a second write
            self.majors_radio.setEnabled(False)
            self.all_radio.setEnabled(False)
            self.cards_chosen.emit(whole)

    def _on_name_committed(self, text):
        name = text.strip()
        if not name:
            self.name_edit.revert()
            return
        self.name_edit.setText(name)
        self._commit_field("name", name)

    def _commit_field(self, key, text):
        text = text.strip()
        editor = {
            "name": self.name_edit,
            "artist": self.artist_edit,
            "description": self.description_edit,
        }[key]
        if text == editor.saved():
            return
        editor.set_saved(text)
        self.fields_edited.emit({key: text})

    def update_from(self, deck):
        """Show deck, reloaded, without disturbing an editor being typed in"""
        self.deck = deck
        metadata = deck.metadata
        self.name_edit.set_saved(metadata.name or "")
        self.artist_edit.set_saved(metadata.artist or "")
        self.description_edit.set_saved(metadata.description or "")
        self.subtitle_label.setText(self.subtitle_text())
        placed, expected = created_progress(deck)
        self.count_bar.setRange(0, max(1, expected))
        self.count_bar.setValue(placed)
        majors_only = is_majors_only(deck)
        self.majors_radio.setChecked(majors_only)
        self.all_radio.setChecked(not majors_only)
        self.majors_radio.setEnabled(True)
        self.all_radio.setEnabled(True)
        self.cover_label.setAccessibleName(DECK_VIEW["cover_of"].format(name=metadata.name))
        self._cover_path = deck_cover_path(deck)
        self._apply_cover(expanded=True)

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

    def _build_details(self):
        details = QWidget()
        form = QFormLayout(details)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(units.LARGE_SPACING)
        form.setVerticalSpacing(units.SMALL_SPACING)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        self.detail_labels = {}
        metadata = self.deck.metadata
        for label, value, key in detail_rows(metadata):
            name = QLabel(f"{label}:")
            name.setForegroundRole(QPalette.ColorRole.PlaceholderText)

            if key == "tags":
                form.addRow(name, self._build_tag_chips(metadata.tags))
                continue

            field = QLabel()
            field.setWordWrap(True)
            field.setFixedWidth(self.measure())
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
        """The artist and the card count; for a created deck, the count alone"""
        if self.created:
            placed, expected = created_progress(self.deck)
            return DECK_VIEW["created_count"].format(placed=placed, expected=expected)
        parts = []
        author = self.deck.metadata.artist
        if author:
            parts.append(author)
        parts.append(DECK_VIEW["card_count"].format(count=len(self.deck.cards)))
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
        return self.created or self.details_button.isChecked()

    def set_expanded(self, expanded):
        if not self.created:
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
        # A created deck's editors want the palette's colours
        if self.created or not self.is_expanded() or not self._cover_path:
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
        if self.details_button is not None:
            self.details_widget.setVisible(expanded and bool(self.detail_labels))
            self.details_button.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            )
            self.details_button.setAccessibleDescription(
                DECK_VIEW["hide_metadata"] if expanded else DECK_VIEW["show_metadata"]
            )
        self._apply_cover(expanded)
        self.row.setAlignment(
            self.text_container,
            Qt.AlignmentFlag.AlignTop if expanded else Qt.AlignmentFlag.AlignVCenter,
        )
        banner = not self.created and expanded and bool(self._cover_path)
        if not self.created:
            self._apply_banner_text(banner)
        padding = BANNER_PADDING if banner else units.LARGE_SPACING
        self.layout().setContentsMargins(EDGE_MARGIN, padding, EDGE_MARGIN, padding)
        self.update()
