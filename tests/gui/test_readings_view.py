from datetime import datetime, timedelta

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QMessageBox

from tarot_canvas.models import readings
from tarot_canvas.models.ground import Ground
from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.settings import (
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEW_READINGS,
    LIBRARY_VIEW_SPREADS,
    LIBRARY_VIEWS,
    get_settings,
)
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS, local_qdatetime
from tarot_canvas.ui.library import diagram as diagram_module
from tarot_canvas.ui.library.readings.details_pane import ReadingDetailsPane
from tarot_canvas.ui.library.readings.model import (
    SORT_EDITED,
    SORT_NEWEST,
    SORT_OLDEST,
    CardRow,
    ReadingPathRole,
    card_row_text,
    spatial_order,
)
from tarot_canvas.ui.library.readings.page import ReadingsPage
from tarot_canvas.ui.library.roles import BadgeRole, SubtitleRole
from tarot_canvas.ui.library.section_row import is_section
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import READINGS, SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.utils.dates import format_month, format_qdatetime, format_recent

NOW = datetime.now().astimezone().replace(microsecond=0)


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


def keep(base, folder, when, question="", cards=(), note=None, **fields):
    path = base / folder
    readings.save(path, Reading(date=when, question=question, cards=tuple(cards), **fields))
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


PAST_PRESENT_FUTURE = Spread(
    name="Three ways",
    positions=tuple(
        Position(id=key, label=key.title(), x=float(n))
        for n, key in enumerate(("past", "present", "future"))
    ),
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


def test_the_pane_shows_the_question_date_numbered_cards_and_note(
    readings_base, page, minimal_deck
):
    first, second = (card["id"] for card in minimal_deck.get_all_cards()[:2])
    keep(
        readings_base,
        "1",
        NOW,
        "Should I?",
        spread=PAST_PRESENT_FUTURE,
        cards=[ReadingCard(id=first), ReadingCard(id=second, reversed=True)],
        note="# Morning\nclear skies",
    )
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    pane = page.details_pane
    names = [minimal_deck.get_card_by_id(card)["name"] for card in (first, second)]
    assert pane.heading_label.text() == "Should I?"
    assert pane.meta_label.text() == READINGS["library_meta"].format(
        when=format_recent(local_qdatetime(NOW)), spread="Three ways"
    )
    assert pane.card_lines() == [
        card_row_text(CardRow(1, "", names[0], False)),
        card_row_text(CardRow(2, "", names[1], True)),
    ]
    assert pane.card_lines()[1] == SPREADS["slot_row"].format(
        number=2, label=READINGS["card_reversed"].format(card=names[1])
    )
    # The whole note, under the pane's own title rather than its heading
    assert pane.note_view.toPlainText() == "clear skies"
    assert pane.note_view.isVisibleTo(pane)


def test_the_pane_shows_the_note_the_readings_tab_edits(readings_base, page):
    path = keep(readings_base, "1", NOW, "Two notes")
    (path / "1700000000.md").write_text("# Older\n\nfirst words", encoding="utf-8")
    (path / "1800000000.md").write_text("# Newer\n\nlater words", encoding="utf-8")
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    assert page.details_pane.note_view.toPlainText() == "first words"


def test_a_reading_without_a_note_shows_no_note_section(readings_base, page):
    keep(readings_base, "1", NOW, "Quiet")
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    pane = page.details_pane
    assert not pane.note_rule.isVisibleTo(pane)
    assert not pane.note_view.isVisibleTo(pane)


@pytest.fixture
def mid_deal(readings_base, minimal_deck):
    """A kept spread reading with its third card still face down, and reversed"""
    first, second = (card["id"] for card in minimal_deck.get_all_cards()[:2])
    keep(
        readings_base,
        "1",
        NOW,
        "Mid-deal",
        spread=PAST_PRESENT_FUTURE,
        cards=[
            ReadingCard(id=first, position="past"),
            ReadingCard(id=first, position="present", reversed=True),
            ReadingCard(id=second, position="future", reversed=True, turned=False),
        ],
    )
    return [minimal_deck.get_card_by_id(card)["name"] for card in (first, second)]


def test_a_face_down_card_is_numbered_and_placed_but_not_named(mid_deal, page):
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    lines = page.details_pane.card_lines()
    face_down = READINGS["library_card_position"].format(
        position="Future", card=READINGS["library_face_down"]
    )
    assert lines[2] == SPREADS["slot_row"].format(number=3, label=face_down)
    assert mid_deal[1] not in lines[2]
    # No reversal mark either: that gives it away too
    assert READINGS["card_reversed"].format(card="") not in lines[2]
    assert lines[1] == SPREADS["slot_row"].format(
        number=2,
        label=READINGS["library_card_position"].format(
            position="Present", card=READINGS["card_reversed"].format(card=mid_deal[0])
        ),
    )


def test_searching_a_face_down_cards_name_finds_nothing(mid_deal, page):
    page.refresh()
    page.set_search(mid_deal[1])
    assert labels(page) == []
    page.set_search(mid_deal[0])
    assert labels(page) == ["Mid-deal"]


def test_a_sandbox_lists_its_cards_unnumbered_by_where_they_lie(readings_base, page, minimal_deck):
    first, second = minimal_deck.get_all_cards()[:2]
    unit = card_unit_size()
    keep(
        readings_base,
        "1",
        NOW,
        "Plain",
        cards=[
            # Put down last but lying top left, then one a little lower beside it, then below
            ReadingCard(id=second["id"], x=2 * unit.width(), y=unit.height() * 0.2),
            ReadingCard(id=first["id"], x=0.0, y=3 * unit.height(), position="past"),
            ReadingCard(id=first["id"], x=0.0, y=0.0),
        ],
    )
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    # No numbers and no positions: a sandbox has neither
    assert page.details_pane.card_lines() == [first["name"], second["name"], first["name"]]


def test_spatial_order_reads_rows_top_to_bottom_then_left_to_right():
    unit = QSize(10, 20)
    cards = [
        ReadingCard(id="c", x=0, y=40),
        ReadingCard(id="b", x=20, y=5),
        ReadingCard(id="a", x=0, y=0),
    ]
    assert [card.id for card in spatial_order(cards, unit)] == ["a", "b", "c"]


def test_many_cards_flow_into_columns(readings_base, page, minimal_deck):
    card = minimal_deck.get_all_cards()[0]["id"]
    positions = tuple(Position(id=str(n), label=str(n), x=float(n)) for n in range(10))
    keep(
        readings_base,
        "1",
        NOW,
        "Big",
        spread=Spread(name="Ten", positions=positions),
        cards=[ReadingCard(id=card, position=str(n)) for n in range(10)],
    )
    page.refresh()
    page.list_view.clicked.emit(first_reading(page))

    pane = page.details_pane
    assert pane.card_columns() == 2
    # Still in deal order, down the first column then the second
    assert [line.split(".")[0] for line in pane.card_lines()] == [str(n) for n in range(1, 11)]


def test_the_diagram_is_a_strip_no_taller_than_its_band(readings_base, qtbot, page, minimal_deck):
    card = minimal_deck.get_all_cards()[0]["id"]
    unit = card_unit_size()
    keep(
        readings_base,
        "1",
        NOW,
        "Row",
        spread=PAST_PRESENT_FUTURE,
        cards=[ReadingCard(id=card, x=n * 1.2 * unit.width()) for n in range(3)],
    )
    page.refresh()
    pane = shown_pane(qtbot, page)

    strip = ReadingDetailsPane.DIAGRAM_STRIP
    assert pane.diagram.height() <= strip.height()
    assert pane.diagram.width() <= strip.width()
    # Three cards in a row are wider than they are tall
    assert pane.diagram.width() > pane.diagram.height()


# -- the diagram's ground -------------------------------------------------------------------


@pytest.fixture
def fresh_sources(monkeypatch):
    monkeypatch.setattr(diagram_module, "_sources", {})


def shown_pane(qtbot, page):
    page.resize(900, 600)
    page.show()
    qtbot.waitExposed(page)
    page.list_view.clicked.emit(first_reading(page))
    return page.details_pane


def ground_corner(pane):
    """The diagram's ground just inside its top left, clear of every mark"""
    diagram = pane.diagram
    image = diagram.grab().toImage()
    square = diagram.square()
    ratio = image.devicePixelRatio()
    return image.pixelColor(round((square.x() + 8) * ratio), round((square.y() + 8) * ratio))


def test_the_diagram_draws_the_readings_own_ground(
    qtbot, readings_base, page, minimal_deck, fresh_sources
):
    card = minimal_deck.get_all_cards()[0]
    keep(
        readings_base,
        "1",
        NOW,
        "Grounded",
        cards=[ReadingCard(id=card["id"])],
        ground=Ground(style="solid", color="#336699"),
    )
    page.refresh()
    pane = shown_pane(qtbot, page)

    assert pane.diagram.isVisibleTo(pane)
    assert ground_corner(pane) == QColor("#336699")


def test_a_reading_without_a_ground_draws_the_default(
    qtbot, readings_base, page, minimal_deck, fresh_sources
):
    Ground(style="solid", color="#654321").to_settings()
    card = minimal_deck.get_all_cards()[0]
    keep(readings_base, "1", NOW, "Default", cards=[ReadingCard(id=card["id"])])
    page.refresh()
    pane = shown_pane(qtbot, page)

    assert ground_corner(pane) == QColor("#654321")


def test_an_image_ground_shows_its_fill_until_the_picture_is_decoded(
    qtbot, readings_base, backgrounds_base, page, minimal_deck, fresh_sources
):
    picture = QImage(QSize(64, 32), QImage.Format.Format_RGB32)
    picture.fill(QColor("#c03030"))
    backgrounds_base.mkdir(parents=True)
    assert picture.save(str(backgrounds_base / "felt.png"))
    card = minimal_deck.get_all_cards()[0]
    keep(
        readings_base,
        "1",
        NOW,
        "Pictured",
        cards=[ReadingCard(id=card["id"])],
        # Center keeps its fill in reading.toml, and the pane paints it as crop
        ground=Ground(style="image", image="felt.png", positioning="center", fill="#204060"),
    )
    page.refresh()
    pane = shown_pane(qtbot, page)

    assert ground_corner(pane) == QColor("#204060")
    qtbot.waitUntil(lambda: ground_corner(pane) == QColor("#c03030"))


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
    entries = [
        action.text().split("\t")[0] for action in menu.actions() if not action.isSeparator()
    ]
    assert entries == [
        READINGS["library_open"],
        READINGS["library_rename"],
        READINGS["library_delete"],
    ]

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


def test_the_delete_key_deletes_the_selected_entry_only_from_the_list(qtbot, three, window):
    library, page = readings_view(window)
    with qtbot.waitActive(window):
        window.show()
        window.activateWindow()
    page.select(three[1])

    library.search_field.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is library.search_field)
    assert not library.can_delete()

    page.list_view.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is page.list_view)
    assert library.can_delete()
    library.delete()

    assert not three[1].exists()
    assert page.staged is not None


# -- rows and their menu --------------------------------------------------------------------


def row_for(page, question):
    model = page.list_model
    return next(
        model.index(row, 0)
        for row in range(model.rowCount())
        if not is_section(model.index(row, 0)) and model.index(row, 0).data() == question
    )


def test_a_rows_caption_says_when_and_which_spread(readings_base, page, minimal_deck):
    card = minimal_deck.get_all_cards()[0]["id"]
    keep(
        readings_base,
        "1",
        NOW,
        "Dealt",
        spread=PAST_PRESENT_FUTURE,
        cards=[ReadingCard(id=card, position="past")],
    )
    keep(readings_base, "2", NOW - timedelta(days=3), "Laid out", cards=[ReadingCard(id=card)])
    page.refresh()

    today = local_qdatetime(NOW)
    assert row_for(page, "Dealt").data(SubtitleRole) == READINGS["library_meta"].format(
        when=format_recent(today), spread="Three ways"
    )
    earlier = local_qdatetime(NOW - timedelta(days=3))
    assert row_for(page, "Laid out").data(SubtitleRole) == READINGS["library_meta"].format(
        when=format_recent(earlier), spread=READINGS["sandbox_canvas"]
    )


def test_a_reading_still_being_dealt_says_how_far_and_resumes(mid_deal, page):
    page.refresh()
    index = first_reading(page)
    assert index.data(BadgeRole) == READINGS["library_revealed"].format(turned=2, total=3)

    menu = page.row_menu(index)
    assert menu.actions()[0].text() == READINGS["library_resume"]
    page.list_view.clicked.emit(index)
    assert page.details_pane.open_button.text() == READINGS["library_resume"]


def test_a_finished_reading_has_no_badge_and_opens(three, page):
    index = first_reading(page)
    assert index.data(BadgeRole) is None
    page.list_view.clicked.emit(index)
    assert page.details_pane.open_button.text() == READINGS["library_open"]


def test_a_row_has_a_menu_button(page):
    assert page.row_delegate._menu_button


def test_renaming_a_row_writes_its_question(qtbot, three, window):
    _library, page = readings_view(window)
    index = row_for(page, "Newest")
    page.list_model.setData(index, "  Renamed   now ")

    qtbot.waitUntil(lambda: readings.load(three[1]).question == "Renamed now")
    qtbot.waitUntil(lambda: "Renamed now" in labels(page))


def test_renaming_an_open_reading_goes_through_its_tab(qtbot, three, window):
    tab = window.open_saved_reading(three[1])
    _library, page = readings_view(window)
    page.list_model.setData(row_for(page, "Newest"), "From the Journal")

    qtbot.waitUntil(lambda: readings.load(three[1]).question == "From the Journal")
    assert tab.saved_reading.question() == "From the Journal"
    # The tab's own autosave doesn't write the old Question back
    qtbot.wait(AUTOSAVE_MS + 200)
    assert readings.load(three[1]).question == "From the Journal"


def test_f2_edits_the_selected_rows_question(qtbot, three, window):
    window.show()
    qtbot.waitExposed(window)
    library, page = readings_view(window)
    page.select(three[1])
    assert page.rename_selected()
    assert page.list_view.state() == page.list_view.State.EditingState


# -- expanding the pane ---------------------------------------------------------------------


@pytest.fixture
def long_and_short(readings_base):
    return [
        keep(readings_base, "1", NOW, "Long", note="words\n\n" + "A long line of words. " * 400),
        keep(readings_base, "2", NOW - timedelta(days=1), "Short", note="brief"),
    ]


def expanded_view(qtbot, window, question):
    window.resize(1000, 700)
    with qtbot.waitActive(window):
        window.show()
        window.activateWindow()
    library, page = readings_view(window)
    page.list_view.clicked.emit(row_for(page, question))
    page.list_view.selectionModel().setCurrentIndex(
        row_for(page, question), page.list_view.selectionModel().SelectionFlag.ClearAndSelect
    )
    qtbot.waitUntil(library.details_pane_is_open)
    return library, page, page.details_pane


def test_only_an_entry_too_long_for_the_pane_offers_to_expand(qtbot, long_and_short, window):
    library, page, pane = expanded_view(qtbot, window, "Short")
    qtbot.wait(20)
    assert not pane.expand_button.isVisible()

    page.list_view.clicked.emit(row_for(page, "Long"))
    qtbot.waitUntil(pane.expand_button.isVisible)


def test_expanding_hides_the_list_and_restoring_puts_the_divider_back(
    qtbot, long_and_short, window
):
    library, page, pane = expanded_view(qtbot, window, "Long")
    qtbot.waitUntil(pane.expand_button.isVisible)
    before = library.splitter.sizes()

    pane.expand_button.click()
    assert library.details_pane_is_expanded()
    assert not library.pages.isVisible()
    assert pane.is_expanded()
    assert pane.expand_button.toolTip() == READINGS["library_details_restore"]

    pane.expand_button.click()
    assert not library.details_pane_is_expanded()
    assert library.pages.isVisible()
    assert library.splitter.sizes() == before
    assert pane.expand_button.toolTip() == READINGS["library_details_expand"]


def test_escape_in_the_expanded_pane_gives_the_list_back(qtbot, long_and_short, window):
    library, _page, pane = expanded_view(qtbot, window, "Long")
    qtbot.waitUntil(pane.expand_button.isVisible)
    pane.expand_button.click()

    qtbot.keyClick(pane.note_view, Qt.Key.Key_Escape)
    assert not library.details_pane_is_expanded()


def test_another_view_a_search_or_closing_the_pane_gives_the_list_back(
    qtbot, long_and_short, window
):
    library, _page, pane = expanded_view(qtbot, window, "Long")
    qtbot.waitUntil(pane.expand_button.isVisible)

    pane.expand_button.click()
    library.show_view(LIBRARY_VIEW_NOTES)
    assert not library.details_pane_is_expanded()
    assert library.pages.isVisible()

    library.show_view(LIBRARY_VIEW_READINGS)
    pane.expand_button.click()
    library.search_field.setText("Long")
    assert not library.details_pane_is_expanded()

    pane.expand_button.click()
    library.toggle_details_pane()
    assert not library.details_pane_is_expanded()
    assert library.pages.isVisible()


# -- live refresh ---------------------------------------------------------------------------


def test_save_as_reading_adds_a_row_without_reopening_the_library(window, minimal_deck):
    _library, page = readings_view(window)
    assert labels(page) == []

    canvas = window.new_canvas_tab()
    canvas.add_specific_card(minimal_deck.get_all_cards()[0], card_deck=minimal_deck)
    window.update_save_action()
    window.save_action.trigger()

    assert [first_reading(page).data(ReadingPathRole)] == [canvas.reading_path]
