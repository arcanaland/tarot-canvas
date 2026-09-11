import shutil

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.tabs.card_view.card_bar import DeckBar
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


def test_the_bars_do_not_pin_the_pane_wide(qtbot, big_image_deck, stub_deck_manager):
    """A long deck name must elide rather than force a minimum width on the pane."""
    big_image_deck._metadata["deck"]["name"] = "A Deck With An Extravagantly Long Name " * 3
    tab = make_tab(qtbot, big_image_deck, 700, 900, deck_count=2, stub=stub_deck_manager)

    button = tab.deck_bar.deck_button
    assert button.width() <= DeckBar.MAX_BUTTON_WIDTH
    assert button.text().endswith("…")
    assert tab.deck_bar.minimumSizeHint().width() < CardViewTab.MIN_IMAGE_PANE_WIDTH
    assert tab.card_bar.minimumSizeHint().width() < CardViewTab.MIN_IMAGE_PANE_WIDTH


def test_the_deck_name_is_not_squeezed(qtbot, big_image_deck, stub_deck_manager):
    big_image_deck._metadata["deck"]["name"] = "Rider-Waite-Smith"
    tab = make_tab(qtbot, big_image_deck, 700, 900, deck_count=2, stub=stub_deck_manager)
    button = tab.deck_bar.deck_button

    for width in (280, 400, 900):
        tab.image_container.setFixedWidth(width)
        qtbot.waitUntil(lambda w=width: tab.deck_bar.width() <= w)
        assert button.text() == "Rider-Waite-Smith", width

    # squeezed below the name it elides, and given room back it grows back
    tab.image_container.setFixedWidth(CardViewTab.MIN_IMAGE_PANE_WIDTH)
    qtbot.waitUntil(lambda: button.text().endswith("…"))
    tab.image_container.setFixedWidth(900)
    qtbot.waitUntil(lambda: button.text() == "Rider-Waite-Smith")



def test_the_card_bar_fits_the_default_windows_pane(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 700, 900)
    bar = tab.card_bar
    tab.image_container.setFixedWidth(280)
    qtbot.waitUntil(lambda: bar.width() <= 280)

    qtbot.waitUntil(lambda: all(bar.widgetForAction(a).isVisible() for a in bar.actions()))


def test_the_deck_is_above_the_card_and_the_verbs_below(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 900, 900, deck_count=2, stub=stub_deck_manager)

    assert tab.deck_bar.geometry().bottom() < tab.image_view.geometry().top()
    assert tab.card_bar.geometry().top() > tab.image_view.geometry().bottom()


def test_one_deck_spends_no_row_on_the_deck(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 900, 900, deck_count=1, stub=stub_deck_manager)

    assert not tab.deck_bar.isVisibleTo(tab)
    assert tab.card_bar.isVisibleTo(tab)
    assert tab.card_bar.copy_action.isEnabled()


def test_two_decks_show_the_deck_bar(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 900, 900, deck_count=2, stub=stub_deck_manager)

    assert tab.deck_bar.isVisibleTo(tab)
    assert len(tab.deck_bar.compatible_decks) == 2


def test_the_deck_picker_is_centred(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 900, 900, deck_count=2, stub=stub_deck_manager)
    bar, button = tab.deck_bar, tab.deck_bar.deck_button

    bar_centre = bar.mapTo(tab, bar.rect().center()).x()
    assert abs(button.mapTo(tab, button.rect().center()).x() - bar_centre) <= 1


def test_a_deck_outside_the_library_is_still_named(qtbot, big_image_deck, stub_deck_manager):
    stub_deck_manager.get_all_decks = list
    tab = make_tab(qtbot, big_image_deck, 900, 900)

    assert tab.deck_bar.deck_button.title() == big_image_deck.get_name()
    assert not tab.deck_bar.isVisibleTo(tab)


def test_no_bar_action_carries_a_shortcut(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 900, 900)
    bar = tab.card_bar
    actions = bar.actions() + bar.zoom_button.menu().actions()

    assert [a.text() for a in actions if not a.shortcut().isEmpty()] == []


def test_the_zoom_button_zooms_and_says_where_it_is(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    view, bar = tab.image_view, tab.card_bar
    fit = view.current_scale()
    assert bar.zoom_button.text() == "Fit"
    assert not bar.fit_action.isEnabled()

    bar.zoom_in_action.trigger()
    assert view.current_scale() > fit
    assert bar.zoom_button.text().endswith("%")
    assert bar.fit_action.isEnabled()

    bar.zoom_out_action.trigger()
    assert view.is_at_fit()
    assert bar.zoom_button.text() == "Fit"

    bar.native_action.trigger()
    assert view.current_scale() == pytest.approx(view.native_scale())
    assert bar.zoom_button.text() == "100%"

    bar.fit_action.trigger()
    assert view.is_at_fit()


def test_the_bar_toggles_the_card_details(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    action = tab.card_bar.info_pane_action
    assert tab.info_pane_is_open()
    assert "Hide" in action.toolTip()

    action.trigger()
    assert not tab.info_pane_is_open()
    assert "Show" in action.toolTip()


def test_copying_from_the_bar_says_so(qtbot, big_image_deck, clipboard):
    from tarot_canvas.ui.card_transfer import CARD_MIME

    tab = make_tab(qtbot, big_image_deck, 1200, 900)

    tab.card_bar.copy_action.trigger()

    assert clipboard.mimeData().hasFormat(CARD_MIME)
    assert tab.toast.isVisible()
    assert tab.toast.text() == f"Copied {tab.card['name']}"


# -- moving through the deck ---------------------------------------------------
# The minimal deck has two cards, major_arcana.00 and .01; make_tab opens the first.


def press(qtbot, tab, key):
    """A QShortcut only fires in the active window; keyPressEvent doesn't care."""
    if not tab.isActiveWindow():
        with qtbot.waitActive(tab):
            tab.activateWindow()
    tab.image_view.setFocus()
    qtbot.keyClick(tab.image_view, key)


def test_arrows_step_through_the_deck(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    assert tab.card["id"] == "major_arcana.00"

    press(qtbot, tab, Qt.Key.Key_Right)
    assert tab.card["id"] == "major_arcana.01"

    press(qtbot, tab, Qt.Key.Key_Right)  # the last card: nothing past it
    assert tab.card["id"] == "major_arcana.01"

    press(qtbot, tab, Qt.Key.Key_Left)
    assert tab.card["id"] == "major_arcana.00"


@pytest.mark.parametrize(
    ("forward", "back"),
    [
        (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp),
        (Qt.Key.Key_Space, Qt.Key.Key_Backspace),
        (Qt.Key.Key_End, Qt.Key.Key_Home),
    ],
)
def test_image_viewer_keys_step_too(qtbot, big_image_deck, forward, back):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)

    press(qtbot, tab, forward)
    assert tab.card["id"] == "major_arcana.01"

    press(qtbot, tab, back)
    assert tab.card["id"] == "major_arcana.00"


def test_arrows_pan_a_zoomed_card_instead(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    view = tab.image_view
    view.zoom_to(view.max_scale())
    before = view.horizontalScrollBar().value()

    press(qtbot, tab, Qt.Key.Key_Right)

    assert tab.card["id"] == "major_arcana.00"
    assert view.horizontalScrollBar().value() != before


def test_stepping_keeps_the_keyboard_on_the_art(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)

    press(qtbot, tab, Qt.Key.Key_Right)
    qtbot.keyClick(tab.image_view, Qt.Key.Key_Left)

    assert tab.card["id"] == "major_arcana.00"
    assert tab.focusWidget() is tab.image_view


def test_d_draws_another_card(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1200, 900)

    press(qtbot, tab, Qt.Key.Key_D)

    assert tab.card["id"] == "major_arcana.01"
    assert tab.tab_name == tab.card["name"]


def test_brackets_step_through_the_decks(qtbot, big_image_deck, minimal_deck, stub_deck_manager):
    stub_deck_manager.get_all_decks = lambda: [big_image_deck, minimal_deck]
    tab = make_tab(qtbot, big_image_deck, 1200, 900)

    press(qtbot, tab, Qt.Key.Key_BracketRight)
    assert tab.deck is minimal_deck
    assert tab.deck_bar.current_index == 1

    press(qtbot, tab, Qt.Key.Key_BracketLeft)
    assert tab.deck is big_image_deck


def test_the_deck_menu_shows_each_decks_art(qtbot, big_image_deck, minimal_deck, stub_deck_manager):
    stub_deck_manager.get_all_decks = lambda: [big_image_deck, minimal_deck]
    tab = make_tab(qtbot, big_image_deck, 1200, 900)
    bar = tab.deck_bar

    bar.deck_menu.aboutToShow.emit()  # filled as it opens, not on every card change
    assert bar.deck_list.count() == 2
    assert bar.deck_list.currentRow() == 0
    assert not bar.deck_list.item(1).icon().isNull()

    bar.deck_list.itemClicked.emit(bar.deck_list.item(1))
    assert tab.deck is minimal_deck
    assert bar.current_index == 1


def test_brackets_do_nothing_with_one_deck(qtbot, big_image_deck, stub_deck_manager):
    tab = make_tab(qtbot, big_image_deck, 1200, 900, deck_count=1, stub=stub_deck_manager)

    press(qtbot, tab, Qt.Key.Key_BracketRight)

    assert tab.deck is big_image_deck


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

    tab.show_card(tab.card, tab.deck)

    assert view.is_at_fit()


def test_a_card_without_an_image(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 800, 900)
    tab.card = dict(tab.card, image=None)
    tab.load_image()

    assert not tab.image_view.has_image()
    assert not tab.image_view.can_pan()
    assert not tab.card_bar.zoom_button.isEnabled()


HINT = QSize(240, 40)


def widened_to_fullscreen(qtbot, tab):
    """Give the image the whole tab, the way fullscreen does."""
    tab.enter_fullscreen()
    qtbot.waitUntil(lambda: tab.image_view.width() > tab.width() * 0.9)
    return tab.image_view


def test_a_card_at_fit_leaves_a_band_to_park_chrome_in(qtbot, big_image_deck):
    """A card is much taller than it is wide, so a landscape pane always has one."""
    view = widened_to_fullscreen(qtbot, make_tab(qtbot, big_image_deck, 1200, 700))
    image = view.image_viewport_rect()

    position = view.clear_band_position(HINT)
    assert position is not None
    assert not QRect(position, HINT).intersects(image)
    # trailing band, and at eye level rather than tucked in a corner
    assert position.x() > image.right()
    assert abs(QRect(position, HINT).center().y() - view.viewport().rect().center().y()) <= 1


def test_no_band_once_the_artwork_fills_the_width(qtbot, big_image_deck):
    view = widened_to_fullscreen(qtbot, make_tab(qtbot, big_image_deck, 1200, 700))
    view.zoom_to(view.max_scale())

    assert view.clear_band_position(HINT) is None


def test_a_pane_too_narrow_for_the_hint_reports_no_band(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 420, 700)

    assert tab.image_view.clear_band_position(HINT) is None


def test_the_hint_ends_up_where_the_settled_layout_says(qtbot, big_image_deck):
    tab = make_tab(qtbot, big_image_deck, 1920, 1080)
    view, toast = tab.image_view, tab.toast

    toast.show_message("foobar")
    tab.enter_fullscreen()
    qtbot.waitUntil(lambda: view.width() > tab.width() * 0.9)

    qtbot.waitUntil(lambda: toast.pos() == view.clear_band_position(toast.size()))
    assert view.clear_band_position(toast.size()) is not None  # a real band
    assert not toast.geometry().intersects(view.image_viewport_rect())
