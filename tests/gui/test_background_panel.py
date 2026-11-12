"""A canvas's own ground: the Background panel, its two ways in, and a reading keeping it."""

import logging

import pytest
from PyQt6.QtCore import QPoint, QPointF, QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox

from tarot_canvas.models import readings
from tarot_canvas.models.ground import Ground
from tarot_canvas.settings import BACKGROUND_COLOR_KEY, BACKGROUND_STYLE_KEY, get_settings
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab
from tests.gui.test_arc_popover import add_cards, drag
from tests.gui.test_canvas_tab import menu_layout
from tests.gui.test_image_background import write_image

SOLID = "#123456"
COMMAND = commands.by_id("window.canvas_background")


def make_tab(qtbot, kind=CanvasTab):
    tab = kind()
    qtbot.addWidget(tab)
    tab.resize(1000, 700)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


@pytest.fixture
def tab(qtbot):
    tab = make_tab(qtbot)
    yield tab
    for panel in (tab.background_panel, tab.arc_popover):
        if panel is not None:
            panel.close()


def brush_colour(tab):
    return tab.view.backgroundBrush().color().name()


def choose_solid(panel, colour=SOLID):
    panel.own.setChecked(True)
    form = panel.form
    form.bg_combo.setCurrentIndex(form.bg_combo.findData("solid"))
    form.set_bg_color(QColor(colour))


def own_solid(colour=SOLID):
    return Ground(style="solid", color=colour)


# -- the panel ---------------------------------------------------------------------------


def test_on_a_following_tab_it_opens_on_the_default_with_the_rows_off(tab):
    panel = tab.edit_background()

    assert panel.isVisible()
    assert panel.follow.isChecked()
    assert not panel.form.isEnabled()
    assert not panel.form.bg_combo.isEnabled()
    assert panel.form.ground() == Ground.from_settings()


def test_on_a_tab_with_its_own_it_opens_on_this_canvas_showing_it(tab):
    tab.ground = own_solid()
    panel = tab.edit_background()

    assert panel.own.isChecked()
    assert panel.form.isEnabled()
    assert panel.form.ground() == own_solid()


def test_each_change_shows_on_the_canvas_before_apply(tab):
    panel = tab.edit_background()
    choose_solid(panel)

    assert tab.ground == own_solid()
    assert brush_colour(tab) == SOLID
    assert not panel.finished


@pytest.mark.parametrize("how", ["cancel", "esc", "esc_on_canvas", "switch_tabs"])
def test_cancel_esc_and_switching_tabs_put_the_ground_back(tab, qtbot, how):
    before = brush_colour(tab)
    panel = tab.edit_background()
    choose_solid(panel)

    if how == "cancel":
        panel.cancel()
    elif how == "esc":
        qtbot.keyClick(panel.form.bg_combo, Qt.Key.Key_Escape)
    elif how == "esc_on_canvas":
        tab.view.setFocus()
        tab.commands["canvas.cancel"].trigger()
    else:
        tab.hide()

    assert panel.finished
    assert tab.ground is None
    assert brush_colour(tab) == before


def test_cancel_puts_back_a_ground_of_its_own(tab):
    tab.ground = own_solid("#654321")
    tab.apply_ground()
    panel = tab.edit_background()
    panel.follow.setChecked(True)
    assert tab.ground is None

    panel.cancel()

    assert tab.ground == own_solid("#654321")
    assert brush_colour(tab) == "#654321"


def test_apply_keeps_the_ground(tab):
    panel = tab.edit_background()
    choose_solid(panel)
    panel.apply()

    assert not panel.isVisible()
    assert tab.ground == own_solid()
    assert brush_colour(tab) == SOLID


def test_apply_on_the_default_leaves_the_tab_following(tab):
    tab.ground = own_solid()
    panel = tab.edit_background()
    panel.follow.setChecked(True)
    panel.apply()
    assert tab.ground is None


def test_the_panel_sits_in_a_corner_clear_of_the_cards(tab):
    viewport = tab.view.viewport().rect()
    near = tab.view.mapToScene(QPoint(viewport.right() - 150, viewport.top() + 150))
    cards = add_cards(tab, 3, apart=10)
    for i, card in enumerate(cards):
        card.setPos(near + QPointF(i * 20 - 70, -80))

    panel = tab.edit_background()

    assert panel.corner != "top_right"
    shown = tab.view.mapFromScene(panel.covered_rect()).boundingRect()
    geometry = panel.geometry().translated(-tab.view.viewport().mapTo(tab.canvas_area, QPoint()))
    assert not geometry.intersects(shown)


def test_on_an_empty_canvas_it_sits_top_right(tab):
    assert tab.edit_background().corner == "top_right"


def test_a_card_can_be_dragged_while_it_is_open(tab):
    (card,) = add_cards(tab, 1)
    tab.scene.clearSelection()
    panel = tab.edit_background()
    before = QPointF(card.pos())

    on_card = tab.view.mapFromScene(card.sceneBoundingRect().center())
    drag(tab.view, on_card, on_card + QPoint(-60, 40))

    assert card.pos() != before
    assert not panel.finished
    assert not tab.arranging


def test_opening_arrange_on_arc_cancels_it(tab):
    add_cards(tab, 3)
    panel = tab.edit_background()
    choose_solid(panel)

    tab.open_arc_popover()

    assert panel.finished
    assert tab.ground is None
    assert tab.arc_is_open()


def test_opening_it_cancels_arrange_on_arc(tab):
    cards = add_cards(tab, 3)
    before = [QPointF(card.pos()) for card in cards]
    popover = tab.open_arc_popover()

    tab.edit_background()

    assert popover.finished
    assert [card.pos() for card in cards] == before
    assert not tab.arranging
    assert tab.background_is_open()


def test_it_lists_the_images_already_copied_in(tab, backgrounds_base):
    write_image(backgrounds_base, "wood.png")
    write_image(backgrounds_base, "felt.png")

    panel = tab.edit_background()

    assert panel.form.background_grid.names() == ["felt.png", "wood.png"]


def test_an_image_ground_of_its_own_opens_selected(tab, backgrounds_base):
    write_image(backgrounds_base, "wood.png")
    tab.ground = Ground(style="image", image="wood.png")
    panel = tab.edit_background()
    assert panel.form.background_grid.selected_name() == "wood.png"


def test_its_tiles_offer_no_remove(tab, backgrounds_base):
    write_image(backgrounds_base, "wood.png")
    panel = tab.edit_background()
    grid = panel.form.background_grid
    index = grid.model().index(0, 0)

    assert grid.delegate.action_rects(grid.visualRect(index), False) == []
    assert not grid.isWrapping()


def test_set_as_default_is_a_button_beside_apply_and_cancel(tab):
    panel = tab.edit_background()
    assert panel.default_button in panel.buttons.buttons()
    assert not panel.default_button.isFlat()


@pytest.mark.parametrize("via", ["image", "solid"])
def test_it_shrinks_back_to_a_types_own_height(tab, via):
    panel = tab.edit_background()
    panel.own.setChecked(True)
    combo = panel.form.bg_combo

    combo.setCurrentIndex(combo.findData("checkerboard"))
    height = panel.height()
    combo.setCurrentIndex(combo.findData(via))
    combo.setCurrentIndex(combo.findData("checkerboard"))

    assert panel.height() == height


def test_it_is_headed_by_its_command(tab):
    assert tab.edit_background().title.text() == COMMAND.text


# -- the ways in -------------------------------------------------------------------------


def background_action(menu):
    return menu.actions()[-1]


def test_a_right_click_on_empty_ground_offers_the_panel(tab):
    add_cards(tab, 1)
    menu = tab.card_menu(QPointF(5000, 5000))

    action = background_action(menu)
    assert action.text() == COMMAND.text
    action.trigger()
    assert tab.background_is_open()


def test_a_right_click_on_a_card_is_still_the_card_menu(tab):
    (card,) = add_cards(tab, 1)
    menu = tab.card_menu(card.sceneBoundingRect().center())
    assert "canvas.flip" in menu_layout(menu)


def test_the_spread_designer_offers_no_ground(qtbot):
    designer = make_tab(qtbot, SpreadTab)
    menu = designer.card_menu(QPointF(5000, 5000))
    assert COMMAND.text not in [action.text() for action in menu.actions()]
    assert designer.edit_background() is None


@pytest.fixture
def window(qtbot, stub_deck_manager, spreads_base, notes_base, monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def view_entry_enabled(window):
    window.update_canvas_background_action()
    return window.canvas_background_action.isEnabled()


def test_the_view_menu_offers_it_on_a_canvas_and_a_reading_only(window, minimal_deck):
    window.new_canvas_tab()
    assert view_entry_enabled(window)

    window.open_reading_of(readings_spread())
    assert view_entry_enabled(window)

    window.new_library_tab()
    assert not view_entry_enabled(window)

    window.new_card_view_tab()
    assert not view_entry_enabled(window)

    window.new_spread_tab()
    assert not view_entry_enabled(window)


def readings_spread():
    from tarot_canvas.models import spreads

    return spreads.load(spreads.BUNDLED_SPREADS_PATH / "three-card")


def test_the_view_entry_opens_the_panel_on_the_current_canvas(window):
    tab = window.new_canvas_tab()
    window.canvas_background_action.trigger()
    assert tab.background_is_open()


def test_its_entry_has_no_key(window):
    assert window.canvas_background_action.shortcuts() == []


# -- kept and reopened -------------------------------------------------------------------


def saved_canvas(window):
    tab = window.new_canvas_tab()
    window.update_save_action()
    window.save_action.trigger()
    return tab


def ground_table(path):
    import tomllib

    table = tomllib.loads((path / readings.READING_FILE).read_text())
    return table["app"]["land.arcana.tarotcanvas"].get("ground")


def test_a_saved_canvas_given_its_own_ground_writes_it(qtbot, window, readings_base):
    tab = saved_canvas(window)
    panel = tab.edit_background()
    choose_solid(panel)
    panel.apply()

    qtbot.waitUntil(lambda: ground_table(tab.reading_path) is not None, timeout=AUTOSAVE_MS * 4)
    assert ground_table(tab.reading_path) == {"style": "solid", "color": SOLID}


def test_a_reopened_reading_draws_its_own_ground(window, readings_base):
    tab = saved_canvas(window)
    tab.ground = own_solid()
    tab.saved_reading.write()
    path = tab.reading_path
    window.close_tab(window.tab_widget.indexOf(tab))

    reopened = window.open_saved_reading(path)

    assert reopened.ground == own_solid()
    assert brush_colour(reopened) == SOLID


def test_a_following_reading_reopens_following_the_changed_default(window, readings_base):
    tab = saved_canvas(window)
    path = tab.reading_path
    window.close_tab(window.tab_widget.indexOf(tab))
    own_solid("#abcdef").to_settings()

    reopened = window.open_saved_reading(path)

    assert reopened.ground is None
    assert brush_colour(reopened) == "#abcdef"


def test_a_reading_naming_a_missing_image_draws_the_default_and_keeps_the_name(
    qtbot, window, readings_base, backgrounds_base, caplog
):
    own_solid("#abcdef").to_settings()
    tab = saved_canvas(window)
    tab.ground = Ground(style="image", image="gone.png")
    tab.saved_reading.write()
    path = tab.reading_path
    window.close_tab(window.tab_widget.indexOf(tab))

    with caplog.at_level(logging.INFO):
        reopened = window.open_saved_reading(path)

    assert brush_colour(reopened) == "#abcdef"
    assert any("gone.png" in record.getMessage() for record in caplog.records)
    assert reopened.ground.image == "gone.png"
    reopened.saved_reading.write()
    assert ground_table(path)["image"] == "gone.png"


def test_a_tab_on_its_own_image_draws_it_over_the_default(window, backgrounds_base):
    write_image(backgrounds_base, "felt.png")
    tab = window.new_canvas_tab()

    tab.ground = Ground(style="image", image="felt.png", positioning="tile")
    tab.apply_ground()

    assert tab.view.backgroundBrush().texture().size() == QSize(64, 32)


def test_use_as_default_writes_the_settings_and_every_following_canvas_redraws(window):
    following = window.new_canvas_tab()
    own = window.new_canvas_tab()
    own.ground = own_solid("#654321")
    own.apply_ground()
    tab = window.new_canvas_tab()

    panel = tab.edit_background()
    choose_solid(panel)
    panel.default_button.click()

    assert panel.finished
    assert tab.ground is None
    assert get_settings().value(BACKGROUND_STYLE_KEY) == "solid"
    assert get_settings().value(BACKGROUND_COLOR_KEY) == SOLID
    assert brush_colour(tab) == SOLID
    assert brush_colour(following) == SOLID
    assert own.ground == own_solid("#654321")
    assert brush_colour(own) == "#654321"
