"""The decan board spike: placement by source, the sun, and a read-only tab"""

from datetime import UTC, datetime
from itertools import pairwise
from types import SimpleNamespace

import pytest

from tarot_canvas.models.esoterica import Entry, SourceReading
from tarot_canvas.ui.canvas import DraggableCardItem
from tarot_canvas.ui.tabs import board_tab
from tarot_canvas.ui.tabs.board_tab import (
    SIGNS,
    SOURCE_NAME,
    BoardTab,
    decan_dates,
    decan_of,
    decan_placement,
    parse_astrology,
    parse_zodiac,
    sun_longitude,
)


def noon(day):
    return datetime.fromisoformat(day).replace(hour=12, tzinfo=UTC)


class FakeManager:
    """Reads correspondences from a dict of {card id: {key: value}}"""

    def __init__(self, cards, name=SOURCE_NAME):
        self.cards = cards
        self.name = name

    def read_card(self, card_id, deck=None):
        values = self.cards.get(card_id)
        if values is None:
            return []
        entries = tuple(Entry("correspondences", key, None, value) for key, value in values.items())
        return [SourceReading(self.name, None, entries, ())]


def card(card_id, rank=None):
    return SimpleNamespace(canonical_id=card_id, rank_key=rank, display_name=card_id)


def deck(*cards):
    return SimpleNamespace(cards=cards, metadata=SimpleNamespace(name="deck"))


def test_astrology_is_planet_in_sign():
    assert parse_astrology("mars in aries") == ("mars", "aries")
    assert parse_astrology("the sun in Leo") == ("sun", "leo")
    assert parse_astrology("aries, leo, sagittarius") is None
    assert parse_astrology(None) is None


def test_an_either_or_zodiac_takes_the_first_named_and_says_so():
    assert parse_zodiac("aries") == ("aries", False)
    assert parse_zodiac("leo or libra") == ("leo", True)
    assert parse_zodiac("libra or leo") == ("libra", True)


@pytest.mark.parametrize(
    ("day", "sign", "slot"),
    [("2026-11-23", "sagittarius", 0), ("2026-03-21", "aries", 0), ("2026-02-25", "pisces", 0)],
)
def test_the_sun_marks_the_decan_of_the_day(day, sign, slot):
    decan = decan_of(sun_longitude(noon(day)))
    assert (SIGNS[decan // 3], decan % 3) == (sign, slot)


def test_the_decan_dates_run_a_year_from_the_equinox_without_gaps():
    dates = decan_dates(noon("2026-11-23"))
    assert len(dates) == 36
    assert dates[0][0].isoformat() == "2026-03-20"
    for (_, last), (first, _) in pairwise(dates):
        assert (first - last).days == 1


def test_a_pip_goes_where_the_source_puts_it_in_rank_order():
    cards = (
        card("w4", "four"),
        card("w2", "two"),
        card("w3", "three"),
        card("strength"),
        card("ace", "ace"),
    )
    manager = FakeManager(
        {
            "w2": {"astrology": "mars in aries"},
            "w3": {"astrology": "sun in aries"},
            "w4": {"astrology": "venus in aries"},
            "strength": {"zodiac": "leo or libra"},
            "ace": {"astrology": "aries, leo, sagittarius"},
        }
    )

    placement = decan_placement(deck(*cards), manager)

    aries, leo = placement.signs[0], placement.signs[4]
    assert [(c.canonical_id, planet) for c, planet in aries.pips] == [
        ("w2", "mars"),
        ("w3", "sun"),
        ("w4", "venus"),
    ]
    assert (leo.major.canonical_id, leo.ambiguous) == ("strength", True)
    assert [c.canonical_id for c in placement.unplaced] == ["ace"]


def test_another_source_places_nothing():
    manager = FakeManager({"w2": {"astrology": "mars in aries"}}, name="Someone Else")

    placement = decan_placement(deck(card("w2", "two")), manager)

    assert [c.canonical_id for c in placement.unplaced] == ["w2"]


@pytest.fixture
def tab(qtbot, stub_deck_library, monkeypatch):
    manager = FakeManager({"major_arcana.01": {"zodiac": "leo or libra"}})
    monkeypatch.setattr(board_tab, "get_esoterica_manager", lambda: manager)
    tab = BoardTab()
    qtbot.addWidget(tab)
    tab.resize(1000, 700)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def items(tab):
    return {item.card_data.canonical_id: item for item in tab.cards()}


def test_the_board_holds_every_card_and_none_can_be_moved_or_deleted(tab):
    cards = items(tab)
    assert set(cards) == {"major_arcana.00", "major_arcana.01"}
    for item in cards.values():
        assert not item.flags() & DraggableCardItem.GraphicsItemFlag.ItemIsMovable

    tab.select_all()
    tab.delete()

    assert set(items(tab)) == {"major_arcana.00", "major_arcana.01"}


@pytest.mark.parametrize("layout", ["wheel", "strip", "table"])
def test_every_layout_keeps_every_card_and_a_sign_selects_its_own(tab, layout):
    tab.board_layout = layout
    tab.relayout()

    tab.select_sign("leo")

    assert len(tab.cards()) == 2
    assert [item.card_data.canonical_id for item in tab.selected_cards()] == ["major_arcana.01"]


def test_hiding_the_unplaced_takes_them_off_the_board(tab):
    tab.show_unplaced = False
    tab.relayout()

    assert set(items(tab)) == {"major_arcana.01"}


def test_the_palette_command_opens_a_board(qtbot, stub_deck_library, monkeypatch):
    from tarot_canvas.ui import commands
    from tarot_canvas.ui.main_window import MainWindow

    monkeypatch.setattr(board_tab, "get_esoterica_manager", lambda: FakeManager({}))
    window = MainWindow()
    qtbot.addWidget(window)

    action = next(a for a in window.actions() if a.objectName() == "window.new_decan_board")
    action.trigger()

    assert isinstance(window.tab_widget.currentWidget(), BoardTab)
    assert commands.by_id("window.new_decan_board").text
