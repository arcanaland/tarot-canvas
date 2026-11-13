"""A saved canvas: Save, the pane, autosave, the label and reopening."""

from datetime import datetime, timedelta, timezone

import pytest
from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from tarot_canvas.models import readings
from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.utils.dates import format_qdatetime


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    """A window left with unsaved work would otherwise wait on a dialog as it closes"""
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture
def window(qtbot, stub_deck_manager, spreads_base, notes_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def with_art(deck):
    return [card for card in deck.get_all_cards() if card.default_image()]


def by_depth(tab):
    return sorted(tab.cards(), key=lambda item: item.zValue())


@pytest.fixture
def two_cards(window, minimal_deck):
    """A canvas holding a card turned 90 and upright, then a reversed one"""
    tab = window.new_canvas_tab()
    first, second = with_art(minimal_deck)[:2]
    turned = tab.add_specific_card(first, card_deck=minimal_deck, is_reversed=False)
    turned.set_orient(90)
    tab.add_specific_card(second, card_deck=minimal_deck, is_reversed=True)
    tab.deselect()
    return tab


def saved(window, tab):
    window.tab_widget.setCurrentWidget(tab)
    window.update_save_action()
    window.save_action.trigger()
    return tab.reading_path


# -- Save as Reading ---------------------------------------------------------------------


def test_save_makes_a_saved_canvas_and_writes_its_reading(window, two_cards, readings_base):
    tab = two_cards

    path = saved(window, tab)

    assert path is not None and path.parent == readings_base
    reading = readings.load(path)
    items = by_depth(tab)
    assert [card.id for card in reading.cards] == [item.card_data.canonical_id for item in items]
    assert [card.reversed for card in reading.cards] == [False, True]
    assert [card.rotation for card in reading.cards] == [90.0, 0.0]
    assert [(card.x, card.y) for card in reading.cards] == [
        (item.pos().x(), item.pos().y()) for item in items
    ]
    assert [card.z for card in reading.cards] == [item.zValue() for item in items]
    assert reading.question == ""
    assert reading.date.tzinfo is not None


def test_once_saved_save_is_disabled_and_the_pane_is_shown(window, two_cards):
    tab = two_cards

    saved(window, tab)

    assert not tab.can_save()
    assert not window.save_action.isEnabled()
    assert not tab.save_reading_action.isEnabled()
    assert tab.saved_reading.pane.isVisibleTo(tab)


def test_a_saved_canvas_names_itself_where_a_spread_reading_names_its_spread(window, two_cards):
    tab = two_cards
    saved(window, tab)

    pane = tab.saved_reading.pane
    assert pane.spread_label.text() == READINGS["sandbox_canvas"]
    assert pane.spread_label.isVisibleTo(pane)


def test_a_scratch_canvas_has_no_pane(window):
    tab = window.new_canvas_tab()

    assert tab.saved_reading is None
    assert tab.can_save()
    assert window.save_action.isEnabled()


def test_file_save_says_what_the_tab_saves(window):
    window.new_canvas_tab()
    window.update_save_action()
    assert window.save_action.text() == READINGS["save_reading"]

    window.new_spread_tab()
    window.update_save_action()
    assert window.save_action.text() == commands.by_id("window.save").text


# -- autosave ----------------------------------------------------------------------------


def test_an_edited_question_is_written_after_a_moment(qtbot, window, two_cards):
    tab = two_cards
    path = saved(window, tab)

    tab.saved_reading.pane.question_edit.setText("Will the move go well?")

    qtbot.waitUntil(
        lambda: readings.load(path).question == "Will the move go well?",
        timeout=AUTOSAVE_MS * 3,
    )


def test_a_flip_is_written(qtbot, window, two_cards):
    tab = two_cards
    path = saved(window, tab)
    first = by_depth(tab)[0]

    first.setSelected(True)
    tab.on_flip_card()

    qtbot.waitUntil(lambda: readings.load(path).cards[0].reversed, timeout=AUTOSAVE_MS * 3)


def test_closing_the_tab_writes_before_it_goes(window, two_cards):
    tab = two_cards
    path = saved(window, tab)

    tab.saved_reading.pane.question_edit.setText("Asked at the last moment")
    window.close_tab(window.tab_widget.indexOf(tab))

    assert readings.load(path).question == "Asked at the last moment"


# -- the Date --------------------------------------------------------------------------


def test_the_date_reads_as_a_fact(window, two_cards):
    tab = two_cards
    path = saved(window, tab)
    pane = tab.saved_reading.pane

    when = QDateTime(readings.load(path).date.astimezone().replace(tzinfo=None))
    assert pane.date_text.text() == format_qdatetime(when)
    assert pane.date_text.isVisibleTo(pane)
    assert not pane.date_edit.isVisibleTo(pane)


@pytest.fixture
def date_pane(qtbot, window, two_cards):
    """A saved canvas's pane, in a window that has focus"""
    window.show()
    window.activateWindow()
    qtbot.waitActive(window)
    saved(window, two_cards)
    return two_cards.saved_reading.pane


def test_activating_the_date_opens_its_editor_with_the_calendar(qtbot, date_pane):
    pane = date_pane

    qtbot.keyClick(pane.date_text, Qt.Key.Key_Space)

    assert pane.date_edit.isVisibleTo(pane)
    assert not pane.date_text.isVisibleTo(pane)
    assert QApplication.activePopupWidget() is pane.date_edit.calendarWidget().window()


def test_a_backdated_reading_shows_and_writes_the_new_date(qtbot, date_pane, two_cards):
    pane = date_pane
    earlier = pane.date_edit.dateTime().addDays(-3)
    pane.date_text.activated.emit()

    # A day picked in the calendar closes it; Return leaves the editor
    pane.date_edit.calendarWidget().clicked.emit(earlier.date())
    pane.date_edit.setFocus()
    qtbot.keyClick(pane.date_edit, Qt.Key.Key_Return)

    assert pane.date_text.isVisibleTo(pane)
    assert not pane.date_edit.isVisibleTo(pane)
    assert pane.date_text.hasFocus()
    assert pane.date_text.text() == format_qdatetime(earlier)
    qtbot.waitUntil(
        lambda: readings.load(two_cards.reading_path).date == earlier.toPyDateTime().astimezone(),
        timeout=AUTOSAVE_MS * 3,
    )


def test_leaving_the_date_editor_closes_it(qtbot, date_pane):
    pane = date_pane
    pane.date_text.activated.emit()
    QApplication.activePopupWidget().close()

    pane.question_edit.setFocus()

    assert pane.date_text.isVisibleTo(pane)
    assert not pane.date_edit.isVisibleTo(pane)


# -- the label ---------------------------------------------------------------------------


def test_the_label_is_the_date_until_there_is_a_question(window, two_cards):
    tab = two_cards
    saved(window, tab)
    index = window.tab_widget.indexOf(tab)
    dated = window.tab_widget.tabText(index)

    assert dated and dated == tab.elided_title(tab.saved_reading.label())

    tab.saved_reading.pane.question_edit.setText("Which way?")

    assert window.tab_widget.tabText(index) == "Which way?"


def test_renaming_a_reading_tab_sets_its_question(window, two_cards, monkeypatch):
    tab = two_cards
    saved(window, tab)
    tab.saved_reading.pane.question_edit.setText("Before")
    offered = []

    def answer(parent, title, prompt, text=""):
        offered.append(text)
        return "After", True

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(answer))
    window.show_tab_rename_dialog(window.tab_widget.indexOf(tab))

    assert offered == ["Before"]
    assert tab.saved_reading.question() == "After"


def test_a_canvas_renamed_by_hand_keeps_its_name_as_the_question(window, two_cards, monkeypatch):
    tab = two_cards
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *_a, **_k: ("Mine", True)))
    window.show_tab_rename_dialog(window.tab_widget.indexOf(tab))

    path = saved(window, tab)

    assert window.tab_widget.tabText(window.tab_widget.indexOf(tab)) == "Mine"
    assert tab.saved_reading.question() == "Mine"
    assert readings.load(path).question == "Mine"


def test_a_canvas_never_renamed_is_saved_with_no_question(window, two_cards):
    path = saved(window, two_cards)

    assert two_cards.saved_reading.question() == ""
    assert readings.load(path).question == ""


# -- reopening ---------------------------------------------------------------------------


def test_a_closed_reading_reopens_as_it_was_and_is_not_rewritten(qtbot, window, two_cards):
    tab = two_cards
    path = saved(window, tab)
    before = [
        (item.card_data.canonical_id, item.pos(), item.zValue(), item.orient, item.is_reversed())
        for item in by_depth(tab)
    ]
    window.close_tab(window.tab_widget.indexOf(tab))
    written = (path / readings.READING_FILE).stat().st_mtime_ns

    reopened = window.open_saved_reading(path)
    qtbot.wait(AUTOSAVE_MS * 2)

    assert reopened is not tab
    assert reopened.reading_path == path
    assert [
        (item.card_data.canonical_id, item.pos(), item.zValue(), item.orient, item.is_reversed())
        for item in by_depth(reopened)
    ] == before
    assert (path / readings.READING_FILE).stat().st_mtime_ns == written


def test_opening_a_reading_twice_raises_its_tab(window, two_cards):
    path = saved(window, two_cards)
    window.new_canvas_tab()

    assert window.open_saved_reading(path) is two_cards
    assert window.tab_widget.currentWidget() is two_cards


def test_a_reading_of_an_unknown_deck_opens_in_the_reference_deck(
    window, minimal_deck, readings_base
):
    path = readings_base / "1700000000"
    card = with_art(minimal_deck)[0]
    when = datetime(2026, 11, 9, 21, 14, tzinfo=timezone(timedelta(hours=-8)))
    readings.save(
        path,
        Reading(
            date=when, deck="No Such Deck", cards=(ReadingCard(id=card.canonical_id, x=10, y=20),)
        ),
    )

    tab = window.open_saved_reading(path)

    (item,) = tab.cards()
    assert item.deck is minimal_deck
    assert (item.pos().x(), item.pos().y()) == (10, 20)


def test_an_unreadable_reading_opens_nothing(window, readings_base):
    path = readings_base / "1700000000"
    path.mkdir(parents=True)
    (path / readings.READING_FILE).write_text("not = [toml", encoding="utf-8")
    count = window.tab_widget.count()

    assert window.open_saved_reading(path) is None
    assert window.tab_widget.count() == count
