import os

import pytest
from PyQt6.QtCore import QPointF, QSize
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QMessageBox

from tarot_canvas.models import spreads, staged_delete
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.settings import (
    LIBRARY_SORT_KEY,
    LIBRARY_SPREADS_SORT_KEY,
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_KEY,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEW_SPREADS,
    LIBRARY_VIEWS,
    get_settings,
)
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.tab_icon import (
    MINIMAP,
    layout_marks,
    render_spread,
    spread_marks,
)
from tarot_canvas.ui.card_colours import SLOT_COLOUR
from tarot_canvas.ui.library.deck_model import SORT_AUTHOR, SORT_COUNT, SORT_NAME, SubtitleRole
from tarot_canvas.ui.library.notes_model import PreviewRole
from tarot_canvas.ui.library.spread_row_delegate import SpreadRowDelegate
from tarot_canvas.ui.library.spreads_model import SORT_EDITED, SORT_NEWEST, SpreadPathRole
from tarot_canvas.ui.library.spreads_page import SpreadsPage
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab

Answer = QMessageBox.StandardButton
UNIT = QSize(200, 340)


@pytest.fixture(autouse=True)
def card_unit(monkeypatch):
    """The stub deck's art is one pixel square"""
    for module in (
        "canvas.slot_item",
        "tabs.spread_tab",
        "tabs.canvas_tab",
        "library.spreads_model",
    ):
        monkeypatch.setattr(f"tarot_canvas.ui.{module}.card_unit_size", lambda: UNIT)


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    """A window left with unsaved work would otherwise wait on a dialog as it closes"""
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning", lambda *_: Answer.Discard
    )


def store(base, stamp, spread):
    folder = base / str(stamp)
    folder.mkdir(parents=True)
    spreads.save(folder, spread)
    return folder


def two_slots(name="Two"):
    return Spread(
        name=name,
        description="First paragraph\nstill first.\n\nSecond paragraph.",
        sources=({"url": "https://example.org/a", "author": "Ana", "note": "from a zine"},),
        positions=(
            Position(id="p1", label="Past", meaning="What led here", x=-1.0, y=0.5),
            Position(id="p2", label="Future", meaning="Whither", x=1.0, y=-0.5, rotation=90.0),
        ),
    )


@pytest.fixture
def page(qtbot, spreads_base):
    store(spreads_base, 1000, two_slots("Older"))
    store(
        spreads_base, 2000, Spread(name="Newer", positions=(Position(id="p1", meaning="Zephyr"),))
    )
    page = SpreadsPage()
    qtbot.addWidget(page)
    page.resize(600, 500)
    return page


def names(page):
    model = page.list_model
    return [model.index(row, 0).data() for row in range(model.rowCount())]


def index_of(page, name):
    return page.list_model.index(names(page).index(name), 0)


@pytest.fixture
def window(qtbot, spreads_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def open_library(window):
    library = LibraryTab()
    window.tab_widget.addTab(library, "Library")
    window.tab_widget.setCurrentWidget(library)
    library.show_view(LIBRARY_VIEW_SPREADS)
    return library


# -- marks


def test_a_spread_gives_one_slot_mark_per_position_keeping_its_shape():
    marks = layout_marks(spread_marks(two_slots(), UNIT), MINIMAP.max_fill)

    assert [mark.colour for mark in marks] == [SLOT_COLOUR, SLOT_COLOUR]
    left, right = marks
    assert left.x < right.x
    assert left.y > right.y
    assert right.angle == 90.0
    assert left.h / left.w == pytest.approx(UNIT.height() / UNIT.width())


def test_a_spreads_marks_paint():
    marks = layout_marks(spread_marks(two_slots(), UNIT), MINIMAP.max_fill)
    image = render_spread(marks, MINIMAP, 64)
    empty = render_spread((), MINIMAP, 64)

    assert image != empty


def test_a_spread_with_no_positions_has_no_marks():
    assert layout_marks(spread_marks(Spread(), UNIT)) == ()


# -- the list


def test_the_view_is_the_librarys_last_row(window):
    library = open_library(window)

    assert LIBRARY_VIEWS[-1] == LIBRARY_VIEW_SPREADS
    assert library.sidebar.count() == len(LIBRARY_VIEWS)
    assert library.current_list_page() is library.spreads_page
    assert library.search_field.placeholderText() == SPREADS["search_placeholder"]


def test_rows_are_newest_first_by_folder_number(qtbot, spreads_base):
    for stamp in (9, 10, 100):
        store(spreads_base, stamp, Spread(name=str(stamp)))
    page = SpreadsPage()
    qtbot.addWidget(page)

    assert names(page) == ["100", "10", "9"]


def test_a_row_says_its_name_slot_count_and_first_paragraph(page):
    older = index_of(page, "Older")

    assert older.data(SubtitleRole) == SPREADS["slot_count"].format(count=2)
    assert older.data(PreviewRole) == "First paragraph still first."
    assert index_of(page, "Newer").data(SubtitleRole) == SPREADS["slot_count_one"]


def test_a_spread_with_no_name_is_listed_as_untitled(qtbot, spreads_base):
    store(spreads_base, 1, Spread())
    page = SpreadsPage()
    qtbot.addWidget(page)

    assert names(page) == [SPREADS["untitled"]]


@pytest.mark.parametrize(
    "word, found",
    [
        ("older", ["Older"]),
        ("second paragraph", ["Older"]),
        ("FUTURE", ["Older"]),
        ("zephyr", ["Newer"]),
        ("ana", ["Older"]),
        ("zine", ["Older"]),
        ("example.org", []),
    ],
)
def test_search_reads_the_name_prose_slots_and_sources(page, word, found):
    page.set_search(word)

    assert names(page) == found


def test_a_source_value_that_is_not_text_does_not_break_search(qtbot, spreads_base):
    store(spreads_base, 1, Spread(name="Odd", sources=({"author": 3},)))
    page = SpreadsPage()
    qtbot.addWidget(page)

    page.set_search("3")

    assert names(page) == ["Odd"]


def test_no_spreads_says_so_and_no_match_says_that(qtbot, spreads_base, page):
    page.set_search("nothing has this")
    assert page.empty_label.text() == SPREADS["empty_no_match"]

    empty = SpreadsPage(base=spreads_base / "none")
    qtbot.addWidget(empty)
    assert empty.empty_label.text() == SPREADS["empty"]


def test_the_list_follows_saving(page, spreads_base):
    store(spreads_base, 3000, Spread(name="Newest"))

    spread_events().spreads_changed.emit()

    assert names(page)[0] == "Newest"


# -- sorting


def slots(count):
    return tuple(Position(id=f"p{number}") for number in range(1, count + 1))


@pytest.fixture
def sorted_page(qtbot, spreads_base):
    """Oldest to newest: Banana has 3 slots, apple 1 and Cherry 2. Banana was edited last"""
    paths = [
        store(spreads_base, 1000, Spread(name="Banana", positions=slots(3))),
        store(spreads_base, 2000, Spread(name="apple", positions=slots(1))),
        store(spreads_base, 3000, Spread(name="Cherry", positions=slots(2))),
    ]
    for edited, path in zip((300, 100, 200), paths, strict=True):
        os.utime(path / spreads.SPREAD_FILE, (edited, edited))
    page = SpreadsPage()
    qtbot.addWidget(page)
    return page


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        (SORT_NEWEST, ["Cherry", "apple", "Banana"]),
        (SORT_NAME, ["apple", "Banana", "Cherry"]),
        (SORT_COUNT, ["apple", "Cherry", "Banana"]),
        (SORT_EDITED, ["Banana", "Cherry", "apple"]),
    ],
)
def test_each_sort_orders_the_rows(sorted_page, sort, expected):
    sorted_page.set_sort_key(sort)

    assert names(sorted_page) == expected


def test_a_tie_goes_by_name(qtbot, spreads_base):
    store(spreads_base, 1000, Spread(name="Zebra", positions=slots(2)))
    store(spreads_base, 2000, Spread(name="Ant", positions=slots(2)))
    page = SpreadsPage()
    qtbot.addWidget(page)

    page.set_sort_key(SORT_COUNT)

    assert names(page) == ["Ant", "Zebra"]


def test_an_untitled_spread_sorts_by_the_name_it_shows(qtbot, spreads_base):
    store(spreads_base, 1000, Spread())
    store(spreads_base, 2000, Spread(name="Zebra"))
    store(spreads_base, 3000, Spread(name="Ant"))
    page = SpreadsPage()
    qtbot.addWidget(page)

    page.set_sort_key(SORT_NAME)

    assert names(page) == ["Ant", SPREADS["untitled"], "Zebra"]


def test_a_sort_change_keeps_the_selection(sorted_page):
    sorted_page.select(index_of(sorted_page, "apple").data(SpreadPathRole))

    sorted_page.set_sort_key(SORT_NAME)

    assert sorted_page._selected_path() == index_of(sorted_page, "apple").data(SpreadPathRole)


def test_a_search_keeps_the_sort(sorted_page):
    sorted_page.set_sort_key(SORT_NAME)

    sorted_page.set_search("an")

    assert names(sorted_page) == ["Banana"]
    sorted_page.set_search("")
    assert names(sorted_page) == ["apple", "Banana", "Cherry"]


def test_saving_moves_a_spread_to_the_top_of_recently_edited(sorted_page):
    sorted_page.set_sort_key(SORT_EDITED)
    path = index_of(sorted_page, "apple").data(SpreadPathRole)

    spreads.save(path, Spread(name="apple", positions=slots(1)))
    spread_events().spreads_changed.emit()

    assert names(sorted_page)[0] == "apple"


def test_a_page_opens_on_the_saved_sort(qtbot, sorted_page):
    sorted_page.set_sort_key(SORT_NAME)

    again = SpreadsPage()
    qtbot.addWidget(again)

    assert names(again) == ["apple", "Banana", "Cherry"]


def test_an_unknown_saved_sort_is_newest(qtbot, sorted_page):
    get_settings().setValue(LIBRARY_SPREADS_SORT_KEY, "nonsense")

    again = SpreadsPage()
    qtbot.addWidget(again)

    assert again.sort_key() == SORT_NEWEST


def sort_keys(library):
    combo = library.sort_combo
    return [combo.itemData(row) for row in range(combo.count())]


def test_the_combo_offers_each_views_own_sorts(window, spreads_base):
    library = open_library(window)

    assert not library.sort_combo.isHidden()
    assert sort_keys(library) == [SORT_NEWEST, SORT_NAME, SORT_COUNT, SORT_EDITED]
    assert library.sort_combo.toolTip() == SPREADS["sort_tooltip"]

    library.show_view(LIBRARY_VIEW_DECKS)
    assert SORT_AUTHOR in sort_keys(library)
    assert SORT_EDITED not in sort_keys(library)

    library.show_view(LIBRARY_VIEW_NOTES)
    assert library.sort_combo.isHidden()


def test_each_view_keeps_its_own_sort(window, spreads_base):
    library = open_library(window)
    combo = library.sort_combo
    combo.setCurrentIndex(combo.findData(SORT_EDITED))

    library.show_view(LIBRARY_VIEW_DECKS)
    combo.setCurrentIndex(combo.findData(SORT_AUTHOR))
    library.show_view(LIBRARY_VIEW_SPREADS)

    assert combo.currentData() == SORT_EDITED
    assert library.spreads_page.sort_key() == SORT_EDITED
    assert library.proxy_model.sort_key() == SORT_AUTHOR
    settings = get_settings()
    assert settings.value(LIBRARY_SPREADS_SORT_KEY, type=str) == SORT_EDITED
    assert settings.value(LIBRARY_SORT_KEY, type=str) == SORT_AUTHOR


def test_opening_on_spreads_keeps_the_decks_saved_sort(window, spreads_base):
    get_settings().setValue(LIBRARY_VIEW_KEY, LIBRARY_VIEW_SPREADS)
    get_settings().setValue(LIBRARY_SORT_KEY, SORT_AUTHOR)

    library = LibraryTab()
    window.tab_widget.addTab(library, "Library")

    assert library.proxy_model.sort_key() == SORT_AUTHOR
    assert library.sort_combo.currentData() == SORT_NEWEST


def test_a_row_paints_the_spreads_shape(page):
    delegate = SpreadRowDelegate(page.list_view)
    side = 120
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)

    delegate._paint_well(painter, image.rect(), page.palette(), index_of(page, "Older"))
    painter.end()

    assert image.pixelColor(side // 2, 4) != QColor("white")


# -- the details pane


def shown_text(page):
    return [label.text() for label in page.details_pane.section_labels()]


def test_the_pane_shows_the_spread_with_its_slots_in_number_order(page):
    page._select_index(index_of(page, "Older"))

    pane = page.details_pane
    assert pane.heading_label.text() == "Older"
    texts = shown_text(page)
    assert "Second paragraph." in texts[1]
    assert texts[1].count("<p ") == 2
    assert texts[2] == SPREADS["sources_title"]
    assert "Ana • from a zine" in texts[3] and 'href="https://example.org/a"' in texts[3]
    assert texts[4:] == [
        SPREADS["slots_title"],
        "1. Past",
        "What led here",
        "2. Future",
        "Whither",
    ]


def test_showing_another_spread_leaves_none_of_the_last_on_screen(page):
    page._select_index(index_of(page, "Older"))
    before = page.details_pane.section_labels()

    page._select_index(index_of(page, "Newer"))

    assert not any(label.isVisibleTo(page.details_pane) for label in before)


def test_description_and_a_source_are_escaped(qtbot, spreads_base):
    spread = Spread(
        name="X",
        description="<b>bold</b>",
        sources=({"author": "<i>A</i>", "url": "not a link"},),
    )
    store(spreads_base, 1, spread)
    page = SpreadsPage()
    qtbot.addWidget(page)

    page._select_index(page.list_model.index(0, 0))

    description, source = shown_text(page)[1], shown_text(page)[3]
    assert "<b>" not in description
    assert "<i>" not in source and "not a link" in source and "href" not in source


def test_a_slot_with_no_label_or_meaning_is_only_its_number(qtbot, spreads_base):
    store(spreads_base, 1, Spread(name="X", positions=(Position(id="p1"),)))
    page = SpreadsPage()
    qtbot.addWidget(page)

    page._select_index(page.list_model.index(0, 0))

    assert shown_text(page) == [SPREADS["slots_title"], "1."]


# -- opening


def test_activating_a_row_opens_its_spread_tab(window, spreads_base):
    folder = store(spreads_base, 1000, two_slots())
    library = open_library(window)
    page = library.spreads_page

    page.list_view.activated.emit(page.list_model.index(0, 0))

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, SpreadTab)
    assert tab.spread_path == folder
    assert [slot.label for slot in tab.slots()] == ["Past", "Future"]


# -- deleting


def test_deleting_takes_the_row_and_undo_brings_it_back_selected(page, spreads_base):
    folder = spreads_base / "1000"

    page.delete(folder)

    assert names(page) == ["Newer"]
    assert not folder.exists()
    assert page.message.isVisibleTo(page)

    page.undo_action.trigger()

    assert names(page) == ["Newer", "Older"]
    assert spreads.load(folder).name == "Older"
    assert not page.message.isVisibleTo(page)
    assert page.list_view.currentIndex().data(SpreadPathRole) == folder


def test_dismissing_the_message_makes_the_delete_final(page, spreads_base):
    page.delete(spreads_base / "1000")

    page.message.dismiss()

    assert sorted(path.name for path in spreads_base.iterdir()) == ["2000"]


def test_a_second_delete_makes_the_first_final(page, spreads_base):
    page.delete(spreads_base / "1000")
    page.delete(spreads_base / "2000")

    page.undo_action.trigger()

    assert names(page) == ["Newer"]
    assert sorted(path.name for path in spreads_base.iterdir()) == ["2000"]


def test_a_delete_that_fails_keeps_the_row_and_says_so(page, spreads_base, monkeypatch):
    def refuse(_path):
        raise OSError("no")

    monkeypatch.setattr(staged_delete, "stage", refuse)

    page.delete(spreads_base / "1000")

    assert names(page) == ["Newer", "Older"]
    assert page.message.label.text() == SPREADS["delete_failed"]
    assert page.staged is None


def test_the_rows_menu_asks_to_delete(page, qtbot, spreads_base):
    menu = page.row_menu(index_of(page, "Older"))
    (action,) = menu.actions()
    assert action.text() == SPREADS["delete"]

    with qtbot.waitSignal(page.delete_requested) as requested:
        action.trigger()

    assert requested.args == [spreads_base / "1000"]


def test_deleting_the_shown_spread_empties_and_closes_the_pane(window, spreads_base):
    folder = store(spreads_base, 1000, two_slots())
    store(spreads_base, 2000, Spread(name="Other"))
    library = open_library(window)
    page = library.spreads_page
    page.select(folder)
    library.toggle_details_pane()
    assert library.details_pane_is_open()

    page.delete_requested.emit(folder)

    assert page.details_pane.details() is None
    assert not library.details_pane_is_open()
    assert not library.details_toggle.isEnabled()


def test_a_spread_saved_again_updates_the_pane(page, spreads_base):
    page._select_index(index_of(page, "Older"))
    folder = spreads_base / "1000"
    spreads.save(folder, Spread(name="Renamed"))

    page.refresh()

    assert page.details_pane.heading_label.text() == "Renamed"
    assert page.list_view.currentIndex().data() == "Renamed"


def test_deleting_an_open_spread_closes_its_tab_first(window, spreads_base):
    folder = store(spreads_base, 1000, two_slots())
    library = open_library(window)
    tab = window.open_spread(folder)

    library.spreads_page.delete_requested.emit(folder)

    assert window.tab_widget.indexOf(tab) == -1
    assert not folder.exists()
    assert window.tab_widget.currentWidget() is library


def test_cancelling_the_tabs_close_cancels_the_delete(window, spreads_base, monkeypatch):
    folder = store(spreads_base, 1000, two_slots())
    library = open_library(window)
    tab = window.open_spread(folder)
    tab.mark_modified()
    monkeypatch.setattr("tarot_canvas.ui.main_window.QMessageBox.warning", lambda *_: Answer.Cancel)

    library.spreads_page.delete_requested.emit(folder)

    assert window.tab_widget.indexOf(tab) != -1
    assert folder.exists()
    assert library.spreads_page.staged is None
    tab._modified = False


def test_closing_the_library_makes_a_pending_delete_final(window, spreads_base):
    folder = store(spreads_base, 1000, two_slots())
    library = open_library(window)
    library.spreads_page.delete(folder)

    window.close_tab(window.tab_widget.indexOf(library))

    assert list(spreads_base.iterdir()) == []


# -- saving a layout


def add_card(tab, centre, z, orient=0):
    card = DraggableCardItem(_pixmap(), {"id": f"card{z}"}, tab)
    card.setPos(centre - card.boundingRect().center())
    card.setZValue(z)
    card.set_orient(orient)
    tab.scene.addItem(card)
    return card


def _pixmap():
    pixmap = QPixmap(150, 260)
    pixmap.fill(QColor("white"))
    return pixmap


def centre(item):
    return item.pos() + item.boundingRect().center()


def test_a_layout_becomes_an_unsaved_spread_of_numbered_slots(window, spreads_base):
    canvas = window.new_canvas_tab()
    add_card(canvas, QPointF(0, 0), 1)
    add_card(canvas, QPointF(400, 0), 3)
    add_card(canvas, QPointF(200, 200), 2, orient=90)

    canvas.commands["canvas.save_layout_as_spread"].trigger()

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, SpreadTab) and tab is not canvas
    slots = tab.slots()
    assert [slot.number for slot in slots] == [1, 2, 3]
    assert [slot.position_id for slot in slots] == ["p1", "p2", "p3"]
    assert [slot.orient for slot in slots] == [0, 90, 0]
    assert [slot.zValue() for slot in slots] == [1, 2, 3]
    assert [slot.label for slot in slots] == ["", "", ""]

    # Where the cards were, from the first
    first = centre(slots[0])
    for slot, (x, y) in zip(slots[1:], ((200, 200), (400, 0)), strict=True):
        assert centre(slot).x() - first.x() == pytest.approx(x, abs=0.5)
        assert centre(slot).y() - first.y() == pytest.approx(y, abs=0.5)

    assert len(canvas.cards()) == 3
    assert tab.spread_path is None and tab.has_unsaved_changes()
    assert list(spreads_base.glob("*")) == []


def test_ctrl_s_keeps_the_new_spread(window, spreads_base):
    canvas = window.new_canvas_tab()
    add_card(canvas, QPointF(0, 0), 1)
    canvas.on_save_layout_as_spread()

    assert window.tab_widget.currentWidget().save()

    (folder,) = spreads_base.iterdir()
    assert len(spreads.load(folder).positions) == 1


def test_the_command_needs_a_card(qtbot, window):
    canvas = window.new_canvas_tab()
    action = canvas.commands["canvas.save_layout_as_spread"]
    assert not action.isEnabled()

    card = add_card(canvas, QPointF(0, 0), 1)
    assert action.isEnabled()

    canvas.scene.removeItem(card)
    assert not action.isEnabled()


def test_it_is_on_a_canvass_toolbar_after_align_with_no_default_key(window):
    canvas = window.new_canvas_tab()
    actions = canvas.toolbar.actions()
    align = actions.index(canvas.commands["canvas.align"])

    assert actions[align + 1] is canvas.commands["canvas.save_layout_as_spread"]
    assert commands.by_id("canvas.save_layout_as_spread").defaults == ()


def test_a_spread_tab_has_no_such_command(window):
    tab = window.new_spread_tab()

    assert "canvas.save_layout_as_spread" not in tab.commands


# -- nothing selected, nothing changed


@pytest.mark.parametrize(
    "command",
    ["canvas.rotate", "canvas.delete", "canvas.bring_to_front", "canvas.send_to_back"],
)
def test_a_command_with_nothing_selected_leaves_a_saved_spread_unmodified(
    window, spreads_base, command
):
    tab = window.open_spread(store(spreads_base, 1000, two_slots()))

    tab.commands[command].setEnabled(True)
    tab.commands[command].trigger()

    assert not tab.has_unsaved_changes()


def test_a_plain_canvas_rotate_with_nothing_selected_reports_no_change(qtbot, window):
    canvas = window.new_canvas_tab()
    assert isinstance(canvas, CanvasTab)

    with qtbot.assertNotEmitted(canvas.layout_changed):
        canvas.on_flip_card()
