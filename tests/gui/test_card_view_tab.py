import shutil

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QPixmap

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab, device_pixel_fit
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture
def big_image_deck(tmp_path):
    """The minimal deck, with card images at a realistic size.

    The checked-in fixture images are 1x1, which cannot exercise any scaling.
    """
    deck_path = tmp_path / "deck"
    shutil.copytree(MINIMAL_DECK_PATH, deck_path)

    pixmap = QPixmap(600, 900)
    pixmap.fill(QColor("steelblue"))
    for image in deck_path.rglob("*.png"):
        pixmap.save(str(image))

    return TarotDeck(str(deck_path))


def make_tab(qtbot, deck, width, height, deck_count=1, stub=None):
    if stub is not None:
        stub.get_all_decks = lambda: [deck] * deck_count
        stub.get_reference_deck = lambda: deck

    card = next(c for c in deck.get_all_cards() if c.get("image"))
    tab = CardViewTab(card=card, deck=deck)
    qtbot.addWidget(tab)
    tab.resize(width, height)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


@pytest.mark.parametrize("width", [1600, 1000, 700, 500])
def test_image_pane_never_clips_its_contents(qtbot, big_image_deck, stub_deck_manager, width):
    """The card pane must shrink with the window instead of overflowing it."""
    tab = make_tab(qtbot, big_image_deck, width, 900, deck_count=2, stub=stub_deck_manager)

    scroll_area = tab.scroll_area
    assert scroll_area.horizontalScrollBar().maximum() == 0
    assert scroll_area.widget().width() <= scroll_area.viewport().width()


def test_card_is_scaled_to_fit_the_visible_pane(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 900, 900, deck_count=2, stub=stub_deck_manager)

    viewport = tab.scroll_area.viewport()
    pixmap = tab.image_label.pixmap()
    assert pixmap.width() <= viewport.width()
    assert pixmap.height() <= viewport.height()
    # and the label is actually tall enough to draw it
    assert tab.image_label.height() >= pixmap.height()


def test_card_fills_a_wide_pane_without_waiting_for_a_resize(qtbot, big_image_deck):
    """The first scale must use settled geometry, not the pre-layout size."""
    tab = make_tab(qtbot, big_image_deck, 1600, 1200)

    viewport = tab.scroll_area.viewport()
    pixmap = tab.image_label.pixmap()
    assert pixmap.width() > viewport.width() * 0.8


def test_deck_switcher_does_not_pin_the_pane_wide(qtbot, big_image_deck, stub_deck_manager):
    """A long deck name must elide rather than force a minimum width on the pane."""
    tab = make_tab(qtbot, big_image_deck, 700, 900, deck_count=2, stub=stub_deck_manager)

    tab.deck_switcher.deck_combo.addItem("A Deck With An Extravagantly Long Name " * 3)
    assert tab.deck_switcher.minimumSizeHint().width() < CardViewTab.MIN_IMAGE_PANE_WIDTH


@pytest.mark.parametrize("dpr", [1.0, 1.5, 2.0])
def test_card_is_rendered_at_full_device_resolution(dpr):
    """A scaled display must get dpr times as many real pixels, not the logical size."""
    source = QSize(683, 1200)
    width, height = device_pixel_fit(source, 300, 600, dpr)

    # fills the box: 300x600 logical is width-bound for a 683x1200 card
    assert width == pytest.approx(300 * dpr, abs=1)
    assert width / height == pytest.approx(source.width() / source.height(), rel=0.01)
    # and laying it out at its own dpr puts it back inside the pane
    assert width / dpr <= 300
    assert height / dpr <= 600


def test_card_is_never_interpolated_past_its_source_resolution():
    """A card smaller than the pane stays 1:1 rather than being blown up."""
    source = QSize(305, 527)
    assert device_pixel_fit(source, 1200, 2000, 2.0) == (305, 527)
