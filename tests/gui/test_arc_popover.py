from itertools import pairwise

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPalette, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QApplication, QDialogButtonBox

from tarot_canvas.ui.canvas.arc_popover import ARC_DEFAULTS, signed
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.strings import CANVAS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab


def make_tab(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab.resize(1000, 700)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def add_cards(tab, count, apart=40):
    """`count` selected 100-wide cards in a row, `apart` pixels between them"""
    pixmap = QPixmap(100, 160)
    pixmap.fill()
    cards = []
    for i in range(count):
        card = DraggableCardItem(pixmap, {"id": f"card-{i}"}, tab)
        card.setPos(i * (100 + apart), 0)
        tab.scene.addItem(card)
        card.setZValue(i)
        card.setSelected(True)
        cards.append(card)
    return cards


def places(cards):
    return [(QPointF(card.pos()), card.orient) for card in cards]


def count_layout_changes(tab):
    changes = []
    tab.layout_changed.connect(lambda: changes.append(1))
    return changes


@pytest.fixture
def tab(qtbot):
    tab = make_tab(qtbot)
    yield tab
    if tab.arc_popover is not None:
        tab.arc_popover.close()
    qtbot.wait(1100)


def test_opening_previews_the_arc(tab):
    cards = add_cards(tab, 4)
    before = places(cards)
    tab.open_arc_popover()
    assert places(cards) != before


@pytest.mark.parametrize("slider,notch", [("bend", 6), ("turn", 3)])
def test_moving_the_bend_or_turn_moves_the_cards(tab, slider, notch):
    cards = add_cards(tab, 4)
    popover = tab.open_arc_popover()
    first = places(cards)
    getattr(popover, slider).setValue(notch)
    assert places(cards) != first


def test_the_preview_never_drifts(tab):
    cards = add_cards(tab, 5)
    popover = tab.open_arc_popover()
    first = places(cards)
    popover.bend.setValue(-4)
    popover.turn.setValue(5)
    popover.follow.setChecked(True)
    popover.bend.setValue(12)
    popover.turn.setValue(0)
    popover.upright.setChecked(True)
    assert places(cards) == first


def test_cancel_puts_every_card_back(tab):
    cards = add_cards(tab, 4)
    cards[1].set_orient(30)
    before = places(cards)
    changes = count_layout_changes(tab)

    popover = tab.open_arc_popover()
    popover.follow.setChecked(True)
    popover.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()

    assert not popover.isVisible()
    assert places(cards) == before
    assert changes == []


def test_esc_puts_every_card_back(tab, qtbot):
    cards = add_cards(tab, 4)
    before = places(cards)
    changes = count_layout_changes(tab)

    popover = tab.open_arc_popover()
    popover.bend.setValue(10)
    qtbot.keyClick(popover.bend, Qt.Key.Key_Escape)

    assert not popover.isVisible()
    assert places(cards) == before
    assert changes == []


def test_esc_on_the_canvas_puts_every_card_back(tab):
    cards = add_cards(tab, 4)
    before = places(cards)
    popover = tab.open_arc_popover()
    tab.view.setFocus()
    tab.commands["canvas.cancel"].trigger()
    assert popover.finished
    assert places(cards) == before


def test_return_applies(tab, qtbot):
    cards = add_cards(tab, 4)
    changes = count_layout_changes(tab)
    popover = tab.open_arc_popover()
    arranged = places(cards)
    qtbot.keyClick(popover.bend, Qt.Key.Key_Return)
    assert popover.finished
    assert places(cards) == arranged
    assert changes == [1]


def test_hiding_the_tab_puts_every_card_back(tab):
    cards = add_cards(tab, 4)
    before = places(cards)
    popover = tab.open_arc_popover()
    tab.hide()
    assert popover.finished
    assert places(cards) == before
    assert not tab.arranging


def test_the_panel_is_part_of_the_canvas_not_a_window(tab):
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    assert not popover.isWindow()
    assert popover.parentWidget() is tab.canvas_area
    assert not popover.hasFocus()


def test_apply_keeps_the_arc_and_changes_the_layout_once(tab):
    cards = add_cards(tab, 4)
    changes = count_layout_changes(tab)
    popover = tab.open_arc_popover()
    popover.bend.setValue(6)
    arranged = places(cards)

    popover.buttons.button(QDialogButtonBox.StandardButton.Apply).click()

    assert not popover.isVisible()
    assert places(cards) == arranged
    assert changes == [1]


def test_the_first_arc_starts_from_the_defaults(tab):
    add_cards(tab, 3)
    assert tab.open_arc_popover().settings() == ARC_DEFAULTS


def test_reopening_keeps_the_last_choices_and_measures_the_spacing_again(tab):
    cards = add_cards(tab, 3, apart=40)
    popover = tab.open_arc_popover()
    assert popover.gap() == pytest.approx(0.4, abs=0.015)  # a smooth pixmap is 1px wider
    popover.bend.setValue(6)
    popover.turn.setValue(3)
    popover.anticlockwise.setChecked(True)
    popover.follow.setChecked(True)
    popover.spacing.setValue(90)
    popover.cancel()

    for i, card in enumerate(cards):
        card.setPos(i * 120, 0)
    again = tab.open_arc_popover()
    assert again.settings() == {"bend": 90, "turn": 45, "clockwise": False, "follow": True}
    assert again.gap() == pytest.approx(0.2, abs=0.015)


def test_a_wide_spacing_is_clamped_to_one_width(tab):
    add_cards(tab, 3, apart=500)
    assert tab.open_arc_popover().gap() == 1.0


@pytest.mark.parametrize("degrees,text", [(180, "+180"), (0, "0"), (-45, "-45")])
def test_a_bend_or_turn_shows_which_way_it_goes(degrees, text):
    assert signed(degrees) == text


def test_the_first_arc_is_a_rainbow(tab):
    cards = add_cards(tab, 5)
    tab.open_arc_popover()
    middles = [card.pos() + card.boundingRect().center() for card in cards]
    assert [m.x() for m in middles] == sorted(m.x() for m in middles)
    assert min(range(5), key=lambda i: middles[i].y()) == 2


def test_choosing_the_arc_from_the_menu_changes_nothing_yet(tab, monkeypatch):
    add_cards(tab, 3)
    changes = count_layout_changes(tab)

    def choose_arc(menu, *_):
        arc = menu.actions()[-1]
        menu.triggered.emit(arc)
        return arc

    monkeypatch.setattr("tarot_canvas.ui.tabs.canvas_tab.QMenu.exec", choose_arc)
    tab.on_align_cards()

    assert tab.arc_popover is not None and tab.arc_popover.isVisible()
    assert changes == []


# -- the canvas stays usable, but locked -----------------------------------------


def send_mouse(view, kind, pos, button, buttons, modifiers=Qt.KeyboardModifier.NoModifier):
    viewport = view.viewport()
    pos = QPointF(pos)
    event = QMouseEvent(
        kind, pos, QPointF(viewport.mapToGlobal(pos.toPoint())), button, buttons, modifiers
    )
    QApplication.sendEvent(viewport, event)


def drag(view, start, end, modifiers=Qt.KeyboardModifier.NoModifier):
    left = Qt.MouseButton.LeftButton
    none = Qt.MouseButton.NoButton
    send_mouse(view, QEvent.Type.MouseButtonPress, start, left, left, modifiers)
    send_mouse(view, QEvent.Type.MouseMove, (start + end) / 2, none, left, modifiers)
    send_mouse(view, QEvent.Type.MouseMove, end, none, left, modifiers)
    send_mouse(view, QEvent.Type.MouseButtonRelease, end, left, none, modifiers)


def wheel(view, pos, notches, modifiers=Qt.KeyboardModifier.NoModifier):
    viewport = view.viewport()
    QApplication.sendEvent(
        viewport,
        QWheelEvent(
            QPointF(pos),
            QPointF(viewport.mapToGlobal(pos)),
            QPoint(),
            QPoint(0, 120 * notches),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        ),
    )


def camera(view):
    return (
        view.transform().m11(),
        view.horizontalScrollBar().value(),
        view.verticalScrollBar().value(),
    )


def empty_point(tab):
    """A viewport point with no card under it, clear of the panel"""
    popover = tab.arc_popover
    free = popover.free_region()
    for x in range(free.left() + 10, free.right(), 20):
        for y in range(free.top() + 10, free.bottom(), 20):
            if tab.view.card_at(tab.view.mapToScene(QPoint(x, y))) is None:
                return QPoint(x, y)
    raise AssertionError("no empty canvas")


def test_the_wheel_zooms_while_the_panel_is_open(tab):
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    before = tab.view.transform().m11()
    wheel(tab.view, empty_point(tab), -2)
    assert tab.view.transform().m11() < before
    assert not popover.finished


def test_ctrl_wheel_over_a_card_zooms_and_does_not_turn_it(tab):
    cards = add_cards(tab, 3)
    tab.open_arc_popover()
    orients = [card.orient for card in cards]
    before = tab.view.transform().m11()
    over = tab.view.mapFromScene(cards[0].sceneBoundingRect().center())
    wheel(tab.view, over, 2, Qt.KeyboardModifier.ControlModifier)
    assert [card.orient for card in cards] == orients
    assert tab.view.transform().m11() != before


@pytest.mark.parametrize(
    "modifiers", [Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.NoModifier]
)
def test_a_drag_on_the_canvas_pans_while_the_panel_is_open(tab, modifiers):
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    start = empty_point(tab)
    before = camera(tab.view)
    drag(tab.view, start, start + QPoint(-40, -30), modifiers)
    assert camera(tab.view)[1:] != before[1:]
    assert not popover.finished


def test_a_click_or_drag_on_a_card_changes_nothing(tab):
    cards = add_cards(tab, 3)
    tab.open_arc_popover()
    tab.scene.clearSelection()  # what a click would do if it got through
    for card in cards:
        card.setSelected(True)
    arranged = places(cards)
    on_card = tab.view.mapFromScene(cards[1].sceneBoundingRect().center())
    drag(tab.view, on_card, on_card + QPoint(30, 30))
    assert places(cards) == arranged
    assert set(tab.selected_cards()) == set(cards)


def test_a_double_click_on_the_canvas_summons_nothing(tab):
    add_cards(tab, 3)
    tab.open_arc_popover()
    point = empty_point(tab)
    left = Qt.MouseButton.LeftButton
    send_mouse(tab.view, QEvent.Type.MouseButtonDblClick, point, left, left)
    send_mouse(tab.view, QEvent.Type.MouseButtonRelease, point, left, Qt.MouseButton.NoButton)
    assert len(tab.cards()) == 3


def card_commands(tab):
    keep = {"canvas.fit", "canvas.fullscreen", "canvas.cancel"}
    return [action for name, action in tab.commands.items() if name not in keep]


@pytest.mark.parametrize("close", ["cancel", "apply"])
def test_card_commands_are_off_while_open_and_back_after(tab, close):
    add_cards(tab, 3)
    before = {action: action.isEnabled() for action in [*card_commands(tab), tab.paste_action]}
    assert any(before.values())

    popover = tab.open_arc_popover()
    assert not any(action.isEnabled() for action in before)
    assert not tab.can_delete()
    assert not tab.can_cut_card()
    assert not tab.can_select_all()
    assert not tab.can_deselect()
    assert tab.view.locked
    assert tab.commands["canvas.fit"].isEnabled()

    getattr(popover, close)()
    assert {action: action.isEnabled() for action in before} == before
    assert tab.can_select_all()
    assert not tab.view.locked


# -- where the panel sits, and the view following ---------------------------------


def test_the_panel_sits_in_a_corner_away_from_the_cards(tab):
    viewport = tab.view.viewport().rect()
    near = tab.view.mapToScene(QPoint(viewport.right() - 150, viewport.top() + 150))
    cards = add_cards(tab, 3, apart=10)
    for i, card in enumerate(cards):
        card.setPos(near + QPointF(i * 20 - 70, -80))
    popover = tab.open_arc_popover()
    assert popover.corner != "top_right"
    cards_shown = tab.view.mapFromScene(popover.cards_rect()).boundingRect()
    panel = popover.geometry().translated(-tab.view.viewport().mapTo(tab.canvas_area, QPoint()))
    assert not panel.intersects(cards_shown)


def test_with_nothing_in_the_way_the_panel_sits_top_right(tab):
    cards = add_cards(tab, 3)
    for card in cards:
        card.moveBy(8000, 8000)  # nowhere near the view
    popover = tab.open_arc_popover()
    assert popover.corner == "top_right"


def shown_in(tab, rect, free, slack=2):
    shown = tab.view.mapFromScene(rect).boundingRect()
    return free.adjusted(-slack, -slack, slack, slack).contains(shown)


def test_the_view_brings_cards_from_off_screen_into_the_free_region(tab):
    cards = add_cards(tab, 5)
    for card in cards:
        card.moveBy(6000, 4000)
    popover = tab.open_arc_popover()
    free = popover.free_region()
    for card in cards:
        assert shown_in(tab, card.sceneBoundingRect(), free)


def test_the_view_follows_as_the_sliders_move(tab):
    cards = add_cards(tab, 8)
    popover = tab.open_arc_popover()
    popover.spacing.setValue(100)
    popover.follow.setChecked(True)
    free = popover.free_region()
    for card in cards:
        assert shown_in(tab, card.sceneBoundingRect(), free)


def test_the_view_never_zooms_in(tab):
    add_cards(tab, 2)
    tab.view.zoom_by_from_center(0.2)
    before = tab.view.transform().m11()
    popover = tab.open_arc_popover()
    popover.bend.setValue(3)
    assert tab.view.transform().m11() <= before


def test_a_zoom_by_hand_stops_the_view_following(tab):
    cards = add_cards(tab, 5)
    popover = tab.open_arc_popover()
    point = tab.view.mapFromScene(cards[0].sceneBoundingRect().center())
    for _ in range(6):
        wheel(tab.view, point, 1)  # well in, so the arc no longer fits
    held = camera(tab.view)
    popover.spacing.setValue(100)
    popover.bend.setValue(24)
    assert camera(tab.view) == held


def test_cancel_and_apply_leave_the_view_where_it_is(tab):
    cards = add_cards(tab, 5)
    for card in cards:
        card.moveBy(6000, 4000)
    popover = tab.open_arc_popover()
    followed = camera(tab.view)
    popover.cancel()
    assert camera(tab.view) == followed


def test_the_panel_hides_the_canvas_under_it(tab):
    tab.create_solid_color_background("#ff00ff")
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    image = tab.grab().toImage()
    inside = popover.geometry().topLeft() + QPoint(4, 4)  # in the margin, clear of every control
    assert image.pixelColor(inside) == popover.palette().color(QPalette.ColorRole.Window)


def test_the_panel_is_outlined_against_the_canvas(tab):
    tab.create_solid_color_background("#ff00ff")
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    image = tab.grab().toImage()
    middle_of_left_edge = popover.geometry().topLeft() + QPoint(0, popover.height() // 2)
    edge = image.pixelColor(middle_of_left_edge)
    fill = popover.palette().color(QPalette.ColorRole.Window)
    assert edge != fill
    assert edge != QColor("#ff00ff")


def test_the_panel_is_titled_by_its_menu_entry(tab):
    add_cards(tab, 3)
    assert tab.open_arc_popover().title.text() == CANVAS["arrange_arc"]


def test_the_sliders_line_up(tab):
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    sliders = (popover.bend, popover.turn, popover.spacing)
    assert len({slider.x() for slider in sliders}) == 1
    assert len({slider.width() for slider in sliders}) == 1


def test_the_gap_spin_box_and_slider_follow_each_other(tab):
    cards = add_cards(tab, 3)
    popover = tab.open_arc_popover()
    popover.spacing.setValue(30)
    assert popover.spacing_box.value() == pytest.approx(0.30)

    before = places(cards)
    popover.spacing_box.setValue(0.75)
    assert popover.spacing.value() == 75
    assert popover.gap() == pytest.approx(0.75)
    assert places(cards) != before, "a typed gap previews too"


def test_the_gap_spin_box_shows_the_gap_s_own_words(tab):
    add_cards(tab, 3)
    box = tab.open_arc_popover().spacing_box
    prefix, _, suffix = CANVAS["arc_gap"].partition("{gap}")
    assert (box.prefix(), box.suffix()) == (prefix, suffix)


def test_the_rows_read_orientation_bend_turn_direction_gap(tab):
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    rows = (popover.upright, popover.bend, popover.turn, popover.clockwise, popover.spacing)
    tops = [control.mapTo(popover, QPoint(0, control.height() // 2)).y() for control in rows]
    assert tops == sorted(tops)
    assert len(set(tops)) == len(tops)


def test_tab_goes_down_the_rows(tab):
    add_cards(tab, 3)
    popover = tab.open_arc_popover()
    order = [popover.upright, popover.follow, popover.bend, popover.turn]
    order += [popover.clockwise, popover.anticlockwise, popover.spacing]
    for first, second in pairwise(order):
        assert next_tab_stop(first) is second


def next_tab_stop(widget):
    """Where Tab goes from widget: the next in the chain that Tab can focus"""
    following = widget.nextInFocusChain()
    while not following.focusPolicy() & Qt.FocusPolicy.TabFocus:
        following = following.nextInFocusChain()
    return following
