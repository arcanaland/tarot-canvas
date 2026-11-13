"""A dealt spread is kept as a reading, written as it is turned, and reopens where it stopped."""

import shutil
from dataclasses import replace

import pytest
from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from tarot_canvas.models import readings, spreads
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.ground import Ground
from tarot_canvas.models.spreads import BUNDLED_SPREADS_PATH, Position, Spread
from tarot_canvas.settings import (
    MOTION_LEVEL_KEY,
    get_readings_reversals,
    get_settings,
    set_readings_reversals,
)
from tarot_canvas.ui.canvas.placement import Phase
from tarot_canvas.ui.canvas.reading_card import is_face_down
from tarot_canvas.ui.canvas.reading_pane import NOTES_MIN_LINES
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS, deck_key, now
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.reading_tab import CARD_Z, NEXT_Z, ReadingTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab
from tests.conftest import write_full_deck

PAST_AUTOSAVE_MS = AUTOSAVE_MS + 500


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture(autouse=True)
def off():
    get_settings().setValue(MOTION_LEVEL_KEY, "Off")


@pytest.fixture
def deck(tmp_path, stub_deck_manager, qapp):
    full = TarotDeck(str(write_full_deck(tmp_path / "full")))
    stub_deck_manager.get_reference_deck = lambda: full
    stub_deck_manager.get_all_decks = lambda: [full]
    return full


@pytest.fixture
def window(qtbot, deck, spreads_base, notes_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def three():
    return Spread(
        name="Three",
        positions=tuple(
            Position(id=f"p{n}", label=f"Place {n}", meaning="", x=n * 1.2, y=0.0)
            for n in range(1, 4)
        ),
    )


def kept(base):
    return readings.scan(base)


def only_reading(base):
    found = kept(base)
    assert len(found) == 1
    return found[0]


def dealt(window, reversals=False, origin="three"):
    tab = window.open_reading_of(three(), origin)
    tab.pane.reversals_check.setChecked(reversals)
    tab.deal()
    return tab


def turned_flags(path):
    return [card.turned for card in readings.load(path).cards]


def close(window, tab):
    assert window.close_tab(window.tab_widget.indexOf(tab))


# -- keeping at the deal


@pytest.mark.parametrize("reversals", [False, True])
def test_dealing_keeps_the_reading_face_down_in_number_order(window, readings_base, reversals):
    tab = dealt(window, reversals)

    path, reading = only_reading(readings_base)
    assert tab.reading_path == path
    assert reading.spread.name == "Three"
    assert reading.spread_from == "three"
    assert reading.reversals is reversals
    assert [card.position for card in reading.cards] == ["p1", "p2", "p3"]
    assert [card.turned for card in reading.cards] == [False, False, False]
    order = tab.turn_order()
    assert [card.id for card in reading.cards] == [item.card_data.canonical_id for item in order]
    assert [card.reversed for card in reading.cards] == [item.drawn_reversed for item in order]
    assert reading.deck == deck_key(order[0].deck)
    assert reading.date.tzinfo is not None and reading.date.microsecond == 0


def test_a_kept_card_lies_where_it_landed(window, readings_base):
    tab = dealt(window)

    _path, reading = only_reading(readings_base)
    for card, item in zip(reading.cards, tab.turn_order(), strict=True):
        slot = tab.placement_of(item).slot
        assert (card.x, card.y, card.rotation) == (item.pos().x(), item.pos().y(), item.orient)
        # At rest, though the next card is raised
        assert card.z == CARD_Z + slot.zValue()
    assert tab.turn_order()[0].zValue() == NEXT_Z


def test_closing_during_setup_keeps_nothing(window, readings_base):
    tab = window.open_reading_of(three(), "three")
    tab.pane.question_edit.setText("Asked, never dealt")

    close(window, tab)

    assert kept(readings_base) == []


def starts(tab):
    started = []
    tab.navigation_requested.connect(lambda action, data: started.append((action, data)))
    tab.start_reading()
    return [data[1] for action, data in started if action == "open_reading_of"]


def test_a_saved_spread_from_the_designer_is_named_by_its_folder(window, spreads_base, qtbot):
    path = spreads_base / "mine"
    path.mkdir(parents=True)
    spreads.save(path, three())
    tab = window.open_spread(path)

    assert starts(tab) == ["mine"]


def test_an_unsaved_or_edited_spread_from_the_designer_names_none(window, qtbot):
    unsaved = SpreadTab(three())
    qtbot.addWidget(unsaved)
    assert starts(unsaved) == [""]

    unsaved.spread_path, unsaved._modified = "somewhere/mine", True
    assert starts(unsaved) == [""]


def test_the_designers_reading_is_kept_with_its_folder(window, spreads_base, readings_base):
    path = spreads_base / "mine"
    path.mkdir(parents=True)
    spreads.save(path, three())
    window.open_spread(path).start_reading()

    window.tab_widget.currentWidget().deal()

    assert only_reading(readings_base)[1].spread_from == "mine"


# -- writing as it is turned


def test_a_turn_is_written_a_moment_later(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path

    tab.turn_next()

    qtbot.waitUntil(lambda: turned_flags(path) == [True, False, False], timeout=PAST_AUTOSAVE_MS)


def test_the_question_is_written(window, readings_base, qtbot):
    tab = dealt(window)

    tab.pane.question_edit.setText("What now?")

    qtbot.waitUntil(
        lambda: readings.load(tab.reading_path).question == "What now?", timeout=PAST_AUTOSAVE_MS
    )


def test_reveal_all_writes_every_card_turned(window, readings_base, qtbot):
    tab = dealt(window)

    tab.turn_all()

    assert tab.phase is Phase.READ
    qtbot.waitUntil(lambda: turned_flags(tab.reading_path) == [True] * 3, timeout=PAST_AUTOSAVE_MS)


def test_closing_at_once_after_a_turn_writes_it(window, readings_base):
    tab = dealt(window)
    path = tab.reading_path

    tab.turn_next()
    close(window, tab)

    assert turned_flags(path) == [True, False, False]


def test_closing_mid_turn_writes_the_turn_and_nothing_after(window, readings_base, qtbot):
    # Hiding a tab settles its motion, which finishes the turn; that must not write later
    get_settings().setValue(MOTION_LEVEL_KEY, "Reactive")
    window.show()
    qtbot.waitExposed(window)
    tab = dealt(window)
    qtbot.waitUntil(tab.can_turn, timeout=3000)
    path = tab.reading_path

    tab.turn_next()
    close(window, tab)
    assert turned_flags(path) == [True, False, False]

    # Deleted at once, from outside or by the Journal, the folder stays gone
    shutil.rmtree(path)
    qtbot.wait(PAST_AUTOSAVE_MS)
    assert not path.exists()


# -- reopening


def test_a_reading_left_mid_turn_reopens_dealt_where_it_stopped(window, readings_base, qtbot):
    tab = dealt(window)
    tab.pane.question_edit.setText("Where was I?")
    path = tab.reading_path
    ids = [item.card_data.canonical_id for item in tab.turn_order()]
    tab.turn_next()
    close(window, tab)
    mtime = (path / readings.READING_FILE).stat().st_mtime_ns

    reopened = window.open_saved_reading(path)

    assert isinstance(reopened, ReadingTab)
    assert reopened.reading_path == path
    assert reopened.phase is Phase.DEALT
    order = reopened.turn_order()
    assert [item.card_data.canonical_id for item in order] == ids
    assert [is_face_down(item) for item in order] == [False, True, True]
    assert reopened.next_card() is order[1]
    assert reopened.placement_of(order[1]).number == 2
    assert reopened.can_turn()
    assert reopened.question() == "Where was I?"
    assert reopened.halo.card is order[1]
    assert reopened.candle.is_still()
    assert not reopened.toolbar.isVisibleTo(reopened)
    qtbot.wait(PAST_AUTOSAVE_MS)
    assert (path / readings.READING_FILE).stat().st_mtime_ns == mtime

    reopened.turn_all()

    assert reopened.phase is Phase.READ
    qtbot.waitUntil(lambda: turned_flags(path) == [True] * 3, timeout=PAST_AUTOSAVE_MS)


def test_a_reopened_reading_keeps_its_own_reversals(window, readings_base, qtbot):
    tab = dealt(window, reversals=True)
    path = tab.reading_path
    close(window, tab)
    set_readings_reversals(False)

    reopened = window.open_saved_reading(path)
    reopened.turn_next()

    assert reopened.dealt_reversals is True
    assert not reopened.pane.reversals_check.isVisibleTo(reopened)
    qtbot.waitUntil(lambda: turned_flags(path)[0], timeout=PAST_AUTOSAVE_MS)
    assert readings.load(path).reversals is True
    assert get_readings_reversals() is False


def test_a_card_its_deck_lacks_leaves_its_position_empty(window, readings_base):
    tab = dealt(window)
    path = tab.reading_path
    close(window, tab)
    reading = readings.load(path)
    lost = replace(reading.cards[1], id="no-such-card")
    readings.save(path, replace(reading, cards=(reading.cards[0], lost, reading.cards[2])))

    reopened = window.open_saved_reading(path)

    assert [p.card is None for p in reopened.placements] == [False, True, False]
    assert reopened.phase is Phase.DEALT
    assert reopened.next_card() is reopened.placements[0].card


def test_a_card_its_deck_lacks_is_written_back_in_its_place(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path
    close(window, tab)
    reading = readings.load(path)
    lost = replace(reading.cards[1], id="no-such-card")
    readings.save(path, replace(reading, cards=(reading.cards[0], lost, reading.cards[2])))

    reopened = window.open_saved_reading(path)
    reopened.turn_next()

    qtbot.waitUntil(lambda: turned_flags(path)[0], timeout=PAST_AUTOSAVE_MS)
    cards = readings.load(path).cards
    assert [card.id for card in cards][1] == "no-such-card"
    assert (cards[1].position, cards[1].turned) == ("p2", False)


def test_a_missing_deck_keeps_its_name_through_a_write(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path
    close(window, tab)
    reading = readings.load(path)
    gone = tuple(replace(card, deck="Uninstalled Deck") for card in reading.cards)
    readings.save(path, replace(reading, deck="Uninstalled Deck", cards=gone))

    # Shown in the reference deck, but written as the deck it names
    reopened = window.open_saved_reading(path)
    reopened.turn_next()

    qtbot.waitUntil(lambda: turned_flags(path)[0], timeout=PAST_AUTOSAVE_MS)
    written = readings.load(path)
    assert written.deck == "Uninstalled Deck"
    assert {card.deck for card in written.cards} == {"Uninstalled Deck"}


def test_with_no_deck_at_all_an_edit_keeps_every_card(
    window, readings_base, qtbot, stub_deck_manager
):
    tab = dealt(window)
    path = tab.reading_path
    ids = [card.id for card in readings.load(path).cards]
    close(window, tab)
    # Before the reference deck's first download, nothing can lay a card out
    stub_deck_manager.get_reference_deck = lambda: None
    stub_deck_manager.get_all_decks = lambda: []

    reopened = window.open_saved_reading(path)
    reopened.pane.question_edit.setText("Still here?")

    qtbot.waitUntil(lambda: readings.load(path).question == "Still here?", timeout=PAST_AUTOSAVE_MS)
    assert [card.id for card in readings.load(path).cards] == ids


def test_a_fully_turned_reading_reopens_read(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path
    tab.turn_all()
    close(window, tab)

    reopened = window.open_saved_reading(path)

    assert isinstance(reopened, ReadingTab)
    assert reopened.phase is Phase.READ
    assert not any(is_face_down(item) for item in reopened.turn_order())
    assert reopened.toolbar.isVisibleTo(reopened)
    assert reopened.next_card() is None


def test_a_dealt_reading_keeps_its_own_ground(window, readings_base):
    tab = dealt(window)
    path = tab.reading_path
    tab.ground = Ground(style="solid", color="#123456")
    tab.saved_reading.write()
    close(window, tab)

    reopened = window.open_saved_reading(path)

    assert readings.load(path).ground == Ground(style="solid", color="#123456")
    assert reopened.ground == Ground(style="solid", color="#123456")


def test_a_plain_canvas_reading_still_opens_as_a_canvas(window, readings_base):
    path = readings_base / "plain"
    readings.save(path, readings.Reading(date=now()))

    reopened = window.open_saved_reading(path)

    assert isinstance(reopened, CanvasTab) and not isinstance(reopened, ReadingTab)


def test_opening_the_same_reading_twice_raises_its_tab(window, readings_base):
    tab = dealt(window)
    path = tab.reading_path

    again = window.open_saved_reading(path)

    assert again is tab
    assert window.tab_widget.currentWidget() is tab


# -- the pane's note


def shown(qtbot, spread, height=700):
    tab = ReadingTab(spread, spread_from="mine")
    qtbot.addWidget(tab)
    tab.resize(1200, height)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def celtic_cross():
    return spreads.load(BUNDLED_SPREADS_PATH / "celtic-cross")


def rows_height(view):
    return sum(view.sizeHintForRow(row) for row in range(view.model().rowCount()))


def settle(qtbot):
    # Let the layouts and the list's fit catch up
    QApplication.processEvents()
    qtbot.wait(50)


def test_the_notes_show_from_the_deal_on(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    assert tab.pane.note is None
    assert not tab.pane.expand_button.isVisible()

    tab.deal()
    settle(qtbot)

    note = tab.pane.note
    assert note.isVisible() and note.editor.isVisible() and note.editor.isEnabled()
    assert not tab.pane.filler.isVisible()


def test_a_note_is_written_beside_the_reading_and_reopens(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path

    qtbot.keyClicks(tab.pane.note.editor, "The tower, again")

    qtbot.waitUntil(
        lambda: any(p.stem.isdigit() for p in path.glob("*.md")), timeout=PAST_AUTOSAVE_MS
    )
    close(window, tab)
    reopened = window.open_saved_reading(path)
    assert reopened.pane.note.editor.toPlainText() == "The tower, again"


def test_a_reading_reopened_read_shows_its_note(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path
    tab.turn_all()
    qtbot.keyClicks(tab.pane.note.editor, "Done")
    close(window, tab)

    reopened = window.open_saved_reading(path)

    assert reopened.phase is Phase.READ
    assert reopened.pane.note.editor.toPlainText() == "Done"


def test_the_editor_has_four_lines_at_least(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    tab.deal()

    editor = tab.pane.note.editor
    assert editor.minimumHeight() >= editor.fontMetrics().lineSpacing() * NOTES_MIN_LINES


# -- the list gives way


def test_a_long_spread_caps_its_list_and_the_pane_does_not_scroll(qtbot, deck, readings_base):
    tab = shown(qtbot, celtic_cross(), height=600)
    tab.deal()
    settle(qtbot)

    pane = tab.pane
    editor = pane.note.editor
    assert editor.height() >= editor.minimumHeight()
    assert pane.list_view.height() < rows_height(pane.list_view)
    assert pane.list_view.verticalScrollBar().maximum() > 0
    assert not pane.verticalScrollBar().isVisible()


def test_a_short_spread_shows_every_row(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    tab.deal()
    settle(qtbot)

    view = tab.pane.list_view
    assert view.height() >= rows_height(view)
    assert view.verticalScrollBar().maximum() == 0
    assert not tab.pane.verticalScrollBar().isVisible()


def test_turning_keeps_the_next_row_in_the_capped_list(qtbot, deck, readings_base):
    tab = shown(qtbot, celtic_cross(), height=600)
    tab.deal()
    for _ in range(7):
        tab.turn_next()
    settle(qtbot)

    view = tab.pane.list_view
    row = tab.placements.index(tab.placement_of(tab.next_card()))
    rect = view.visualRect(tab.positions.index(row))
    assert view.viewport().rect().contains(rect)


# -- ⤢


def overflowed(qtbot, tab):
    tab.pane.note.editor.setPlainText("\n".join(f"line {n}" for n in range(60)))
    qtbot.waitUntil(tab.pane.expand_button.isVisible, timeout=2000)


def test_an_empty_note_has_no_expand_button(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    tab.deal()
    settle(qtbot)

    assert not tab.pane.expand_button.isVisible()


def test_expanding_hides_the_facts_and_the_list_and_a_turn_gives_them_back(
    qtbot, deck, readings_base
):
    tab = shown(qtbot, three())
    tab.deal()
    overflowed(qtbot, tab)
    pane = tab.pane

    pane.expand_button.click()

    assert pane.notes_expanded()
    assert not pane.facts.isVisible() and not pane.list_view.isVisible()
    assert pane.question_edit.isVisible()
    assert pane.expand_button.isVisible()

    tab.turn_next()

    assert not pane.notes_expanded()
    assert pane.facts.isVisible() and pane.list_view.isVisible()


def test_choosing_a_card_on_the_canvas_gives_the_list_back(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    tab.deal()
    tab.turn_next()
    overflowed(qtbot, tab)
    pane = tab.pane
    pane.expand_button.click()
    assert pane.notes_expanded()

    tab.turn_order()[0].setSelected(True)

    assert not pane.notes_expanded()
    assert pane.list_view.isVisible()


def test_restoring_by_the_button_gives_the_list_back(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    tab.deal()
    overflowed(qtbot, tab)
    pane = tab.pane
    pane.expand_button.click()

    pane.expand_button.click()

    assert not pane.notes_expanded()
    assert pane.list_view.isVisible() and pane.facts.isVisible()


# -- the Date line


def test_the_date_is_text_until_activated(qtbot, deck, readings_base):
    tab = shown(qtbot, three())
    pane = tab.pane
    assert not pane.date_text.isVisible()

    tab.deal()

    assert pane.date_text.isVisible() and not pane.date_edit.isVisible()
    pane.date_line.edit()
    assert pane.date_edit.isVisible() and not pane.date_text.isVisible()
    QApplication.activePopupWidget().close()


def test_a_backdated_reading_is_written_and_kept_through_a_turn(window, readings_base, qtbot):
    tab = dealt(window)
    path = tab.reading_path
    earlier = QDateTime(tab.dealt_at).addDays(-3)

    tab.pane.date_edit.setDateTime(earlier)
    tab.turn_next()

    assert tab.pane.date_edit.dateTime() == earlier
    wanted = earlier.toPyDateTime().astimezone()
    qtbot.waitUntil(lambda: readings.load(path).date == wanted, timeout=PAST_AUTOSAVE_MS)


@pytest.mark.parametrize("clicks", [1, 2])
def test_the_expand_button_leaves_the_typing_in_the_note(qtbot, deck, readings_base, clicks):
    tab = shown(qtbot, three())
    tab.deal()
    overflowed(qtbot, tab)
    editor = tab.pane.note.editor
    tab.view.setFocus()
    cards = len(tab.cards())

    for _ in range(clicks):
        qtbot.mouseClick(tab.pane.expand_button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(QApplication.focusWidget(), "dd")

    assert editor.hasFocus()
    assert editor.toPlainText().startswith("dd")
    assert len(tab.cards()) == cards
