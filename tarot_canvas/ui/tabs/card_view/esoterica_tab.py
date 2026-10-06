import html
from importlib.resources import files
from itertools import groupby

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QFormLayout,
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
from tarot_canvas.models.esoterica_registry import Role
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import muted_text, subtle_fill, with_text_colour
from tarot_canvas.ui.tabs.card_view.ghost_passages import GhostPassages
from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, SUBTITLE_SCALE, apply_heading
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    BODY_LINE_HEIGHT,
    HEADING_TO_BODY,
    PADDING,
    PARAGRAPH_GAP,
    PASSAGE_SPACING,
    SIDE_MARGIN,
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

PLACEHOLDER_ICON = files("tarot_canvas.resources.icons").joinpath("esoterica.svg")

PLACEHOLDER_HEADING = "Esoterica"
PLACEHOLDER_EXPLANATION = 'Per-card meanings, associations and symbolism will show up here. See the <a href="{faq}">Frequently Asked Questions</a> for how to add your own.'
NO_CONTENT_TEXT = "No esoteric content available for this card."

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


def _spelled(value):
    """A value as TOML gave it: never title-cased, booleans spelled as TOML spells them"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return label_for("joiner").join(_spelled(item) for item in value)
    return str(value)


def _row_label(text, text_format):
    label = QLabel()
    label.setWordWrap(True)
    label.setTextFormat(text_format)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setText(text)
    return label


def prose_row(value):
    """Paragraphs of the source's prose; an array is joined into one paragraph"""
    return _row_label(_body_html(_spelled(value)), Qt.TextFormat.RichText)


def line_row(value):
    """One line of values, verbatim, such as keywords"""
    return _row_label(_spelled(value), Qt.TextFormat.PlainText)


def list_row(value):
    """Each string a bullet, such as a source's questions"""
    items = value if isinstance(value, tuple) else (value,)
    bullets = "".join(f"<li>{html.escape(_spelled(item))}</li>" for item in items)
    return _row_label(f"<ul>{bullets}</ul>", Qt.TextFormat.RichText)


def affirmation_row(value):
    """Indented and italic: the reader's own first-person line, not the author's claim"""
    label = prose_row(value)
    label.setContentsMargins(PADDING, 0, 0, 0)
    _italic(label)
    return label


def _stack(widgets, spacing):
    """Widgets one above another with `spacing` between, and no margins of their own"""
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return box


# Rows of these roles sit together under one label
_FAMILIES = {
    Role.ADVICE: "family.advice",
    Role.SYMBOLS: "family.symbols",
    Role.DIVINATORY: "family.divinatory",
    Role.CORRESPONDENCES: "family.correspondences",
}

# Group families whose label is shared by every member
_SHARED_GROUP_LABELS = {"suits", "ranks", "all", "custom"}


def _group_label_key(group):
    if group.family in _SHARED_GROUP_LABELS:
        return f"group.{group.family}"
    return f"group.{group.group}"


class PassageWidget(QFrame):
    """Everything one source says about one card, in one frame.

    Its labels are the edition's words, from `esoterica_text`; a row whose label is empty is
    not drawn at all. Nothing from two sources ever shares a frame.
    """

    def __init__(self, reading, card=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.card = card or {}

        # The edition's labels, which take the muted colour
        self.headings = []
        # The source's principal text, where it has one
        self.body = None

        # The source line and the lead are one group, set apart from the rows (passage_metrics)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(TITLE_TO_AUTHOR)

        # Whose voice this is, first but quiet: the reader came for what it says
        credit = (reading.name, reading.author) if reading.author else (reading.name,)
        self.source = QLabel(label_for("joiner").join(credit))
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        self.source.setFont(units.scaled_font(self.source.font(), SUBTITLE_SCALE))
        layout.addWidget(self.source)

        # The frame's one heading: the author's own name for the card, or else the keywords
        own = list(reading.entries)
        lead = tuple(entry.value for entry in own if entry.role is Role.EPITHET)
        if not lead:
            keywords = next((entry for entry in own if entry.role is Role.KEYWORDS), None)
            if keywords is not None:
                own.remove(keywords)
                lead = (keywords.value,)
        self.lead = None
        if lead:
            self.lead = line_row(lead)
            self.lead.setFont(units.scaled_font(self.lead.font(), SECTION_SCALE, bold=True))
            layout.addWidget(self.lead)

        own = [entry for entry in own if entry.role is not Role.EPITHET]
        rows = self._rows(own) + [
            block for group in reading.groups if (block := self._group(group)) is not None
        ]
        for i, row in enumerate(rows):
            layout.addSpacing(PARAGRAPH_GAP if i else HEADING_TO_BODY)
            layout.addWidget(row)

        self._apply_colours()

    def _heading(self, text):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        apply_heading(label, SUBTITLE_SCALE)
        self.headings.append(label)
        return label

    def _labelled(self, key, make_body):
        """A label above its value, or None while the label is empty"""
        text = label_for(key)
        if not text:
            return None
        return _stack([self._heading(text), make_body()], HEADING_TO_BODY)

    def _row(self, entry):
        value = entry.value
        if entry.role is Role.KEYWORDS:
            return line_row(value)
        if entry.role is Role.EPITHET:
            label = line_row(value)
            _italic(label)
            return label
        if entry.key == "text":
            label = prose_row(value)
            if self.body is None:
                self.body = label
            return label
        if entry.key == "questions":
            return self._labelled(entry.key, lambda: list_row(value))
        if entry.key == "affirmation":
            return self._labelled(entry.key, lambda: affirmation_row(value))
        return self._labelled(entry.key, lambda: prose_row(value))

    def _correspondences(self, entries):
        shown = [(label_for(entry.key), entry) for entry in entries if label_for(entry.key)]
        if not shown:
            return None
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        for text, entry in shown:
            heading = QLabel(text)
            heading.setTextFormat(Qt.TextFormat.PlainText)
            self.headings.append(heading)
            form.addRow(heading, line_row(entry.value))
        return form_widget

    def _family(self, role, entries):
        """One label over a run of rows, or None if the label or every row is hidden"""
        text = label_for(_FAMILIES[role])
        if not text:
            return None
        if role is Role.CORRESPONDENCES:
            body = self._correspondences(entries)
        else:
            if role is Role.SYMBOLS:
                # A symbol's key is a build-time slug, never a heading
                rows = [prose_row(entry.value) for entry in entries]
            else:
                rows = [row for entry in entries if (row := self._row(entry)) is not None]
            body = _stack(rows, PARAGRAPH_GAP) if rows else None
        if body is None:
            return None
        return _stack([self._heading(text), body], HEADING_TO_BODY)

    def _rows(self, entries):
        """The widgets for entries in registry order; a hidden row is never built"""
        rows = []
        known = [entry for entry in entries if entry.role is not None]
        for role, run in groupby(known, key=lambda entry: entry.role):
            if role in _FAMILIES:
                built = [self._family(role, list(run))]
            else:
                built = [self._row(entry) for entry in run]
            rows += [row for row in built if row is not None]
        return rows

    def _group(self, group):
        """What the source says of a group the card is in, under the group's label"""
        text = label_for(_group_label_key(group))
        if not text:
            return None
        member = group.group.split(".", 1)[-1]
        if group.family == "suits":
            text = text.replace("{suit}", self.card.get("display_suit") or member)
        elif group.family == "custom":
            text = text.replace("{name}", member)
        # A group's own text is not the card's
        own_body = self.body
        rows = self._rows(group.entries)
        self.body = own_body
        if not rows:
            return None
        return _stack([self._heading(text), _stack(rows, PARAGRAPH_GAP)], HEADING_TO_BODY)

    def _apply_colours(self):
        muted = muted_text(self.palette())
        for label in [self.source, *self.headings]:
            label.setPalette(with_text_colour(label.palette(), muted))

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
        if HEADER_ICON:
            self.header_icon = TintedIcon(
                QIcon(str(HEADER_ICON)), HEADER_ICON_SIZE, colour=_window_text
            )
            header_layout.addWidget(self.header_icon)

        self.header_label = apply_heading(QLabel(PLACEHOLDER_HEADING), SECTION_SCALE)
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        self.content_layout.addLayout(header_layout)

        # Sources are loaded, but none has anything for this card
        self.no_content = PlaceholderMessage(QIcon(str(PLACEHOLDER_ICON)), NO_CONTENT_TEXT)
        self.no_content.setContentsMargins(0, ICON_SIZE // 2, 0, 0)
        self.content_layout.addWidget(self.no_content)

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
            QIcon(str(PLACEHOLDER_ICON)),
            PLACEHOLDER_HEADING,
            _with_faq_link(PLACEHOLDER_EXPLANATION),
            _with_faq_link(PLACEHOLDER_FOOTNOTE),
        )
        page_layout.addWidget(self.placeholder)
        page_layout.addWidget(GhostPassages(), 1)
        return page

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
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

        logger.debug(f"Reading esoterica for card: {card_id}")

        readings = get_esoterica_manager().read_card(card_id)

        if not readings:
            logger.debug(f"No esoterica found for card: {card_id}")
            self.show_no_content()
            return

        logger.debug(f"Found {len(readings)} sources for card: {card_id}")

        # We have content, hide the no content label
        self.no_content.setVisible(False)

        # One frame per source
        for reading in readings:
            passage_widget = PassageWidget(reading, card, self)
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
        self.no_content.setVisible(True)
