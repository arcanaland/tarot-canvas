from datetime import datetime, timedelta

import pytest
from PyQt6.QtWidgets import QMessageBox

from tarot_canvas.models import readings
from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.settings import (
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEW_READINGS,
    LIBRARY_VIEW_SPREADS,
    LIBRARY_VIEWS,
    get_settings,
)
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS, local_qdatetime
from tarot_canvas.ui.library.readings.model import (
    SORT_EDITED,
    SORT_NEWEST,
    SORT_OLDEST,
    ReadingPathRole,
)
from tarot_canvas.ui.library.readings.page import ReadingsPage
from tarot_canvas.ui.library.section_row import is_section
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.utils.dates import format_month, format_qdatetime

NOW = datetime.now().astimezone().replace(microsecond=0)


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


def keep(base, folder, when, question="", cards=(), note=None):
    path = base / folder
    readings.save(path, Reading(date=when, question=question, cards=tuple(cards)))
    if note is not None:
        (path / "1700000000.md").write_text(note, encoding="utf-8")
    return path


@pytest.fixture
def three(readings_base):
    return [
        keep(readings_base, "1", NOW - timedelta(days=2), "Oldest", note="the river bends"),
        keep(readings_base, "3", NOW, "Newest"),
        keep(readings_base, "2", NOW - timedelta(days=1)),
    ]


@pytest.fixture
def page(qtbot, minimal_deck):
    page = ReadingsPage(lambda: [minimal_deck], lambda: minimal_deck)
    qtbot.addWidget(page)
    return page


@pytest.fixture
def window(qtbot, stub_deck_manager, spreads_base, notes_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def shown(page):
    """Each row's label, a heading's in capitals"""
    model = page.list_model
    rows = (model.index(row, 0) for row in range(model.rowCount()))
    return [index.data().upper() if is_section(index) else index.data() for index in rows]


def labels(page):
    model = page.list_model
    rows = (model.index(row, 0) for row in range(model.rowCount()))
    return [index.data() for index in rows if not is_section(index)]


def first_reading(page):
    return next(
        page.list_model.index(row, 0)
        for row in range(page.list_model.rowCount())
        if not is_section(page.list_model.index(row, 0))
    )


def readings_view(window):
    library = window.new_library_tab(LIBRARY_VIEW_READINGS)
    return library, library.readings_page


# -- the view -------------------------------------------------------------------------------


def test_the_journal_comes_after_decks_and_before_notes():
    assert LIBRARY_VIEWS[:3] == (LIBRARY_VIEW_DECKS, LIBRARY_VIEW_READINGS, LIBRARY_VIEW_NOTES)


def test_the_library_shows_the_readings_page(window):
    library, page = readings_view(window)
    assert library.pages.currentWidget() is page
    assert library.current_details_pane() is page.details_pane
    assert library.search_field.placeholderText() == READINGS["library_search_placeholder"]


def test_with_no_readings_the_empty_state_says_what_a_reading_is(page):
    assert page.empty_label.isVisibleTo(page)
    assert page.empty_label.text() == READINGS["library_empty"]
    assert not page.list_view.isVisibleTo(page)


# -- rows -----------------------------------------------------------------------------------


def test_rows_are_newest_first_and_a_reading_without_a_question_shows_its_date(three, page):
    plain = format_qdatetime(local_qdatetime(NOW - timedelta(days=1)))
    assert labels(page) == ["Newest", plain, "Oldest"]


def test_a_row_has_the_canvas_minimap(readings_base, page, minimal_deck):
    card = minimal_deck.get_all_cards()[0]["id"]
    keep(readings_base, "1", NOW, "Q", cards=[ReadingCard(id=card)])
    page.refresh()
    from PyQt6.QtCore import Qt

    assert not first_reading(page).data(Qt.ItemDataRole.DecorationRole).isNull()


def month(year, number):
    return datetime(year, number, 15, 12).astimezone()


@pytest.fixture
def two_months(readings_base):
    keep(
        readings_base,
        "1",
        month(
            2026,
            10,
        ),
        "October",
    )
    keep(readings_base, "2", month(2026, 11), "Early November")
    keep(readings_base, "3", month(2026, 11) + timedelta(days=5), "Late November")


def heading(year, number):
    return format_month(local_qdatetime(month(year, number)).date()).upper()


def test_by_date_the_rows_sit_under_a_heading_per_month(two_months, page):
    assert shown(page) == [
        heading(2026, 11),
        "Late November",
        "Early November",
        heading(2026, 10),
        "October",
    ]
    assert not page.list_model.flags(page.list_model.index(0, 0))


def test_oldest_first_keeps_the_headings_in_its_order(two_months, page):
    page.set_sort_key(SORT_OLDEST)
    assert shown(page) == [
        heading(2026, 10),
        "October",
        heading(2026, 11),
        "Early November",
        "Late November",
    ]


def test_recently_edited_has_no_headings_and_a_note_counts_as_an_edit(
    two_months, page, readings_base
):
    import os

    for folder, stamp in (("1", 3000), ("2", 1000), ("3", 2000)):
        os.utime(readings_base / folder / readings.READING_FILE, (stamp, stamp))
    note = readings_base / "2" / "1700000000.md"
    note.write_text("later", encoding="utf-8")
    os.utime(note, (4000, 4000))
    page.refresh()

    page.set_sort_key(SORT_EDITED)

    assert shown(page) == ["Early November", "October", "Late November"]


def test_the_sort_is_remembered(two_months, page, qtbot, minimal_deck):
    page.set_sort_key(SORT_OLDEST)
    again = ReadingsPage(lambda: [minimal_deck], lambda: minimal_deck)
    qtbot.addWidget(again)
    assert again.sort_key() == SORT_OLDEST
    get_settings().clear()
    assert ReadingsPage().sort_key() == SORT_NEWEST


def test_the_library_offers_the_readings_sorts(window):
    library, _page = readings_view(window)
    keys = [library.sort_combo.itemData(n) for n in range(library.sort_combo.count())]
    assert keys == [SORT_NEWEST, SORT_OLDEST, SORT_EDITED]
    assert library.sort_combo.isVisibleTo(library)


# -- search ---------------------------------------------------------------------------------


def test_a_term_only_in_a_note_matches_that_reading_alone(three, page):
    page.set_search("RIVER")
    assert labels(page) == ["Oldest"]


def test_a_term_in_a_question_matches(three, page):
    page.set_search("newe")
    assert labels(page) == ["Newest"]


def test_a_card_or_deck_name_matches(readings_base, page, minimal_deck):
    card = minimal_deck.get_all_cards()[0]
    keep(readings_base, "1", NOW, "With", cards=[ReadingCard(id=card["id"])])
    keep(readings_base, "2", NOW, "Without")
    page.refresh()

    page.set_search(card["name"])
    assert labels(page) == ["With"]
    page.set_search(minimal_deck.get_name())
    assert labels(page) == ["With"]


def test_a_search_with_no_match_says_so(three, page):
    page.set_search("nothing like this")
    assert page.empty_label.text() == READINGS["library_empty_no_match"]


# -- details and open -----------------------------------------------------------------------


def test_the_pane_shows_the_question_date_cards_and_newest_note(readings_base, page, minimal_deck):
    first, second = (card["id"] for card in minimal_deck.get_all_cards()[:2])
    keep(
        readings_base,
        "1",
        NOW,
        "Should I?",
        cards=[ReadingCard(id=first), ReadingCard(id=second, reversed=True)],
        note="# Morning\nclear skies",
    )
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    pane = page.details_pane
    names = [minimal_deck.get_card_by_id(card)["name"] for card in (first, second)]
    assert pane.heading_label.text() == "Should I?"
    assert pane.date_label.text() == format_qdatetime(local_qdatetime(NOW))
    assert pane.card_lines() == [names[0], READINGS["card_reversed"].format(card=names[1])]
    assert pane.note_label.text() == "Morning"


def test_activating_a_row_opens_its_reading_in_a_tab(three, window):
    _library, page = readings_view(window)
    page.list_view.activated.emit(first_reading(page))

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, CanvasTab)
    assert tab.reading_path == three[1]


def test_the_panes_open_button_opens_the_reading(three, window):
    _library, page = readings_view(window)
    page.list_view.clicked.emit(first_reading(page))
    page.details_pane.open_button.click()

    assert window.tab_widget.currentWidget().reading_path == three[1]


# -- the header -----------------------------------------------------------------------------


def test_new_reading_shows_only_on_the_journal(window):
    library, _page = readings_view(window)
    assert library.new_reading_button.isVisibleTo(library)
    library.show_view(LIBRARY_VIEW_SPREADS)
    assert not library.new_reading_button.isVisibleTo(library)


def test_new_readings_menu_leads_with_a_blank_canvas(window):
    library, _page = readings_view(window)
    menu = library.new_reading_button.menu()
    menu.aboutToShow.emit()

    first = menu.actions()[0]
    assert first.text().split("\t")[0] == commands.by_id("window.new_canvas").text
    assert menu.actions()[1].isSeparator()

    first.trigger()
    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, CanvasTab) and tab.reading_path is None


# -- delete ---------------------------------------------------------------------------------


def test_delete_takes_the_row_and_folder_and_undo_brings_them_back(three, page):
    page.delete(three[1])

    assert "Newest" not in labels(page)
    assert not three[1].exists()

    page.undo_action.trigger()

    assert labels(page)[0] == "Newest"
    assert readings.load(three[1]).question == "Newest"
    assert page.list_view.currentIndex().data(ReadingPathRole) == three[1]


def test_the_menu_deletes_through_the_library(three, window):
    library, page = readings_view(window)
    menu = page.row_menu(first_reading(page))
    entries = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert entries == [READINGS["library_open"], READINGS["library_delete"]]

    menu.actions()[-1].trigger()

    assert not three[1].exists()
    assert library.readings_page.staged is not None


def test_deleting_an_open_reading_closes_its_tab_first_and_nothing_rewrites_it(
    qtbot, three, window
):
    tab = window.open_saved_reading(three[1])
    tab.saved_reading.set_question("Changed")
    library, page = readings_view(window)

    library.on_reading_delete_requested(three[1])

    assert window.tab_widget.indexOf(tab) == -1
    assert window.tab_widget.currentWidget() is library
    assert not three[1].exists()
    qtbot.wait(AUTOSAVE_MS + 200)
    assert not three[1].exists()

    page.undo_action.trigger()
    # The close wrote the pending edit before the folder went aside
    assert readings.load(three[1]).question == "Changed"


def test_closing_the_library_makes_a_pending_delete_final(three, window, readings_base):
    library, page = readings_view(window)
    page.delete(three[0])
    window.new_canvas_tab()

    window.close_tab(window.tab_widget.indexOf(library))

    assert page.staged is None
    assert sorted(path.name for path in readings_base.iterdir()) == ["2", "3"]


# -- live refresh ---------------------------------------------------------------------------


def test_save_as_reading_adds_a_row_without_reopening_the_library(window, minimal_deck):
    _library, page = readings_view(window)
    assert labels(page) == []

    canvas = window.new_canvas_tab()
    canvas.add_specific_card(minimal_deck.get_all_cards()[0], card_deck=minimal_deck)
    window.update_save_action()
    window.save_action.trigger()

    assert [first_reading(page).data(ReadingPathRole)] == [canvas.reading_path]
