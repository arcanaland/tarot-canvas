from datetime import datetime, timedelta

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QMessageBox, QPushButton

from tarot_canvas.about import load_about_data
from tarot_canvas.models import readings, spreads
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.models.readings import Reading
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.settings import LIBRARY_VIEW_SPREADS
from tarot_canvas.ui import main_window as main_window_module
from tarot_canvas.ui.library.roles import SubtitleRole
from tarot_canvas.ui.library.spreads.model import spread_title
from tarot_canvas.ui.library.tab import LibraryTab
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.spread_menu import sections
from tarot_canvas.ui.strings import DATES, MAIN_WINDOW
from tarot_canvas.ui.tabs.reading_tab import ReadingTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab
from tarot_canvas.ui.welcome_tab import WelcomeTab, shows_part


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture
def window(qtbot, stub_deck_manager, spreads_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def welcome(window):
    tab = window.tab_widget.widget(0)
    assert isinstance(tab, WelcomeTab)
    return tab


def keep(base, folder, when, question="", spread=None):
    path = base / folder
    readings.save(path, Reading(date=when, question=question, spread=spread))
    return path


def one_card(name="One Card"):
    return Spread(name=name, positions=(Position(id="p1"),))


def keep_spread(path, spread):
    path.mkdir(parents=True)
    spreads.save(path, spread)


def recent_rows(tab):
    model = tab.recent_model
    return [
        (model.index(row, 0).data(), model.index(row, 0).data(SubtitleRole))
        for row in range(model.rowCount())
    ]


def spread_rows(tab):
    return [tab.spreads_list.item(row) for row in range(tab.spreads_list.count())]


NOW = datetime.now().astimezone().replace(microsecond=0)


def test_the_header_describes_the_app(window):
    assert welcome(window).description.text() == load_about_data().summary


def test_the_top_buttons_start_a_reading_a_canvas_and_a_deck(window):
    buttons = welcome(window).findChildren(QPushButton)

    assert [button.text() for button in buttons[:3]] == [
        MAIN_WINDOW["welcome_new_reading"],
        MAIN_WINDOW["welcome_new_canvas"],
        MAIN_WINDOW["welcome_open_deck"],
    ]
    assert buttons[0].menu() is not None


def test_recent_readings_are_newest_first_by_question_else_date(window, readings_base):
    older = NOW - timedelta(days=3)
    keep(readings_base, "older", older)
    keep(readings_base, "newer", NOW, question="Should I?", spread=one_card())

    welcome(window).refresh_readings()

    (first, first_sub), (_, second_sub) = recent_rows(welcome(window))
    assert first == "Should I?"
    assert (first_sub, second_sub) == (DATES["today"], DATES["days_ago"].format(days=3))


def test_a_recent_row_without_a_question_shows_its_date(window, readings_base):
    from tarot_canvas.ui.canvas.saved_canvas import reading_label

    keep(readings_base, "plain", NOW)
    welcome(window).refresh_readings()

    ((title, _),) = recent_rows(welcome(window))
    assert title == reading_label("", NOW)


def test_activating_a_recent_row_opens_that_reading(window, readings_base, qtbot):
    path = keep(readings_base, "kept", NOW, question="Q")
    tab = welcome(window)
    tab.refresh_readings()

    tab.recent_list.activated.emit(tab.recent_model.index(0, 0))

    opened = window.tab_widget.currentWidget()
    assert opened.saved_reading.path == path


def test_a_new_reading_appears_and_the_placeholder_goes(window, readings_base):
    tab = welcome(window)
    assert tab.recent_placeholder.isVisibleTo(tab)

    keep(readings_base, "new", NOW, question="New")
    reading_events().readings_changed.emit()

    assert [title for title, _ in recent_rows(tab)] == ["New"]
    assert not tab.recent_placeholder.isVisibleTo(tab)


def test_the_spreads_are_the_new_reading_menus(window, spreads_base, included_base):
    keep_spread(included_base / "one-card", one_card())
    keep_spread(spreads_base / "mine", one_card("Mine"))
    tab = welcome(window)
    tab.refresh_spreads()

    expected = [spread_title(spread) for rows in sections() for _, spread in rows]
    assert [item.text() for item in spread_rows(tab)] == expected == ["Mine", "One Card"]
    assert all(not item.icon().isNull() for item in spread_rows(tab))
    assert not tab.spreads_placeholder.isVisibleTo(tab)


def test_with_no_spreads_the_placeholder_shows(window):
    tab = welcome(window)
    assert tab.spreads_list.count() == 0
    assert tab.spreads_placeholder.isVisibleTo(tab)


def test_activating_a_spread_starts_a_reading_of_it(window, included_base):
    keep_spread(included_base / "one-card", one_card())
    tab = welcome(window)
    tab.refresh_spreads()

    tab.spreads_list.activated.emit(tab.spreads_list.model().index(0, 0))

    reading = window.tab_widget.currentWidget()
    assert isinstance(reading, ReadingTab)
    assert reading.spread.name == "One Card"


def test_new_spread_and_the_spread_library(window):
    buttons = welcome(window).buttons
    buttons[3].click()
    assert isinstance(window.tab_widget.currentWidget(), SpreadTab)

    window.add_welcome_tab()
    welcome_tab = window.tab_widget.widget(window.tab_widget.count() - 1)
    welcome_tab.buttons[4].click()
    library = window.tab_widget.currentWidget()
    assert isinstance(library, LibraryTab)
    assert library.current_view() == LIBRARY_VIEW_SPREADS


def test_the_help_links_open_the_metainfos_urls(window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        main_window_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )

    for link in welcome(window).help_links:
        link.linkActivated.emit("#")

    about = load_about_data()
    assert opened == [about.faq, about.bugtracker, about.contribute]


def test_contribute_is_the_metainfos():
    assert load_about_data().contribute == "https://github.com/arcanaland/tarot-canvas"


@pytest.mark.parametrize(
    ("visible", "room", "shown"),
    [
        (True, 501, True),
        (True, 500, False),
        (False, 500 + 100 + 20, False),
        (False, 500 + 100 + 21, True),
    ],
)
def test_a_part_gives_way_with_hysteresis(visible, room, shown):
    assert shows_part(visible, room, content=500, part=100, spacing=20) is shown


def shown_at(qtbot, tab, size):
    tab.resize(size)
    qtbot.wait(10)
    tab.update_layout()
    return tab.header.isVisibleTo(tab), tab.help.isVisibleTo(tab)


def test_the_header_and_help_give_way_and_come_back(qtbot, window):
    tab = welcome(window)
    tab.setParent(None)
    qtbot.addWidget(tab)
    tab.show()

    assert shown_at(qtbot, tab, QSize(1600, 1200)) == (True, True)
    assert shown_at(qtbot, tab, QSize(1600, 300))[0] is False
    assert shown_at(qtbot, tab, QSize(1600, 1200))[0] is True
    assert shown_at(qtbot, tab, QSize(500, 1200))[1] is False
    assert shown_at(qtbot, tab, QSize(1600, 1200))[1] is True

    shown_at(qtbot, tab, QSize(200, 200))
    assert tab.verticalScrollBar().maximum() > 0
    assert tab.horizontalScrollBar().maximum() > 0


def test_a_reading_row_shows_its_cards_minimap(window, readings_base):
    from tarot_canvas.models.readings import ReadingCard
    from tarot_canvas.ui.canvas.icons import CanvasIcon

    path = readings_base / "dealt"
    readings.save(
        path,
        Reading(date=NOW, cards=(ReadingCard(id="major_arcana.00"), ReadingCard(id="x", x=300))),
    )
    keep(readings_base, "empty", NOW - timedelta(days=1))
    tab = welcome(window)
    tab.refresh_readings()

    dealt, empty = (tab.recent_model.item(row).icon() for row in range(2))
    assert not isinstance(dealt, CanvasIcon) and not dealt.isNull()
    assert empty.cacheKey() != dealt.cacheKey()


def test_a_reading_mark_is_a_slot_coloured_by_suit_and_face_down_while_unturned():
    from PyQt6.QtCore import QSize

    from tarot_canvas.models.readings import ReadingCard
    from tarot_canvas.ui.canvas.reading_card import FACE_DOWN_MARK
    from tarot_canvas.ui.canvas.tab_icon import reading_marks
    from tarot_canvas.ui.card_colours import card_colour

    reading = Reading(
        date=NOW,
        cards=(
            ReadingCard(id="minor_arcana.cups.two", x=1, y=2, z=3, rotation=90),
            ReadingCard(id="major_arcana.00", turned=False),
        ),
    )

    up, down = reading_marks(reading, QSize(10, 20))

    assert up == (1, 2, 10, 20, 90, card_colour({"type": "minor_arcana", "suit": "cups"}), 3)
    assert up[5] != card_colour({})
    assert down[5] == FACE_DOWN_MARK
    (major,) = reading_marks(
        Reading(date=NOW, cards=(ReadingCard(id="major_arcana.00"),)), QSize(1, 1)
    )
    assert major[5] == card_colour({"type": "major_arcana"}) != card_colour({})


def test_a_first_launch_on_a_small_laptop_shows_the_header(qtbot, window):
    from tarot_canvas.ui.main_window import first_launch_size

    window.resize(first_launch_size(QSize(1366, 720)))
    with qtbot.waitExposed(window):
        window.show()
    qtbot.wait(50)

    assert welcome(window).header.isVisible()
