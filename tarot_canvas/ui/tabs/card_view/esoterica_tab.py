import html

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import FALLBACK_URLS, load_about_data
from tarot_canvas.models.esoterica import get_esoterica_manager
from tarot_canvas.ui.palette import muted_text, subtle_fill, with_text_colour
from tarot_canvas.ui.tabs.card_view.ghost_passages import GhostPassages
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    BODY_LINE_HEIGHT,
    HEADING_TO_BODY,
    PADDING,
    PARAGRAPH_GAP,
    PASSAGE_SPACING,
    SIDE_MARGIN,
    TITLE_PIXEL_SIZE,
    TITLE_TO_AUTHOR,
    TOP_MARGIN,
    column_width,
)
from tarot_canvas.ui.widgets.placeholder_message import (
    ICON_SIZE,
    PlaceholderMessage,
    TintedIcon,
)
from tarot_canvas.utils.logger import logger

PLACEHOLDER_ICON = "story-editor"

PLACEHOLDER_HEADING = "Esoterica"
PLACEHOLDER_EXPLANATION = 'Per-card meanings, associations and symbolism will show up here. See the <a href="{faq}">Frequently Asked Questions</a> for instructions for editing them.'
PLACEHOLDER_FOOTNOTE = "A complete corpus containing astrological, alchemical and esoteric data is still under development and will be included here out of the box eventually."

HEADER_ICON = PLACEHOLDER_ICON
HEADER_ICON_SIZE = 22

ESOTERICA_FAQ_ANCHOR = "3-how-do-i-add-my-own-esoterica"

# Pages of EsotericaTab.stack
PASSAGES_PAGE = 0  # sources loaded: this card's passages, or a line saying there are none
PLACEHOLDER_PAGE = 1  # no sources loaded at all


def esoterica_faq_url():
    """The FAQ's esoterica section, from the same metainfo as Help > FAQ"""
    faq = load_about_data().faq or FALLBACK_URLS["faq"]
    return f"{faq}#{ESOTERICA_FAQ_ANCHOR}"


def _with_faq_link(text):
    return text.replace("{faq}", esoterica_faq_url()) if "{faq}" in text else text


def _body_html(text):
    """A passage's text as rich text: paragraphs at blank lines, line breaks at newlines.

    Escaped first: this is a file the user dropped in a directory.
    """
    line_height = round(BODY_LINE_HEIGHT * 100)
    return "".join(
        f'<p style="margin: {PARAGRAPH_GAP if i else 0}px 0 0 0; line-height: {line_height}%">'
        + paragraph.replace("\n", "<br>")
        + "</p>"
        for i, paragraph in enumerate(html.escape(text).split("\n\n"))
    )


def _window_text(palette):
    return palette.color(QPalette.ColorRole.WindowText)


def _italic(label):
    font = label.font()
    font.setItalic(True)
    label.setFont(font)


class PassageWidget(QFrame):
    """Widget to display a single book/source passage"""

    def __init__(self, passage, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        # Title and author are one group, set apart from the body (passage_metrics)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(TITLE_TO_AUTHOR)

        # Header (book/source title)
        self.title = QLabel(passage.source_name)
        self.title.setStyleSheet(f"font-size: {TITLE_PIXEL_SIZE}px; font-weight: bold;")
        layout.addWidget(self.title)

        # Author, only where the source declares one
        self.author = None
        if passage.author:
            self.author = QLabel(f"by {passage.author}")
            _italic(self.author)
            layout.addWidget(self.author)

        layout.addSpacing(HEADING_TO_BODY)

        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setText(_body_html(passage.text))
        layout.addWidget(self.body)

        self._apply_colours()

    def _apply_colours(self):
        if self.author is not None:
            self.author.setPalette(
                with_text_colour(self.author.palette(), muted_text(self.palette()))
            )

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_colours()

    def paintEvent(self, event):
        # The same fill as a ghost passage; the frame goes on top
        painter = QPainter(self)
        painter.fillRect(self.rect(), subtle_fill(self.palette()))
        painter.end()
        super().paintEvent(event)


class EsotericaTab(QWidget):
    """Tab displaying esoteric information about a tarot card"""

    def __init__(self, card=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.parent_tab = parent

        # Currently displayed passages
        self.passage_widgets = []

        self.setup_ui()

    def setup_ui(self):
        """Set up the esoterica tab UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._passages_page())
        self.stack.addWidget(self._placeholder_page())
        main_layout.addWidget(self.stack)

        self._apply_colours()

        # Update content for the current card
        self.update_card_info(self.card)

    def _passages_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        # One reading column, about 85 characters wide and centred when the view is wider
        # (passage_metrics). The header is inside it, so it lines up with the passages.
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(SIDE_MARGIN, TOP_MARGIN, SIDE_MARGIN, 10)
        self.content_layout.setSpacing(PASSAGE_SPACING)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 5, 0, 0)

        self.header_icon = None
        if HEADER_ICON and QIcon.hasThemeIcon(HEADER_ICON):
            self.header_icon = TintedIcon(
                QIcon.fromTheme(HEADER_ICON), HEADER_ICON_SIZE, colour=_window_text
            )
            header_layout.addWidget(self.header_icon)

        self.header_label = QLabel(PLACEHOLDER_HEADING)
        self.header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        self.content_layout.addLayout(header_layout)

        # No content label (shown when no passages are available)
        self.no_content_label = QLabel("No esoteric content available for this card.")
        self.no_content_label.setStyleSheet("padding: 20px;")
        _italic(self.no_content_label)
        self.no_content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.no_content_label)

        # Add stretch to push content to the top
        self.content_layout.addStretch()

        scroll_area.setWidget(self.content_widget)
        page_layout.addWidget(scroll_area)
        self._apply_column_width()
        return page

    def _apply_column_width(self):
        self.content_widget.setMaximumWidth(column_width(self.content_widget.font()))

    def _placeholder_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, ICON_SIZE, 0, 0)

        # Above the ghosts, never over them
        self.placeholder = PlaceholderMessage(
            PLACEHOLDER_ICON,
            PLACEHOLDER_HEADING,
            _with_faq_link(PLACEHOLDER_EXPLANATION),
            _with_faq_link(PLACEHOLDER_FOOTNOTE),
        )
        page_layout.addWidget(self.placeholder)
        page_layout.addWidget(GhostPassages(), 1)
        return page

    def _apply_colours(self):
        self.no_content_label.setPalette(
            with_text_colour(self.no_content_label.palette(), muted_text(self.palette()))
        )

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_colours()
        elif event.type() == QEvent.Type.FontChange:
            self._apply_column_width()

    def update_card_info(self, card):
        """Update displayed content based on the card"""
        # Loaded once per process, so this can't change while the app runs
        has_sources = get_esoterica_manager().has_sources()
        self.stack.setCurrentIndex(PASSAGES_PAGE if has_sources else PLACEHOLDER_PAGE)

        self.card = card

        # Clear any existing passage widgets
        self.clear_passages()

        if not has_sources:
            return

        if not card:
            logger.debug("No card provided to EsotericaTab.update_card_info")
            self.show_no_content()
            return

        # Get the card ID
        card_id = card.get("id", "")
        if not card_id:
            logger.debug("Card has no ID")
            self.show_no_content()
            return

        logger.debug(f"Looking for passages for card: {card_id}")

        # Get all passages for this card
        passages = get_esoterica_manager().get_passages_for_card(card_id)

        if not passages:
            logger.debug(f"No passages found for card: {card_id}")
            self.show_no_content()
            return

        logger.debug(f"Found {len(passages)} passages for card: {card_id}")

        # We have content, hide the no content label
        self.no_content_label.setVisible(False)

        # Add a widget for each passage
        for passage in passages:
            passage_widget = PassageWidget(passage, self)
            self.content_layout.insertWidget(self.content_layout.count() - 1, passage_widget)
            self.passage_widgets.append(passage_widget)

    def clear_passages(self):
        """Remove all passage widgets"""
        for widget in self.passage_widgets:
            self.content_layout.removeWidget(widget)
            widget.deleteLater()
        self.passage_widgets = []

    def show_no_content(self):
        """Show the 'no content available' message"""
        self.no_content_label.setVisible(True)
