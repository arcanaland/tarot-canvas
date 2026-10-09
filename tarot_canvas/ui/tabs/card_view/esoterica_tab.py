import html
from importlib.resources import files
from itertools import groupby
from math import ceil

from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QPainter, QPalette, QTextDocument
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import FALLBACK_URLS, load_about_data
from tarot_canvas.models.esoterica import get_esoterica_manager
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.esoterica_registry import FAMILIES, GROUPS, SYMBOLS, Role
from tarot_canvas.settings import (
    get_esoterica_expanded,
    get_esoterica_hidden,
    set_esoterica_expanded,
    set_esoterica_hidden,
)
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import muted_text, subtle_fill, with_text_colour
from tarot_canvas.ui.tabs.card_view.fold import Fold
from tarot_canvas.ui.tabs.card_view.ghost_passages import GhostPassages
from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, SUBTITLE_SCALE, apply_heading
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    BODY_LINE_HEIGHT,
    FOLD_INDENT,
    HEADER_TO_ROWS,
    HEADING_TO_BODY,
    LIST_ITEM_GAP,
    PADDING,
    PARAGRAPH_GAP,
    PASSAGE_SPACING,
    SIDE_MARGIN,
    TITLE_TO_AUTHOR,
    TOP_MARGIN,
    column_width,
)
from tarot_canvas.ui.widgets.contextual_help import ContextualHelpButton
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

HELP_BUTTON_TOOLTIP = "About Esoterica"
HELP_BUTTON_ACCESSIBLE_NAME = "About Esoterica"

HEADER_ICON = PLACEHOLDER_ICON
HEADER_ICON_SIZE = 22

ESOTERICA_FAQ_ANCHOR = "3-how-do-i-add-my-own-esoterica"

SHOW_MENU_ICON = "view-filter"

# The show menu's entries, in order
SHOWABLE = (*FAMILIES.values(), GROUPS)

# Pages of EsotericaTab.stack
PASSAGES_PAGE = 0  # sources loaded: this card's passages, or a line saying there are none
PLACEHOLDER_PAGE = 1  # no source loaded, or every one disabled


def esoterica_faq_url():
    """The FAQ's esoterica section, from the same metainfo as Help > FAQ"""
    faq = load_about_data().faq or FALLBACK_URLS["faq"]
    return f"{faq}#{ESOTERICA_FAQ_ANCHOR}"


def _with_faq_link(text):
    return text.replace("{faq}", esoterica_faq_url()) if "{faq}" in text else text


def _line_height():
    return f"line-height: {round(BODY_LINE_HEIGHT * 100)}%"


def _body_html(text):
    """A passage's text as rich text: paragraphs at blank lines, line breaks at newlines.

    Escaped first: this is a file the user dropped in a directory.
    """
    return "".join(
        f'<p style="margin: {PARAGRAPH_GAP if i else 0}px 0 0 0; {_line_height()}">'
        + paragraph.replace("\n", "<br>")
        + "</p>"
        for i, paragraph in enumerate(html.escape(text).split("\n\n"))
    )


def _show_menu_icon():
    return QIcon.fromTheme(SHOW_MENU_ICON)


def _without(ids, family):
    return [i for i in ids if i != family]


def _window_text(palette):
    return palette.color(QPalette.ColorRole.WindowText)


def _italic(label):
    font = label.font()
    font.setItalic(True)
    label.setFont(font)


def _spelled(value):
    """A value as TOML gave it"""
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
    """Paragraphs of the source's prose"""
    return _row_label(_body_html(_spelled(value)), Qt.TextFormat.RichText)


def printed_heading(text):
    """A heading the source prints, in its paragraph's face and size, bold"""
    label = _row_label(text, Qt.TextFormat.PlainText)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def line_row(value):
    """One line of values, verbatim, such as keywords"""
    return _row_label(_spelled(value), Qt.TextFormat.PlainText)


LEAD_ROLES = (Role.EPITHET, Role.KEYWORDS)


def lead_of(reading, roles=LEAD_ROLES):
    """What heads a source's frame, as (role, entries), or None.

    The first of `roles` the source has for the card: every epithet, or its first keywords.
    """
    for role in roles:
        entries = tuple(entry for entry in reading.entries if entry.role is role)
        if role is Role.KEYWORDS:
            entries = entries[:1]
        if entries:
            return role, entries
    return None


def lead_row(entries):
    """A lead's values on one line, bold, at SECTION_SCALE"""
    label = line_row(tuple(entry.value for entry in entries))
    label.setFont(units.scaled_font(label.font(), SECTION_SCALE, bold=True))
    return label


def list_row(value):
    """Each string a bullet, such as a source's questions"""
    items = value if isinstance(value, tuple) else (value,)
    bullets = "".join(
        f'<li style="margin-top: {LIST_ITEM_GAP if i else 0}px; {_line_height()}">'
        f"{html.escape(_spelled(item))}</li>"
        for i, item in enumerate(items)
    )
    return _row_label(f"<ul>{bullets}</ul>", Qt.TextFormat.RichText)


def affirmation_row(value):
    """Indented and italic"""
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


def _family_label_key(family):
    return f"family.{family}"


def _group_fold_id(group):
    """Every suit shares one fold, every rank another, and so on"""
    return f"group.{group.family}"


def _counted(text, count):
    # The label goes in last, so a brace in it is never read as a field
    return label_for("count").replace("{count}", str(count)).replace("{label}", text) or text


def _muted(palette, colour):
    palette = with_text_colour(palette, colour)
    palette.setColor(QPalette.ColorRole.ButtonText, colour)
    return palette


# Group families whose label is shared by every member
_SHARED_GROUP_LABELS = {"suits", "ranks", "all", "custom"}


def _group_label_key(group):
    if group.family in _SHARED_GROUP_LABELS:
        return f"group.{group.family}"
    return f"group.{group.group}"


def _pattern_name(identifier):
    return label_for(f"pattern.{identifier}") or identifier or ""


def reseated_note(reading, deck):
    """Where the source wrote this card's text, when it isn't the card's own ID; else None"""
    if not reading.written_at or deck is None:
        return None
    card = deck.get_card_by_id(reading.written_at)
    slots = {
        "card": (card or {}).get("name") or reading.written_at,
        "card_id": reading.written_at,
        "deck_pattern": _pattern_name(deck.get_pattern()),
        "source_pattern": _pattern_name(reading.pattern),
    }
    slots = {key: html.escape(str(value)) for key, value in slots.items()}
    slots["card_id"] = f"<code>{slots['card_id']}</code>"
    return label_for("reseated").format(**slots)


def draw_reseated_icon(icon_label, note, byline):
    """An information icon the height of the byline's line, tipped with the note; hidden without one"""
    icon_label.setToolTip(note or "")
    icon_label.setVisible(note is not None)
    if note is None:
        return
    icon = QIcon.fromTheme("dialog-information")
    if icon.isNull():
        icon = icon_label.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
    size = byline.fontMetrics().height()
    icon_label.setPixmap(icon.pixmap(QSize(size, size), icon_label.devicePixelRatioF()))


class Byline(QLabel):
    """A word-wrapped label that asks for its whole text on one line, so beside an icon it
    wraps only when the row is too narrow, not at QLabel's guess"""

    def sizeHint(self):
        hint = super().sizeHint()
        document = QTextDocument()
        document.setDefaultFont(self.font())
        document.setDocumentMargin(0)
        if self.textFormat() == Qt.TextFormat.PlainText:
            document.setPlainText(self.text())
        else:
            document.setHtml(self.text())
        margins = self.contentsMargins()
        width = ceil(document.idealWidth()) + margins.left() + margins.right()
        return QSize(max(width, hint.width()), hint.height())


def byline_row(byline, icon_label):
    """The byline with the icon just after it"""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(units.SMALL_SPACING)
    row.addWidget(byline)
    row.addWidget(icon_label)
    row.addStretch(1)
    return row


class PassageWidget(QFrame):
    """Everything one source says about one card, in one frame.

    Its labels are the edition's words, from `esoterica_text`; a row whose label is empty is
    not drawn at all. Nothing from two sources ever shares a frame. Each family and group is a
    fold, open if its id is in `expanded`; a family in `hidden` is not drawn.
    """

    # A fold's id, and whether it is now open
    fold_toggled = pyqtSignal(str, bool)

    def __init__(self, reading, card=None, parent=None, expanded=(), hidden=(), deck=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.card = card or {}
        self.expanded = set(expanded)
        self.hidden = set(hidden)

        # The edition's labels, which take the muted colour
        self.headings = []
        # Fold id -> the folds with that id, in order
        self.folds = {}
        # The source's principal text, where it has one
        self.body = None

        # The source line and the lead are one group, set apart from the rows (passage_metrics)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(TITLE_TO_AUTHOR)

        # Whose voice this is
        credit = (reading.name, reading.author) if reading.author else (reading.name,)
        self.source = Byline(label_for("joiner").join(credit))
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        self.source.setFont(units.scaled_font(self.source.font(), SUBTITLE_SCALE))
        # Beside it, an icon when the source wrote this card's text at another ID
        self.reseated = QLabel()
        self.reseated.setObjectName("reseated")
        draw_reseated_icon(self.reseated, reseated_note(reading, deck), self.source)
        layout.addLayout(byline_row(self.source, self.reseated))

        # The frame's heading: the author's own name for the card, or else the keywords
        own = list(reading.entries)
        self.lead = None
        if (lead := lead_of(reading)) is not None:
            role, entries = lead
            if role is Role.KEYWORDS:
                own.remove(entries[0])
            self.lead = lead_row(entries)
            layout.addWidget(self.lead)

        own = [entry for entry in own if entry.role is not Role.EPITHET]
        rows = self._rows(own)
        if (groups := self._groups(reading.groups)) is not None:
            rows.append(groups)
        for i, row in enumerate(rows):
            layout.addSpacing(PARAGRAPH_GAP if i else HEADER_TO_ROWS)
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

    def _symbol(self, entry):
        """A symbol's paragraph, under its printed heading if the source gives one"""
        if entry.slot != SYMBOLS:
            return self._row(entry)
        body = prose_row(entry.value)
        if entry.label is None:
            return body
        return _stack([printed_heading(entry.label), body], HEADING_TO_BODY)

    def _fold(self, fold_id, text, body, count):
        """A family's or group's rows under a header that opens and closes them"""
        fold = Fold(_counted(text, count), body, fold_id in self.expanded)
        apply_heading(fold.header, SUBTITLE_SCALE)
        fold.toggled.connect(lambda expanded: self.fold_toggled.emit(fold_id, expanded))
        self.folds.setdefault(fold_id, []).append(fold)
        return fold

    def _correspondences(self, entries):
        shown = [(label_for(entry.key), entry) for entry in entries if label_for(entry.key)]
        if not shown:
            return None
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for text, entry in shown:
            heading = QLabel(text)
            heading.setTextFormat(Qt.TextFormat.PlainText)
            self.headings.append(heading)
            form.addRow(heading, line_row(entry.value))

        return form_widget

    def _family(self, role, entries):
        """One fold over a run of rows, or None if the family, its label or every row is hidden"""
        family = FAMILIES[role]
        text = label_for(_family_label_key(family))
        if family in self.hidden or not text:
            return None
        if role is Role.CORRESPONDENCES:
            body = self._correspondences(entries)
            count = body.layout().rowCount() if body is not None else 0
        else:
            # A symbol's key is a build-time slug, never a heading
            make_row = self._symbol if role is Role.SYMBOLS else self._row
            rows = [row for entry in entries if (row := make_row(entry)) is not None]
            body = _stack(rows, PARAGRAPH_GAP) if rows else None
            count = len(rows)
        if body is None:
            return None
        return self._fold(family, text, body, count)

    def _rows(self, entries):
        """The widgets for entries in registry order; a hidden row is never built"""
        rows = []
        known = [entry for entry in entries if entry.role is not None]
        for role, run in groupby(known, key=lambda entry: entry.role):
            if role in FAMILIES:
                built = [self._family(role, list(run))]
            else:
                built = [self._row(entry) for entry in run]
            rows += [row for row in built if row is not None]
        return rows

    def _groups(self, groups):
        """Every group the card is in, as folds inside one fold, as the show menu offers them"""
        text = label_for(_family_label_key(GROUPS))
        if GROUPS in self.hidden or not text:
            return None
        blocks = [block for group in groups if (block := self._group(group)) is not None]
        if not blocks:
            return None
        body = _stack(blocks, PARAGRAPH_GAP)
        body.setContentsMargins(FOLD_INDENT, 0, 0, 0)
        return self._fold(GROUPS, text, body, len(blocks))

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
        return self._fold(_group_fold_id(group), text, _stack(rows, PARAGRAPH_GAP), len(rows))

    def _apply_colours(self):
        muted = muted_text(self.palette())
        headers = [fold.header for folds in self.folds.values() for fold in folds]
        for label in [self.source, *self.headings, *headers]:
            label.setPalette(_muted(label.palette(), muted))

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

    def __init__(self, card=None, deck=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck = deck
        self.parent_tab = parent

        # Currently displayed passages
        self.passage_widgets = []

        self.setup_ui()

        # Slots of this tab's, so Qt drops the connections when the tab is deleted
        esoterica_events().display_changed.connect(self._on_display_changed)
        esoterica_events().sources_changed.connect(self._on_sources_changed)

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
        self.scroll_area = scroll_area = QScrollArea()
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
        self.help_button = ContextualHelpButton(
            _with_faq_link(PLACEHOLDER_EXPLANATION),
            HELP_BUTTON_TOOLTIP,
            HELP_BUTTON_ACCESSIBLE_NAME,
        )
        header_layout.addWidget(self.help_button)
        header_layout.addWidget(self._show_menu_button())
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

    def _show_menu_button(self):
        """A menu that hides a family on every card, offering only the families sources have"""
        self.show_button = QToolButton()
        self.show_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.show_button.setAutoRaise(True)
        self.show_menu = QMenu(self.show_button)
        self.show_button.setMenu(self.show_menu)

        icon = _show_menu_icon()
        if not icon.isNull():
            self.show_button.setIcon(icon)
        else:
            self.show_button.setText(label_for("show_menu"))
        self.show_button.setToolTip(label_for("show_menu_tooltip"))

        self._fill_show_menu()
        return self.show_button

    def _fill_show_menu(self):
        """The show menu's entries, for the families the enabled sources have now"""
        self.show_menu.clear()
        # Family id -> its checkable entry
        self.show_actions = {}
        present = get_esoterica_manager().families_present()
        hidden = get_esoterica_hidden()
        for family in SHOWABLE:
            text = label_for(_family_label_key(family))
            if family not in present or not text:
                continue
            action = self.show_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(family not in hidden)
            action.toggled.connect(
                lambda shown, family=family: self._on_show_toggled(family, shown)
            )
            self.show_actions[family] = action

        self.show_button.setVisible(
            bool(self.show_actions)
            and (not self.show_button.icon().isNull() or bool(self.show_button.text()))
        )

    def _on_show_toggled(self, family, shown):
        hidden = _without(get_esoterica_hidden(), family)
        set_esoterica_hidden(hidden if shown else [*hidden, family])

    def _on_fold_toggled(self, fold_id, expanded):
        ids = _without(get_esoterica_expanded(), fold_id)
        set_esoterica_expanded([*ids, fold_id] if expanded else ids)

    @pyqtSlot()
    def _on_display_changed(self):
        """Another fold opened or a family was hidden, here or in another card's tab"""
        hidden = get_esoterica_hidden()
        for family, action in self.show_actions.items():
            action.blockSignals(True)
            action.setChecked(family not in hidden)
            action.blockSignals(False)

        self._redraw()

    @pyqtSlot()
    def _on_sources_changed(self):
        """A source was added, removed, enabled or disabled"""
        self._fill_show_menu()
        self._redraw()

    def _redraw(self):
        """This card again, where the reader left it"""
        bar = self.scroll_area.verticalScrollBar()
        position = bar.value()
        self.update_card_info(self.card)
        bar.setValue(position)

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
        )
        page_layout.addWidget(self.placeholder)
        page_layout.addWidget(GhostPassages(), 1)
        return page

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._apply_column_width()

    def update_card_info(self, card, deck=None):
        """Update displayed content based on the card, and the deck it is shown on if given"""
        if deck is not None:
            self.deck = deck

        has_sources = get_esoterica_manager().has_enabled_sources()
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

        readings = get_esoterica_manager().read_card(card_id, deck=self.deck)

        if not readings:
            logger.debug(f"No esoterica found for card: {card_id}")
            self.show_no_content()
            return

        logger.debug(f"Found {len(readings)} sources for card: {card_id}")

        # We have content, hide the no content label
        self.no_content.setVisible(False)

        # One frame per source
        expanded, hidden = get_esoterica_expanded(), get_esoterica_hidden()
        for reading in readings:
            passage_widget = PassageWidget(reading, card, self, expanded, hidden, self.deck)
            passage_widget.fold_toggled.connect(self._on_fold_toggled)
            self.content_layout.insertWidget(self.content_layout.count() - 1, passage_widget)
            # Now rather than when the layout gets to it, or the scroll range is briefly empty
            passage_widget.show()
            self.passage_widgets.append(passage_widget)

    def clear_passages(self):
        """Remove all passage widgets"""
        for widget in self.passage_widgets:
            self.content_layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self.passage_widgets = []

    def show_no_content(self):
        """Show the 'no content available' message"""
        self.no_content.setVisible(True)
