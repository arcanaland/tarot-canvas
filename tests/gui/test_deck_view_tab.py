"""The deck view page: a header, then every card in one grid that scrolls one way"""

import json

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPalette, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QScrollBar,
    QStyle,
    QStyleOptionViewItem,
    QWidget,
)
from pytestqt.qtbot import QtBot

from tarot_canvas.settings import (
    DECK_VIEW_DENSITY_DEFAULT,
    DECK_VIEW_DENSITY_KEY,
    LIBRARY_DENSITY_KEY,
    get_settings,
)
from tarot_canvas.ui import typography
from tarot_canvas.ui.card_transfer import CARD_MIME, card_from_mime
from tarot_canvas.ui.deck_view import card_delegate
from tarot_canvas.ui.deck_view.card_model import (
    KIND_CARD,
    KIND_HEADING,
    KIND_NOTE,
    CardRole,
    KindRole,
)
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs import deck_view_tab as module
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.widgets.deck_header import DeckHeader
from tests.conftest import MINIMAL_DECK_PATH


def shown(qtbot, deck_path, width=900, height=600):
    widget = DeckViewTab(str(deck_path))
    qtbot.addWidget(widget)
    widget.resize(width, height)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.fixture
def tab(qtbot):
    return shown(qtbot, MINIMAL_DECK_PATH)


@pytest.fixture
def full_tab(qtbot, full_deck):
    return shown(qtbot, full_deck.deck_path, width=1300, height=800)


def indexes(tab, kind):
    model = tab.grid.model()
    return [
        model.index(row, 0)
        for row in range(model.rowCount())
        if model.index(row, 0).data(KindRole) == kind
    ]


def press(tab, key, modifier=Qt.KeyboardModifier.NoModifier):
    QtBot.keyClick(tab.grid, key, modifier)


class RecordingPainter:
    """Just enough of a QPainter to see what the delegate set before drawing text"""

    def __init__(self):
        self.pens, self.fonts, self.fills = [], [], []

    def save(self):
        pass

    def restore(self):
        pass

    def setPen(self, pen):
        self.pens.append(pen)

    def setFont(self, font):
        self.fonts.append(font)

    def drawText(self, *args):
        pass

    def fillRect(self, rect, colour):
        self.fills.append((rect, colour))


# -- the page ---------------------------------------------------------------------


def test_the_deck_view_has_a_deck_level_header(tab):
    headers = tab.findChildren(DeckHeader)
    assert len(headers) == 1
    assert headers[0].title_label.text() == "Minimal Test Deck"


def test_nothing_in_the_deck_view_opens_a_dialog(tab):
    """Four lines of read-only text is not a reason to go modal."""
    assert not hasattr(tab, "show_deck_info")
    assert not hasattr(module, "DeckInfoDialog")
    assert tab.findChildren(QDialog) == []


def test_the_header_reaches_the_edges_of_the_view(tab):
    """The banner is a page header; an inset would make it read as a floating bar."""
    header = tab.findChildren(DeckHeader)[0]
    bar = tab.search_field.parentWidget()
    assert header.mapTo(tab, QPoint(0, 0)).x() == 0
    assert header.mapTo(tab, QPoint(0, 0)).y() == bar.geometry().bottom() + 1


def test_the_sections_take_back_the_margin_the_header_gave_up(tab):
    """With the tab flush, section headings would otherwise sit against the window edge."""
    (heading,) = indexes(tab, KIND_HEADING)
    assert heading.data() == "Major Arcana"
    left = tab.grid.viewport().mapTo(tab, tab.grid.visualRect(heading).topLeft()).x()
    assert left == module.SECTION_MARGIN


def test_section_headings_use_the_system_font(tab):
    font = tab.delegate.heading_font()
    assert font.family() == QApplication.font().family()
    assert font == typography.font(typography.Role.HEADING_2)
    assert font.pointSizeF() > QApplication.font().pointSizeF()


def test_nothing_in_the_deck_view_hardcodes_a_colour(full_tab):
    for widget in [full_tab, *full_tab.findChildren(QWidget)]:
        assert "rgba(255, 255, 255" not in widget.styleSheet()


def test_the_exclusion_note_is_palette_derived(tab):
    """The minimal fixture excludes 76 cards, so it shows the note."""
    (note,) = indexes(tab, KIND_NOTE)
    assert note.data().startswith("Note: Test fixture only needs")

    option = QStyleOptionViewItem()
    option.rect = tab.grid.visualRect(note)
    option.palette = tab.grid.palette()
    option.font = tab.grid.font()
    painter = RecordingPainter()
    tab.delegate.paint(painter, option, note)

    assert painter.pens == [option.palette.placeholderText().color()]
    assert [font.italic() for font in painter.fonts] == [True]


def test_headings_and_notes_are_not_painted_disabled(tab):
    """They have no flags, so the view hands the delegate its Disabled colours."""
    palette = QPalette(tab.grid.palette())
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("red"))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, QColor("red")
    )
    palette.setCurrentColorGroup(QPalette.ColorGroup.Disabled)
    for index in indexes(tab, KIND_HEADING) + indexes(tab, KIND_NOTE):
        option = QStyleOptionViewItem()
        option.rect = tab.grid.visualRect(index)
        option.palette = palette
        option.font = tab.grid.font()
        option.state = QStyle.StateFlag.State_Active
        painter = RecordingPainter()
        tab.delegate.paint(painter, option, index)
        assert QColor("red") not in painter.pens


def test_copy_from_the_deck_view_copies_the_card_from_this_deck(tab, clipboard):
    tab.grid.setCurrentIndex(indexes(tab, KIND_CARD)[0])

    assert tab.can_copy_card()
    tab.copy_card()

    card, deck, _ = card_from_mime(clipboard.mimeData(), [tab.deck])
    assert card["id"] == "major_arcana.00"
    assert deck is tab.deck


def test_nothing_selected_has_nothing_to_copy(tab):
    tab.grid.clearSelection()
    assert not tab.can_copy_card()


# -- the grid ---------------------------------------------------------------------


@pytest.mark.parametrize("width", [700, 1300])
def test_each_heading_starts_a_line_and_no_card_shares_it(qtbot, full_deck, width):
    tab = shown(qtbot, full_deck.deck_path, width=width, height=800)
    grid = tab.grid
    headings = [grid.visualRect(index) for index in indexes(tab, KIND_HEADING)]
    cards = [grid.visualRect(index) for index in indexes(tab, KIND_CARD)]

    assert len(headings) == 5
    for heading in headings:
        assert heading.left() == grid.spacing()
        assert heading.width() == grid.viewport().width() - 2 * grid.spacing()
        for card in cards:
            assert card.bottom() < heading.top() or card.top() > heading.bottom()


def test_a_resize_lays_the_headings_out_again(qtbot, full_deck):
    tab = shown(qtbot, full_deck.deck_path, width=1300, height=800)
    wide = tab.grid.height()

    def headings_span():
        heading = tab.grid.visualRect(indexes(tab, KIND_HEADING)[0])
        return heading.width() == tab.grid.viewport().width() - 2 * tab.grid.spacing()

    tab.resize(700, 800)
    qtbot.waitUntil(lambda: headings_span() and tab.grid.height() > wide)
    tab.resize(1300, 800)
    qtbot.waitUntil(lambda: headings_span() and tab.grid.height() == wide)


def test_the_majors_wrap_instead_of_running_off_the_page(full_tab):
    grid = full_tab.grid
    majors = [grid.visualRect(index) for index in indexes(full_tab, KIND_CARD)[:22]]
    on_first_line = [rect for rect in majors if rect.top() == majors[0].top()]

    cell = units.cover_size(units.DENSITY_MEDIUM)[0] + 2 * units.LARGE_SPACING
    fits = (grid.viewport().width() - grid.spacing()) // (cell + grid.spacing())
    assert len(on_first_line) == fits
    assert all(rect.right() < grid.viewport().width() for rect in majors)
    for bar in full_tab.findChildren(QScrollBar):
        if bar.orientation() == Qt.Orientation.Horizontal:
            assert not bar.isVisible()


def test_right_from_the_last_major_lands_on_the_first_wand(full_tab):
    cards = indexes(full_tab, KIND_CARD)
    full_tab.grid.setCurrentIndex(cards[21])

    press(full_tab, Qt.Key.Key_Right)

    assert full_tab.grid.currentIndex() == cards[22]
    assert cards[22].data(CardRole)["id"] == "minor_arcana.wands.ace"


def test_left_from_the_first_wand_lands_on_the_last_major(full_tab):
    cards = indexes(full_tab, KIND_CARD)
    full_tab.grid.setCurrentIndex(cards[22])

    press(full_tab, Qt.Key.Key_Left)

    assert full_tab.grid.currentIndex() == cards[21]


def test_down_never_stops_on_a_heading(full_tab):
    cards = indexes(full_tab, KIND_CARD)
    full_tab.grid.setCurrentIndex(cards[0])
    visited = []
    for _ in range(20):
        press(full_tab, Qt.Key.Key_Down)
        visited.append(full_tab.grid.currentIndex())

    assert all(index.data(KindRole) == KIND_CARD for index in visited)
    assert visited[-1].row() > cards[22].row()


def test_shift_right_extends_the_selection_and_copy_takes_all_of_it(full_tab, clipboard):
    full_tab.grid.setCurrentIndex(indexes(full_tab, KIND_CARD)[0])

    press(full_tab, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    press(full_tab, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert full_tab.can_copy_card()
    full_tab.copy_card()

    payload = json.loads(bytes(clipboard.mimeData().data(CARD_MIME)).decode())
    assert payload["card_ids"] == ["major_arcana.00", "major_arcana.01", "major_arcana.02"]


def test_the_page_follows_the_keyboard_down(full_tab):
    bar = full_tab.scroll.verticalScrollBar()
    assert bar.value() == 0
    full_tab.grid.setCurrentIndex(indexes(full_tab, KIND_CARD)[0])

    for _ in range(12):
        press(full_tab, Qt.Key.Key_Down)

    assert bar.value() > 0
    current = full_tab.grid.visualRect(full_tab.grid.currentIndex())
    top = full_tab.grid.viewport().mapTo(full_tab.scroll.widget(), current.topLeft()).y()
    assert bar.value() <= top
    assert top + current.height() <= bar.value() + full_tab.scroll.viewport().height()


def test_a_wheel_over_the_grid_is_left_to_the_page(full_tab):
    """Qt hands an ignored wheel to the parent, but only a spontaneous one, which a test
    can't send. So: the grid leaves it, and the page takes the same event."""
    grid, page = full_tab.grid, full_tab.scroll
    assert grid.verticalScrollBar().maximum() == 0
    assert grid.horizontalScrollBar().maximum() == 0

    def wheel(widget, pos):
        return QWheelEvent(
            QPointF(pos),
            QPointF(widget.mapToGlobal(pos)),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    centre = grid.viewport().rect().center()
    event = wheel(grid.viewport(), centre)
    QApplication.sendEvent(grid.viewport(), event)
    assert not event.isAccepted()
    assert page.verticalScrollBar().value() == 0

    QApplication.sendEvent(page.viewport(), wheel(page.viewport(), centre))
    assert page.verticalScrollBar().value() > 0


def test_the_context_menu_offers_open_and_copy(full_tab, qtbot):
    first = indexes(full_tab, KIND_CARD)[0]
    actions = {a.text().replace("&", ""): a for a in full_tab.card_menu(first).actions()}

    assert list(actions) == ["Open Card", "Copy Card"]
    with qtbot.waitSignal(full_tab.card_action_requested, timeout=1000) as opened:
        actions["Open Card"].trigger()
    assert opened.args[0] == "double_click"
    assert opened.args[1]["id"] == "major_arcana.00"
    assert opened.args[2] is full_tab.deck


def test_activating_a_card_opens_it(full_tab, qtbot):
    second = indexes(full_tab, KIND_CARD)[1]
    with qtbot.waitSignal(full_tab.card_action_requested, timeout=1000) as opened:
        full_tab.grid.activated.emit(second)
    assert opened.args[1]["id"] == "major_arcana.01"


def test_clicking_a_card_names_its_image(full_tab, qtbot):
    first = indexes(full_tab, KIND_CARD)[0]
    with qtbot.waitSignal(full_tab.card_clicked, timeout=1000) as clicked:
        full_tab.grid.clicked.emit(first)
    assert clicked.args == [first.data(CardRole)["image"]]


# -- section headings -------------------------------------------------------------


def test_every_section_but_the_first_has_room_above_its_heading(full_tab):
    grid = full_tab.grid
    headings = indexes(full_tab, KIND_HEADING)
    cards = [grid.visualRect(index) for index in indexes(full_tab, KIND_CARD)]

    for heading in headings[1:]:
        rect = grid.visualRect(heading)
        above = max(card.bottom() for card in cards if card.bottom() < rect.top())
        text, _ = full_tab.delegate.heading_layout(rect, heading.row())
        assert text.top() - above >= card_delegate.SECTION_SPACE
    first = grid.visualRect(headings[0])
    assert full_tab.delegate.heading_layout(first, headings[0].row())[0].top() == first.top()


def test_a_hairline_runs_under_each_heading(full_tab):
    heading = indexes(full_tab, KIND_HEADING)[1]
    option = QStyleOptionViewItem()
    option.rect = full_tab.grid.visualRect(heading)
    option.palette = full_tab.grid.palette()
    option.font = full_tab.grid.font()
    option.state = QStyle.StateFlag.State_Active
    painter = RecordingPainter()
    full_tab.delegate.paint(painter, option, heading)

    ((rule, colour),) = painter.fills
    text, _ = full_tab.delegate.heading_layout(option.rect, heading.row())
    assert rule.height() == 1
    assert rule.width() == option.rect.width()
    assert rule.top() > text.bottom()
    assert colour.rgb() == option.palette.windowText().color().rgb()
    assert colour.alpha() == card_delegate.HEADING_RULE_ALPHA


# -- cover size ---------------------------------------------------------------------


def test_find_and_the_slider_are_pinned_above_the_banner(full_tab):
    page = full_tab.scroll
    for widget in (full_tab.search_field, full_tab.zoom_slider):
        assert widget.isVisible()
        assert not page.isAncestorOf(widget)
    header = full_tab.findChildren(DeckHeader)[0]
    assert page.isAncestorOf(header)
    assert full_tab.search_field.placeholderText() == "Find card…"

    before = full_tab.search_field.mapTo(full_tab, QPoint())
    page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
    assert page.verticalScrollBar().value() > 0
    assert full_tab.search_field.mapTo(full_tab, QPoint()) == before


def test_find_leaves_the_matching_cards_under_their_headings(full_tab):
    full_tab.search_field.setText("ace")

    names = [index.data() for index in indexes(full_tab, KIND_CARD)]
    headings = [index.data() for index in indexes(full_tab, KIND_HEADING)]
    assert names == ["Ace of Wands", "Ace of Cups", "Ace of Swords", "Ace of Pentacles"]
    assert headings == ["Wands", "Cups", "Swords", "Pentacles"]

    first = indexes(full_tab, KIND_HEADING)[0]
    rect = full_tab.grid.visualRect(first)
    assert full_tab.delegate.heading_layout(rect, first.row())[0].top() == rect.top()

    full_tab.search_field.clear()
    assert len(indexes(full_tab, KIND_CARD)) == 78


def test_find_shrinks_the_grid_to_what_it_leaves(full_tab, qtbot):
    full_height = full_tab.grid.height()
    full_tab.search_field.setText("ace")
    qtbot.waitUntil(lambda: full_tab.grid.height() < full_height)

    full_tab.search_field.setText("no card is called this")
    assert full_tab.grid.model().rowCount() == 0
    qtbot.waitUntil(lambda: full_tab.grid.height() == 0)


def test_copy_after_find_copies_only_cards_still_shown(full_tab, clipboard):
    full_tab.grid.selectAll()
    full_tab.search_field.setText("ace")

    assert [card["id"] for card in full_tab.selected_cards()] == [
        f"minor_arcana.{suit}.ace" for suit in ("wands", "cups", "swords", "pentacles")
    ]
    full_tab.copy_card()
    payload = json.loads(bytes(clipboard.mimeData().data(CARD_MIME)).decode())
    assert len(payload["card_ids"]) == 4


def test_find_is_the_tabs_own_search(full_tab):
    assert full_tab.can_find()
    full_tab.search_field.setText("moon")
    full_tab.find()
    assert full_tab.search_field.hasFocus() or not full_tab.isActiveWindow()
    assert full_tab.search_field.selectedText() == "moon"


def test_the_deck_view_starts_at_medium(full_tab):
    assert DECK_VIEW_DENSITY_DEFAULT == units.DENSITY_MEDIUM
    assert full_tab.zoom_slider.key() == units.DENSITY_MEDIUM
    assert full_tab.zoom_slider.slider.toolTip() == "Cover size"
    assert not full_tab.can_zoom("reset")


def test_density_is_remembered_apart_from_the_librarys(full_tab):
    card = indexes(full_tab, KIND_CARD)[0]
    before = full_tab.grid.visualRect(card).size()

    full_tab.zoom_slider.in_button.click()

    assert get_settings().value(DECK_VIEW_DENSITY_KEY, type=str) == units.DENSITY_LARGE
    assert get_settings().value(LIBRARY_DENSITY_KEY) is None
    after = full_tab.grid.visualRect(card).size()
    assert after.width() > before.width()
    assert after.height() > before.height()


def test_a_remembered_density_is_where_the_slider_starts(qtbot, full_deck):
    get_settings().setValue(DECK_VIEW_DENSITY_KEY, units.DENSITY_SMALL)
    tab = shown(qtbot, full_deck.deck_path)
    assert tab.zoom_slider.key() == units.DENSITY_SMALL
    assert tab.delegate.density == units.DENSITY_SMALL


def test_view_zoom_steps_the_slider(full_tab):
    assert full_tab.can_zoom("in") and full_tab.can_zoom("out")

    full_tab.zoom("in")
    assert full_tab.zoom_slider.key() == units.DENSITY_LARGE
    full_tab.zoom("in")
    assert full_tab.zoom_slider.key() == units.DENSITY_EXTRA_LARGE
    assert not full_tab.can_zoom("in")
    assert full_tab.can_zoom("reset")

    full_tab.zoom("reset")
    assert full_tab.delegate.density == units.DENSITY_MEDIUM

    full_tab.zoom("out")
    assert full_tab.delegate.density == units.DENSITY_SMALL
    assert not full_tab.can_zoom("out")


def test_ctrl_wheel_on_the_page_zooms_instead_of_scrolling(full_tab):
    page = full_tab.scroll
    centre = page.viewport().rect().center()

    def wheel(delta):
        return QWheelEvent(
            QPointF(centre),
            QPointF(page.viewport().mapToGlobal(centre)),
            QPoint(),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    QApplication.sendEvent(page.viewport(), wheel(-120))
    assert full_tab.zoom_slider.key() == units.DENSITY_SMALL
    QApplication.sendEvent(page.viewport(), wheel(120))
    assert full_tab.zoom_slider.key() == units.DENSITY_MEDIUM
    assert page.verticalScrollBar().value() == 0
