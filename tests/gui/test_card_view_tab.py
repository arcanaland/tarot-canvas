import shutil

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
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


def double_click(view):
    """Synthesise a left double-click at the center of the image."""
    pos = QPointF(view.viewport().rect().center())
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        pos,
        view.viewport().mapToGlobal(QPoint(int(pos.x()), int(pos.y()))).toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseDoubleClickEvent(event)


def rendered_rect(view):
    """The image's on-screen rectangle, in viewport coordinates.

    Rounded outwards from a float mapping, so compare it with a pixel of slack.
    """
    return view.mapFromScene(view.scene().sceneRect()).boundingRect()


def fits_in_viewport(view):
    viewport = view.viewport().rect()
    return viewport.adjusted(-1, -1, 1, 1).contains(rendered_rect(view))


@pytest.mark.parametrize("width", [1600, 1000, 700, 500])
def test_image_pane_never_clips_its_contents(qtbot, big_image_deck, stub_deck_manager, width):
    """The card pane must shrink with the window instead of overflowing it."""
    tab = make_tab(qtbot, big_image_deck, width, 900, deck_count=2, stub=stub_deck_manager)

    view = tab.image_view
    assert tab.image_container.width() <= tab.width()
    assert fits_in_viewport(view)


def test_card_is_scaled_to_fit_the_visible_pane(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 900, 900, deck_count=2, stub=stub_deck_manager)

    view = tab.image_view
    assert view.is_at_fit()
    assert fits_in_viewport(view)
    assert view.horizontalScrollBar().maximum() == 0
    assert view.verticalScrollBar().maximum() == 0


def test_card_fills_a_wide_pane_without_waiting_for_a_resize(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1600, 1200)

    view = tab.image_view
    image = rendered_rect(view)
    viewport = view.viewport().rect()
    # a 600x900 card in a tall narrow pane is width-bound
    assert image.width() > viewport.width() * 0.9


def test_deck_switcher_does_not_pin_the_pane_wide(qtbot, big_image_deck, stub_deck_manager):
    """A long deck name must elide rather than force a minimum width on the pane."""
    tab = make_tab(qtbot, big_image_deck, 700, 900, deck_count=2, stub=stub_deck_manager)

    tab.deck_switcher.deck_combo.addItem("A Deck With An Extravagantly Long Name " * 3)
    assert tab.deck_switcher.minimumSizeHint().width() < CardViewTab.MIN_IMAGE_PANE_WIDTH


def test_zoom_never_shrinks_the_card_below_the_pane(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    view = tab.image_view

    fit = view.fit_scale()
    for _ in range(10):
        view.zoom_out()

    assert view.current_scale() == pytest.approx(fit)
    assert view.is_at_fit()


def test_zoom_stops_at_four_times_native(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    view = tab.image_view

    for _ in range(40):
        view.zoom_in()

    assert view.current_scale() == pytest.approx(4.0 * view.native_scale())


def test_double_click_toggles_between_fit_and_native(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    view = tab.image_view
    assert view.is_at_fit()

    double_click(view)
    assert view.current_scale() == pytest.approx(view.native_scale())
    assert not view.is_at_fit()

    double_click(view)
    assert view.is_at_fit()


def test_panning_cannot_leave_the_artwork(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    view = tab.image_view
    view.zoom_to(4.0 * view.native_scale())
    assert view.can_pan()

    for _ in range(20):
        view.horizontalScrollBar().setValue(view.horizontalScrollBar().value() - 500)
        view.verticalScrollBar().setValue(view.verticalScrollBar().value() - 500)

    image = rendered_rect(view)
    viewport = view.viewport().rect()
    # panned as far as it goes: the image still covers the viewport
    assert image.adjusted(-1, -1, 1, 1).contains(viewport)


def test_the_pane_refits_when_it_is_resized(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 700, 900)
    view = tab.image_view
    narrow_fit = view.fit_scale()

    tab.resize(1600, 900)
    qtbot.waitUntil(lambda: view.fit_scale() > narrow_fit)

    assert view.is_at_fit()
    assert fits_in_viewport(view)


def test_switching_decks_resets_the_zoom(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 1200, 900, deck_count=2, stub=stub_deck_manager)
    view = tab.image_view
    view.zoom_to(4.0 * view.native_scale())
    assert not view.is_at_fit()

    tab.switch_to_deck(tab.deck, tab.card)

    assert view.is_at_fit()


def test_a_card_without_an_image(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 800, 900)
    tab.card = dict(tab.card, image=None)
    tab.load_image()

    assert not tab.image_view.has_image()
    assert not tab.image_view.can_pan()
