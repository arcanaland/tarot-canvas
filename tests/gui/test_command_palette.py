from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from tarot_canvas.ui import command_palette
from tarot_canvas.ui.command_palette import THUMBNAIL_SIZE, CommandPalette
from tarot_canvas.ui.library.cover_cache import CoverCache
from tests.conftest import MINIMAL_DECK_PATH

ART = MINIMAL_DECK_PATH / "h750" / "major_arcana"


@pytest.fixture(autouse=True)
def four_cards(stub_deck_manager):
    """Three majors, one without art, and a minor that "the" does not match"""
    cards = [
        {"name": "The Fool", "type": "major_arcana", "image": str(ART / "00.png")},
        {"name": "The Magician", "type": "major_arcana", "image": str(ART / "01.png")},
        {"name": "The High Priestess", "type": "major_arcana", "image": None},
        {"name": "Ace of Cups", "type": "minor_arcana", "suit": "cups", "rank": "ace"},
    ]
    deck = SimpleNamespace(_cards=cards, get_name=lambda: "Fixture")
    stub_deck_manager.get_reference_deck = lambda: deck
    return cards


@pytest.fixture
def decodes(monkeypatch):
    """Every image the palette decodes, through a cache of its own"""
    decoded = []
    original = CoverCache._decode

    def counting(path, well_size, device_pixel_ratio):
        decoded.append(path)
        return original(path, well_size, device_pixel_ratio)

    monkeypatch.setattr(CoverCache, "_decode", staticmethod(counting))
    monkeypatch.setattr(command_palette, "_THUMBNAILS", CoverCache())
    return decoded


@pytest.fixture
def palette(qtbot, decodes):
    widget = CommandPalette()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget.activateWindow()
    widget.search_input.setFocus()
    return widget


def visible_names(palette):
    return [
        palette.results_list.item(row).data(Qt.ItemDataRole.UserRole)[0]["name"]
        for row in palette.visible_rows()
    ]


def current_name(palette):
    return palette.results_list.currentItem().data(Qt.ItemDataRole.UserRole)[0]["name"]


def test_thumbnails_are_decoded_at_display_size(palette):
    labels = [
        palette.results_list.itemWidget(palette.results_list.item(row)).findChildren(
            command_palette.QLabel
        )[0]
        for row in range(palette.results_list.count())
    ]
    pixmaps = [label.pixmap() for label in labels if not label.pixmap().isNull()]

    assert pixmaps
    for pixmap in pixmaps:
        assert pixmap.height() / pixmap.devicePixelRatio() <= THUMBNAIL_SIZE.height()
        assert pixmap.width() / pixmap.devicePixelRatio() <= THUMBNAIL_SIZE.width()


def test_reopening_the_palette_decodes_nothing(qtbot, decodes):
    first = CommandPalette()
    qtbot.addWidget(first)
    after_first = len(decodes)

    second = CommandPalette()
    qtbot.addWidget(second)

    assert after_first > 0
    assert len(decodes) == after_first


def test_filtering_hides_rows_instead_of_rebuilding_them(palette, decodes):
    count = palette.results_list.count()
    widgets = [
        palette.results_list.itemWidget(palette.results_list.item(row)) for row in range(count)
    ]
    decoded = len(decodes)

    palette.search_input.setText("fool")
    assert visible_names(palette) == ["The Fool"]
    assert current_name(palette) == "The Fool"

    palette.search_input.setText("")
    assert palette.results_list.count() == count
    assert len(palette.visible_rows()) == count
    assert [
        palette.results_list.itemWidget(palette.results_list.item(row)) for row in range(count)
    ] == widgets
    assert len(decodes) == decoded


def test_up_and_down_skip_hidden_rows_and_wrap(qtbot, palette):
    palette.search_input.setText("the")
    rows = palette.visible_rows()
    assert 1 < len(rows) < palette.results_list.count()

    for _ in rows:
        qtbot.keyClick(palette.search_input, Qt.Key.Key_Down)
        assert palette.results_list.currentRow() in rows
    assert palette.results_list.currentRow() == rows[0]

    qtbot.keyClick(palette.search_input, Qt.Key.Key_Up)
    assert palette.results_list.currentRow() == rows[-1]


def test_enter_with_nothing_visible_selects_nothing(qtbot, palette):
    selected = []
    palette.card_selected.connect(lambda card, deck: selected.append(card))

    palette.search_input.setText("no card is called this")
    assert palette.visible_rows() == []
    qtbot.keyClick(palette.search_input, Qt.Key.Key_Return)

    assert selected == []


def test_a_card_without_art_still_gets_a_row(palette, four_cards):
    assert visible_names(palette) == [card["name"] for card in four_cards]


def test_the_best_match_is_listed_and_selected_first(palette):
    # "a" starts Ace of Cups' name, but only matches the majors through "arcana"
    palette.search_input.setText("a")
    assert visible_names(palette)[0] == "Ace of Cups"
    assert current_name(palette) == "Ace of Cups"

    palette.search_input.setText("3oC")
    assert visible_names(palette) == []

    palette.search_input.setText("AoC")
    assert visible_names(palette) == ["Ace of Cups"]


def test_clearing_the_search_restores_deck_order(palette, four_cards):
    palette.search_input.setText("a")
    palette.search_input.setText("")
    assert visible_names(palette) == [card["name"] for card in four_cards]
