"""A dealt spread is kept as a reading, written as it is turned, and reopens where it stopped."""

from dataclasses import replace

import pytest
from PyQt6.QtWidgets import QMessageBox

from tarot_canvas.models import readings, spreads
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.ground import Ground
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.settings import (
    MOTION_LEVEL_KEY,
    get_readings_reversals,
    get_settings,
    set_readings_reversals,
)
from tarot_canvas.ui.canvas.placement import Phase
from tarot_canvas.ui.canvas.reading_card import is_face_down
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
    assert [card.id for card in reading.cards] == [item.card_data["id"] for item in order]
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


# -- reopening


def test_a_reading_left_mid_turn_reopens_dealt_where_it_stopped(window, readings_base, qtbot):
    tab = dealt(window)
    tab.pane.question_edit.setText("Where was I?")
    path = tab.reading_path
    ids = [item.card_data["id"] for item in tab.turn_order()]
    tab.turn_next()
    close(window, tab)
    mtime = (path / readings.READING_FILE).stat().st_mtime_ns

    reopened = window.open_saved_reading(path)

    assert isinstance(reopened, ReadingTab)
    assert reopened.reading_path == path
    assert reopened.phase is Phase.DEALT
    order = reopened.turn_order()
    assert [item.card_data["id"] for item in order] == ids
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
