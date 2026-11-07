import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PyQt6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QEnterEvent,
    QMouseEvent,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import QApplication

from tarot_canvas.settings import (
    BACKGROUND_COLOR_KEY,
    BACKGROUND_STYLE_KEY,
    CANVAS_GUIDES_KEY,
    CANVAS_TAB_MINIMAP_KEY,
    CHECKERBOARD_COLOR_KEY,
    MOTION_LEVEL_KEY,
    get_settings,
)
from tarot_canvas.ui.canvas import (
    align_items_horizontally,
    align_items_vertically,
    arrange_items_on_arc,
    distribute_items_horizontally,
)
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.ground import CHECKERBOARD_SQUARE, checkerboard_partner
from tarot_canvas.ui.canvas.guides import GuideItem
from tarot_canvas.ui.canvas.icons import CanvasIcon
from tarot_canvas.ui.canvas.motion import LIFT_REST, LIFT_SELECTED
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, GILT_ON_LIGHT
from tarot_canvas.ui.card_colours import CARD_COLOURS, SLOT_COLOUR
from tarot_canvas.ui.card_transfer import card_mime_data, cards_mime_data, copy_card_to_clipboard
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab, wheel_turn
from tarot_canvas.ui.widgets.document_tabs import DocumentTabs


def add_cards(tab, count):
    """Put count selected cards on the canvas."""
    pixmap = QPixmap(100, 160)
    pixmap.fill()
    for i in range(count):
        item = DraggableCardItem(pixmap, {"id": f"card-{i}"})
        item.setPos(i * 150, 0)
        tab.scene.addItem(item)
        item.setSelected(True)


def set_motion_level(level):
    settings = get_settings()
    settings.setValue(MOTION_LEVEL_KEY, level)
    settings.sync()


def make_tab(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def test_arrange_actions_track_the_selection(qtbot):
    tab = make_tab(qtbot)
    align = tab.arrange_actions[tab.on_align_cards]
    front = tab.arrange_actions[tab.on_bring_to_front]

    assert not align.isEnabled()
    assert not front.isEnabled()

    add_cards(tab, 1)
    assert front.isEnabled()
    assert not align.isEnabled(), "aligning needs two cards"

    add_cards(tab, 1)
    assert align.isEnabled()

    tab.scene.clearSelection()
    assert not front.isEnabled()
    assert not align.isEnabled()


def test_align_menu_anchors_to_its_toolbar_button(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 2)

    button = tab.toolbar.widgetForAction(tab.arrange_actions[tab.on_align_cards])
    assert button is not None

    anchor = tab.align_menu_anchor()
    expected = button.mapToGlobal(button.rect().bottomLeft())
    # Below the button, within a pixel of its bottom-left corner: never QCursor.pos(),
    # which carries no meaning on Wayland.
    assert abs(anchor.x() - expected.x()) <= 1
    assert abs(anchor.y() - expected.y()) <= 1


def test_an_arc_goes_round_in_z_order_whatever_the_selection_order(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 4)
    cards = list(tab.cards())
    for z, card in enumerate(cards):
        card.setZValue(z)
    select_only(tab, reversed(cards))

    assert tab.arrange_order(tab.selected_cards()) == cards
    popover = tab.open_arc_popover()
    popover.apply()

    # The default is a rainbow, numbered left to right
    centres = [card.pos() + card.boundingRect().center() for card in cards]
    assert [c.x() for c in centres] == sorted(c.x() for c in centres)
    qtbot.wait(1100)


def hover_canvas(tab, viewport_pos):
    """Put the pointer over the canvas at viewport_pos, as a real move would."""
    view = tab.view
    globalpos = QPointF(view.viewport().mapToGlobal(viewport_pos))
    QApplication.sendEvent(
        view.viewport(), QEnterEvent(QPointF(viewport_pos), QPointF(viewport_pos), globalpos)
    )
    QApplication.sendEvent(
        view.viewport(),
        QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(viewport_pos),
            globalpos,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def only_card(tab):
    cards = [item for item in tab.scene.items() if isinstance(item, DraggableCardItem)]
    assert len(cards) == 1
    return cards[0]


def test_card_is_drawn_under_the_pointer(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    spot = QPoint(120, 90)
    hover_canvas(tab, spot)

    tab.add_specific_card(minimal_deck.get_random_card())

    card = only_card(tab)
    centre = card.sceneBoundingRect().center()
    expected = tab.view.mapToScene(spot)
    assert abs(centre.x() - expected.x()) <= 1
    assert abs(centre.y() - expected.y()) <= 1


def test_card_falls_back_to_the_view_centre_when_the_pointer_is_away(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    hover_canvas(tab, QPoint(120, 90))
    QApplication.sendEvent(tab.view.viewport(), QEvent(QEvent.Type.Leave))

    tab.add_specific_card(minimal_deck.get_random_card())

    centre = only_card(tab).sceneBoundingRect().center()
    view_centre = tab.view.mapToScene(tab.view.viewport().rect().center())
    # Placed near the middle of the view, jittered by up to 50px on each axis
    assert abs(centre.x() - view_centre.x()) <= 50
    assert abs(centre.y() - view_centre.y()) <= 50


def test_repeated_draws_cascade_instead_of_stacking(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    hover_canvas(tab, QPoint(120, 90))

    positions = [tab.add_specific_card(minimal_deck.get_random_card()).pos() for _ in range(3)]
    assert len({(p.x(), p.y()) for p in positions}) == 3


def send_mouse(tab, kind, pos, button, buttons=None, modifiers=Qt.KeyboardModifier.NoModifier):
    view = tab.view
    QApplication.sendEvent(
        view.viewport(),
        QMouseEvent(
            kind,
            QPointF(pos),
            QPointF(view.viewport().mapToGlobal(pos)),
            button,
            button if buttons is None else buttons,
            modifiers,
        ),
    )


def double_click(tab, pos):
    send_mouse(tab, QMouseEvent.Type.MouseButtonDblClick, pos, Qt.MouseButton.LeftButton)


def test_double_clicking_empty_canvas_summons_a_card_there(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    tab.deck = minimal_deck
    spot = QPoint(120, 90)

    double_click(tab, spot)

    centre = only_card(tab).sceneBoundingRect().center()
    expected = tab.view.mapToScene(spot)
    assert abs(centre.x() - expected.x()) <= 1
    assert abs(centre.y() - expected.y()) <= 1


def test_double_clicking_a_card_summons_nothing(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    tab.deck = minimal_deck
    add_cards(tab, 1)
    card = only_card(tab)
    card.settle_motion()
    spot = tab.view.mapFromScene(card.sceneBoundingRect().center())

    double_click(tab, spot)

    assert only_card(tab) is card


def drag(tab, button, start, end, modifiers=Qt.KeyboardModifier.NoModifier):
    send_mouse(tab, QMouseEvent.Type.MouseButtonPress, start, button, modifiers=modifiers)
    send_mouse(
        tab, QMouseEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, button, modifiers=modifiers
    )
    send_mouse(tab, QMouseEvent.Type.MouseButtonRelease, end, button, Qt.MouseButton.NoButton)


def view_centre(tab):
    return tab.view.mapToScene(tab.view.viewport().rect().center())


def test_middle_drag_pans_the_view(qtbot):
    tab = make_tab(qtbot)
    before = view_centre(tab)

    drag(tab, Qt.MouseButton.MiddleButton, QPoint(200, 150), QPoint(120, 100))

    after = view_centre(tab)
    # Dragging the canvas up and left moves the camera down and right by the same amount
    assert abs((after.x() - before.x()) - 80) <= 1
    assert abs((after.y() - before.y()) - 50) <= 1


def test_middle_drag_pans_over_a_card(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = only_card(tab)
    card.setPos(tab.view.mapToScene(QPoint(200, 150)))
    before = card.pos()

    drag(tab, Qt.MouseButton.MiddleButton, QPoint(200, 150), QPoint(120, 100))

    assert card.pos() == before, "panning must not drag the card under the pointer"


def test_shift_left_drag_still_pans(qtbot):
    tab = make_tab(qtbot)
    before = view_centre(tab)

    drag(
        tab,
        Qt.MouseButton.LeftButton,
        QPoint(200, 150),
        QPoint(120, 100),
        Qt.KeyboardModifier.ShiftModifier,
    )

    assert abs((view_centre(tab).x() - before.x()) - 80) <= 1


def test_panning_leaves_no_override_cursor_behind(qtbot):
    tab = make_tab(qtbot)
    depth = 0 if QApplication.overrideCursor() is None else 1

    # A stray left click mid-pan must not end the pan or strand the cursor
    send_mouse(
        tab, QMouseEvent.Type.MouseButtonPress, QPoint(200, 150), Qt.MouseButton.MiddleButton
    )
    send_mouse(
        tab,
        QMouseEvent.Type.MouseButtonPress,
        QPoint(200, 150),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.MiddleButton | Qt.MouseButton.LeftButton,
    )
    send_mouse(
        tab,
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(200, 150),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.MiddleButton,
    )
    assert tab.view._pan_button == Qt.MouseButton.MiddleButton

    send_mouse(
        tab,
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(200, 150),
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.NoButton,
    )
    assert tab.view._pan_button is None
    assert (0 if QApplication.overrideCursor() is None else 1) == depth


def test_the_motion_clock_follows_the_tab_visibility(qtbot):
    """An idle window must genuinely idle."""
    set_motion_level("Full")
    tab = make_tab(qtbot)
    assert tab.motion_clock.is_running()

    tab.hide()
    assert not tab.motion_clock.is_running()

    tab.show()
    qtbot.waitExposed(tab)
    assert tab.motion_clock.is_running()


def test_the_motion_clock_stays_off_when_motion_is_off(qtbot):
    set_motion_level("Off")
    tab = make_tab(qtbot)
    assert not tab.motion_clock.is_running()


def test_ambient_stays_shut_while_the_canvas_is_hidden(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    tab.hide()
    assert not tab.ambient_is_allowed()


def test_cards_hold_an_identity_transform_while_ambient_is_gated(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]
    tab.scene.clearSelection()

    for frame in range(120):
        tab._advance_motion(0.5 + frame / 60.0, 1.0 / 60.0)

    assert tab.ambient_gain == 0.0  # snapped, not merely small
    assert all(card.transform().isIdentity() for card in cards)

    # Exactly identity
    assert not any(card.advance_motion(3.0, 1.0 / 60.0, 0.0) for card in cards)


def test_cards_drift_once_ambient_is_allowed(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]

    for card in cards:
        card.advance_motion(0.0, 1.0 / 60.0, 1.0)
    first = [card.transform() for card in cards]
    assert not any(transform.isIdentity() for transform in first)
    assert not any(transform.isAffine() for transform in first)  # tilt, not a 2-D spin

    for card in cards:
        card.advance_motion(2.0, 1.0 / 60.0, 1.0)
    deltas = [
        card.transform().dx() - transform.dx() for card, transform in zip(cards, first, strict=True)
    ]
    assert len(set(deltas)) == len(deltas)


def test_every_card_gets_its_own_depth(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]
    for card in cards:
        card.setZValue(tab.take_top_z())
    depths = [card.zValue() for card in cards]

    assert len(set(depths)) == len(depths)


def test_restacking_a_selection_keeps_its_internal_order(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = sorted(
        (i for i in tab.scene.items() if isinstance(i, DraggableCardItem)),
        key=lambda item: item.zValue(),
    )
    for depth, card in enumerate(cards, start=1):
        card.setZValue(float(depth))
        card.setSelected(True)

    tab.on_bring_to_front()
    assert [c.zValue() for c in cards] == sorted(c.zValue() for c in cards)

    tab.on_send_to_back()
    assert [c.zValue() for c in cards] == sorted(c.zValue() for c in cards)


def test_a_raised_card_carries_its_shadow_with_it(qtbot):
    """Raising a card must lift its shadow past the cards it now sits on top of."""
    tab = make_tab(qtbot)
    add_cards(tab, 2)
    lower, upper = sorted(
        (i for i in tab.scene.items() if isinstance(i, DraggableCardItem)),
        key=lambda item: item.zValue(),
    )

    tab.scene.clearSelection()
    lower.setSelected(True)
    tab.on_bring_to_front()

    assert lower.zValue() > upper.zValue()
    assert lower.shadow.zValue() > upper.zValue()  # the shadow lands *on* the other card


def test_reactive_is_no_longer_indistinguishable_from_off(qtbot):
    set_motion_level("Reactive")
    tab = make_tab(qtbot)

    assert tab.motion_is_enabled()  # the clock runs
    assert tab.reactive_is_allowed()  # cards answer the pointer
    assert not tab.ambient_is_allowed()  # but nothing breathes

    set_motion_level("Off")
    tab.refresh_motion_settings()

    assert not tab.motion_is_enabled()
    assert not tab.reactive_is_allowed()


def test_selection_lifts_the_card_off_the_felt(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = next(i for i in tab.scene.items() if isinstance(i, DraggableCardItem))

    card.setSelected(True)
    for frame in range(120):
        card.advance_motion(frame / 60.0, 1.0 / 60.0, 0.0)
    lifted = card.motion.lift
    assert lifted > 1.0

    card.setSelected(False)
    for frame in range(120):
        card.advance_motion(frame / 60.0, 1.0 / 60.0, 0.0)
    assert card.motion.lift == 1.0
    assert card.transform().isIdentity()


def test_a_hidden_canvas_is_left_flat_rather_than_frozen_mid_breath(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 2)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]
    for card in cards:
        card.advance_motion(1.0, 1.0 / 60.0, 1.0)

    tab.hide()

    assert all(card.transform().isIdentity() for card in cards)


def test_flip_and_rotate_drive_the_orient_channel(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = next(i for i in tab.scene.items() if isinstance(i, DraggableCardItem))

    tab.on_flip_card()
    assert card.is_reversed()
    assert card.orient == 0
    assert not card.transform().isIdentity()  # the channel really reaches the transform

    tab.on_flip_card()
    assert not card.is_reversed()

    tab.on_rotate_card()
    assert card.orient == 90
    tab.on_rotate_card()
    tab.on_rotate_card()
    tab.on_rotate_card()
    assert card.orient == 0  # wraps rather than accumulating


def test_a_flip_keeps_the_rotation_and_leaves_the_deck_alone(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    card = minimal_deck.get_all_cards()[0]
    item = tab.add_specific_card(card, card_deck=minimal_deck)

    tab.on_rotate_card()
    tab.on_flip_card()
    assert item.orient == 90
    assert item.is_reversed()
    assert "reversed" not in minimal_deck.get_card_by_id(card["id"])

    tab.on_flip_card()
    assert item.orient == 90
    assert not item.is_reversed()
    assert "reversed" not in minimal_deck.get_card_by_id(card["id"])


def test_a_card_summoned_reversed_is_drawn_upside_down(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    card = minimal_deck.get_all_cards()[0]

    item = tab.add_specific_card(card, card_deck=minimal_deck, is_reversed=True)

    assert item.is_reversed()
    assert item.orient == 0
    item.settle_motion()
    assert item.motion.drawn_angle() == 180.0
    assert "reversed" not in minimal_deck.get_card_by_id(card["id"])


def test_applying_preferences_starts_and_stops_the_clock(qtbot):
    """The gate is re-sampled when preferences are applied, not polled on the tick."""
    set_motion_level("Full")
    tab = make_tab(qtbot)
    assert tab.motion_clock.is_running()

    set_motion_level("Off")
    tab.apply_background_settings()
    assert not tab.motion_clock.is_running()

    set_motion_level("Full")
    tab.apply_background_settings()
    assert tab.motion_clock.is_running()


# -- paste and drop ----------------------------------------------------------------


def drag_over(tab, mime, viewport_pos):
    """Enter, move and drop at viewport_pos, as a real drag would. Returns the events."""
    viewport = tab.view.viewport()
    args = (
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    enter = QDragEnterEvent(viewport_pos, *args)
    move = QDragMoveEvent(viewport_pos, *args)
    drop = QDropEvent(QPointF(viewport_pos), *args)
    for event in (enter, move, drop):
        QApplication.sendEvent(viewport, event)
    return enter, move, drop


def test_a_dropped_card_lands_centred_under_the_drop(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    spot = QPoint(160, 120)
    card = minimal_deck.get_card_by_id("major_arcana.01")

    enter, move, drop = drag_over(tab, card_mime_data(card, minimal_deck), spot)

    assert enter.isAccepted()
    assert move.isAccepted(), "QGraphicsView's own dragMoveEvent refuses what enter accepted"
    assert drop.isAccepted()
    placed = only_card(tab)
    assert placed.card_data["id"] == "major_arcana.01"
    centre = placed.sceneBoundingRect().center()
    expected = tab.view.mapToScene(spot)
    assert abs(centre.x() - expected.x()) <= 1
    assert abs(centre.y() - expected.y()) <= 1
    qtbot.wait(1100)


def test_a_drop_ignores_the_stale_pointer(qtbot, minimal_deck):
    """A drag delivers no Enter, so the tracked pointer is wherever it last was."""
    tab = make_tab(qtbot)
    hover_canvas(tab, QPoint(40, 40))
    card = minimal_deck.get_card_by_id("major_arcana.00")

    drag_over(tab, card_mime_data(card, minimal_deck), QPoint(260, 200))

    centre = only_card(tab).sceneBoundingRect().center()
    assert abs(centre.x() - tab.view.mapToScene(QPoint(260, 200)).x()) <= 1
    qtbot.wait(1100)


def test_a_drop_that_is_not_a_card_places_nothing(qtbot):
    tab = make_tab(qtbot)
    mime = QMimeData()
    mime.setText("The Fool")

    _, move, _ = drag_over(tab, mime, QPoint(160, 120))

    # QGraphicsScene accepts every enter; the move is where a drag is refused, so a
    # real one shows the forbidden cursor and never gets as far as a drop
    assert not move.isAccepted()
    assert [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)] == []
    qtbot.wait(1100)


def test_the_toolbar_paste_button_follows_the_clipboard(qtbot, clipboard, minimal_deck):
    tab = make_tab(qtbot)
    assert not tab.paste_action.isEnabled()
    assert tab.paste_action.shortcut().isEmpty(), "Ctrl+V belongs to Edit > Paste Card"

    copy_card_to_clipboard(minimal_deck.get_card_by_id("major_arcana.00"), minimal_deck)
    assert tab.paste_action.isEnabled()

    tab.paste_action.trigger()
    assert only_card(tab).card_data["id"] == "major_arcana.00"
    qtbot.wait(1100)


def test_a_copy_pastes_once(qtbot, clipboard, minimal_deck):
    """A second paste of the same clipboard would only stack a duplicate."""
    tab = make_tab(qtbot)
    card = minimal_deck.get_card_by_id("major_arcana.00")
    copy_card_to_clipboard(card, minimal_deck)

    tab.paste_action.trigger()
    assert not tab.paste_action.isEnabled()
    assert not tab.can_paste_card(clipboard.mimeData())
    tab.on_paste_card()
    assert len([i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]) == 1

    copy_card_to_clipboard(card, minimal_deck)
    assert tab.paste_action.isEnabled(), "a new copy is a new paste"
    qtbot.wait(1100)


def test_pasting_once_does_not_stop_a_drop(qtbot, clipboard, minimal_deck):
    tab = make_tab(qtbot)
    card = minimal_deck.get_card_by_id("major_arcana.00")
    copy_card_to_clipboard(card, minimal_deck)
    tab.paste_action.trigger()

    drag_over(tab, card_mime_data(card, minimal_deck), QPoint(260, 200))

    assert len([i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]) == 2
    qtbot.wait(1100)


def test_a_paste_naming_a_removed_deck_places_nothing(qtbot, clipboard, minimal_deck, tmp_path):
    import shutil

    from tarot_canvas.models.deck import TarotDeck
    from tests.conftest import MINIMAL_DECK_PATH

    shutil.copytree(MINIMAL_DECK_PATH, tmp_path / "gone")
    gone = TarotDeck(str(tmp_path / "gone"))
    tab = make_tab(qtbot)

    assert tab.paste_card(card_mime_data(gone.get_random_card(), gone)) is None
    assert [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)] == []
    qtbot.wait(1100)


def test_pasting_three_cards_places_three_at_distinct_positions(
    qtbot, clipboard, full_deck, stub_deck_manager
):
    stub_deck_manager.get_all_decks = lambda: [full_deck]
    ids = ["major_arcana.00", "minor_arcana.cups.two", "minor_arcana.swords.queen"]
    tab = make_tab(qtbot)

    first = tab.paste_card(cards_mime_data([full_deck.get_card_by_id(i) for i in ids], full_deck))

    placed = canvas_cards(tab)
    assert sorted(item.card_data["id"] for item in placed) == sorted(ids)
    assert first.card_data["id"] == ids[0]
    assert len({(item.pos().x(), item.pos().y()) for item in placed}) == 3
    assert all(item.isSelected() for item in placed)
    qtbot.wait(1100)


def canvas_cards(tab):
    return [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]


def test_selection_marks_are_not_cards(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 2)

    assert len(tab.cards()) == 2
    assert all(card.marks.built for card in canvas_cards(tab))
    assert len(tab.scene.selectedItems()) == 2


def test_zooming_tells_the_selected_cards_so_their_corners_hold_their_size(qtbot):
    tab = make_tab(qtbot)
    tab.resize(1000, 700)  # room for one card at 1x, so home is exactly 1x
    add_cards(tab, 1)
    card = canvas_cards(tab)[0]
    near = card.marks.corners[0].path().boundingRect()

    tab.view.zoom_by_from_center(0.25)

    assert card.view_scale() == pytest.approx(0.25)
    assert card.marks.corners[0].path().boundingRect().width() > near.width()

    tab.on_home()

    assert card.view_scale() == 1.0
    assert card.marks.corners[0].path().boundingRect() == near


def viewport_centre_in_scene(tab):
    return tab.view.mapToScene(tab.view.viewport().rect().center())


def test_home_shows_one_card_at_1x_centred(qtbot):
    tab = make_tab(qtbot)
    tab.resize(1000, 700)
    add_cards(tab, 1)
    card = canvas_cards(tab)[0]
    tab.view.zoom_by_from_center(4)
    told = []
    tab.view.zoom_changed.connect(told.append)

    tab.on_home()

    assert tab.view.transform().m11() == 1.0
    assert told == [1.0]
    centre = viewport_centre_in_scene(tab)
    expected = card.sceneBoundingRect().center()
    assert centre.x() == pytest.approx(expected.x(), abs=1)
    assert centre.y() == pytest.approx(expected.y(), abs=1)


def test_home_on_an_empty_canvas_is_1x_at_the_origin(qtbot):
    tab = make_tab(qtbot)
    tab.resize(1000, 700)
    tab.view.zoom_by_from_center(3)
    for _ in range(5):  # pan well away from the origin
        tab.view.horizontalScrollBar().setValue(tab.view.horizontalScrollBar().maximum())
        tab.view.verticalScrollBar().setValue(tab.view.verticalScrollBar().maximum())

    tab.on_home()

    assert tab.view.transform().m11() == 1.0
    centre = viewport_centre_in_scene(tab)
    assert centre.x() == pytest.approx(0, abs=1)
    assert centre.y() == pytest.approx(0, abs=1)


@pytest.mark.parametrize(
    ("style", "tone"),
    [
        ("gradient", GILT_ON_DARK),
        ("checkerboard", GILT_ON_LIGHT),
        # A label stored before the combo stored keys
        ("Gradient", GILT_ON_DARK),
        ("Checkerboard", GILT_ON_LIGHT),
    ],
)
def test_the_selection_tone_follows_the_background(qtbot, style, tone):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = canvas_cards(tab)[0]

    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, style)
    settings.sync()
    tab.apply_background_settings()

    assert tab.gilt == QColor(tone)
    assert card.marks.corners[0].brush().color() == QColor(tone)


def test_a_light_solid_background_takes_the_dark_gilt(qtbot):
    tab = make_tab(qtbot)
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "solid")
    settings.setValue(BACKGROUND_COLOR_KEY, "#ffffff")
    settings.sync()

    tab.apply_background_settings()

    assert tab.gilt == QColor(GILT_ON_LIGHT)


def test_the_checkerboard_is_the_stored_colour_and_its_partner(qtbot):
    tab = make_tab(qtbot)
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "checkerboard")
    settings.setValue(CHECKERBOARD_COLOR_KEY, "#35654d")
    settings.sync()

    tab.apply_background_settings()

    tile = tab.view.backgroundBrush().texture().toImage()
    colour = QColor("#35654d")
    assert tile.width() == tile.height() == 2 * CHECKERBOARD_SQUARE
    assert tile.pixelColor(10, 10) == colour
    assert tile.pixelColor(tile.width() - 10, tile.height() - 10) == colour
    assert tile.pixelColor(tile.width() - 10, 10) == checkerboard_partner(colour)
    assert tile.pixelColor(10, tile.height() - 10) == checkerboard_partner(colour)
    # A dark board takes the light gilt, as a dark solid ground does
    assert tab.gilt == QColor(GILT_ON_DARK)


def press_and_move(tab, card, by):
    """Grab card by its left strip, which no neighbour in stacked_cards() covers."""
    start = tab.view.mapFromScene(card.mapToScene(QPointF(20.0, 80.0)))
    send_mouse(tab, QMouseEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    for step in range(1, 4):
        send_mouse(
            tab,
            QMouseEvent.Type.MouseMove,
            start + by * step / 3,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
    return start + by


def release(tab, at):
    send_mouse(
        tab,
        QMouseEvent.Type.MouseButtonRelease,
        at,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )


def stacked_cards(tab, count):
    """count overlapping, unselected cards, the first at the bottom."""
    add_cards(tab, count)
    tab.scene.clearSelection()
    cards = sorted(canvas_cards(tab), key=lambda card: card.pos().x())
    for card in cards:
        card.setPos(card.pos().x() / 3, 0)  # overlap each neighbour by two thirds
        card.setZValue(tab.take_top_z())
    return cards


def test_a_dragged_card_rides_above_every_card_it_crosses(qtbot):
    tab = make_tab(qtbot)
    bottom, middle, top = stacked_cards(tab, 3)

    end = press_and_move(tab, bottom, QPoint(120, 0))
    assert bottom.zValue() > max(middle.zValue(), top.zValue()), "picked up, not slid under"

    release(tab, end)
    assert bottom.zValue() > max(middle.zValue(), top.zValue()), "and put down on top"


def test_a_dragged_selection_rises_together_and_keeps_its_own_order(qtbot):
    tab = make_tab(qtbot)
    first, second, third = stacked_cards(tab, 3)
    first.setSelected(True)
    second.setSelected(True)

    release(tab, press_and_move(tab, first, QPoint(0, 200)))

    assert third.zValue() < first.zValue() < second.zValue()


def test_dragging_the_top_card_spends_no_depth(qtbot):
    tab = make_tab(qtbot)
    *_, top = stacked_cards(tab, 3)
    depth = top.zValue()

    release(tab, press_and_move(tab, top, QPoint(0, 200)))

    assert top.zValue() == depth


def test_a_group_drag_moves_every_card_the_same_way_with_no_physics(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 2)
    grabbed, carried = sorted(canvas_cards(tab), key=lambda card: card.pos().x())
    before = [grabbed.pos(), carried.pos()]

    end = press_and_move(tab, grabbed, QPoint(90, 40))
    for frame in range(30):
        for card in (grabbed, carried):
            card.advance_motion(frame / 60.0, 1.0 / 60.0, 0.0)

    assert grabbed.pos() - before[0] == carried.pos() - before[1]
    for card in (grabbed, carried):
        assert card.motion.face_x == 0.0
        assert card.motion.face_y == 0.0
        assert card.motion.lift == pytest.approx(LIFT_SELECTED, abs=1e-3)

    release(tab, end)
    assert not grabbed._group_dragging


def test_a_lone_drag_still_ploughs(qtbot):
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 2)
    tab.scene.clearSelection()
    card = sorted(canvas_cards(tab), key=lambda card: card.pos().x())[0]

    end = press_and_move(tab, card, QPoint(90, 0))
    for frame in range(3):
        card.advance_motion(frame / 60.0, 1.0 / 60.0, 0.0)

    assert card._dragging and not card._group_dragging
    assert card.motion.face_y < 0  # the leading edge digs in
    release(tab, end)


# Snapping a dragged card

ALT = Qt.KeyboardModifier.AltModifier


@pytest.fixture
def snapping():
    """Snapping is off until it is turned on in Preferences."""
    get_settings().setValue(CANVAS_GUIDES_KEY, True)


def mover_and_still(tab):
    """An unselected card at the origin and another, mover, away from it below and to the right."""
    add_cards(tab, 2)
    tab.scene.clearSelection()
    still, mover = sorted(canvas_cards(tab), key=lambda card: card.pos().x())
    still.setPos(0, 0)
    mover.setPos(120, 200)
    tab.view.centerOn(QPointF(110, 180))
    return still, mover


def move_to(tab, at, modifiers=Qt.KeyboardModifier.NoModifier):
    send_mouse(
        tab,
        QMouseEvent.Type.MouseMove,
        at,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        modifiers=modifiers,
    )


def drag_card(tab, card, by, modifiers=Qt.KeyboardModifier.NoModifier):
    """Press card, move it by screen pixels in three steps, and let go."""
    start = tab.view.mapFromScene(card.mapToScene(QPointF(20.0, 80.0)))
    send_mouse(tab, QMouseEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    for step in range(1, 4):
        move_to(tab, start + by * step / 3, modifiers)
    release(tab, start + by)


def test_a_dragged_card_lands_exactly_on_a_centre_line_it_comes_near(snapping, qtbot):
    tab = make_tab(qtbot)
    still, mover = mover_and_still(tab)

    drag_card(tab, mover, QPoint(-120 + 3, 0))

    assert mover.pos().x() == pytest.approx(still.pos().x(), abs=1e-9)
    assert mover.pos().y() == pytest.approx(200, abs=1)


def test_alt_held_lets_a_card_land_where_the_mouse_put_it(snapping, qtbot):
    tab = make_tab(qtbot)
    _, mover = mover_and_still(tab)

    drag_card(tab, mover, QPoint(-120 + 3, 0), modifiers=ALT)

    assert mover.pos().x() == pytest.approx(3, abs=1)
    assert tab.guide_item.scene() is None


def test_snapping_is_off_until_it_is_turned_on(qtbot):
    tab = make_tab(qtbot)
    assert not tab.snap_guides
    _, mover = mover_and_still(tab)

    drag_card(tab, mover, QPoint(-120 + 3, 0))

    assert mover.pos().x() == pytest.approx(3, abs=1)


@pytest.mark.parametrize(("miss_px", "snaps"), [(6, True), (12, False)])
def test_the_snap_radius_is_in_screen_pixels(snapping, qtbot, miss_px, snaps):
    tab = make_tab(qtbot)
    _, mover = mover_and_still(tab)
    tab.view.setTransform(QTransform.fromScale(2.0, 2.0))
    tab.view.centerOn(QPointF(110, 180))

    drag_card(tab, mover, QPoint(-240 + miss_px, 0))

    if snaps:
        assert mover.pos().x() == pytest.approx(0, abs=1e-9)
    else:
        assert mover.pos().x() == pytest.approx(miss_px / 2.0, abs=1)


def test_a_group_snaps_by_the_card_under_the_cursor_and_keeps_its_shape(snapping, qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 4)
    tab.scene.clearSelection()
    still, grabbed, second, third = sorted(canvas_cards(tab), key=lambda card: card.pos().x())
    still.setPos(0, 0)
    for card, at in ((grabbed, (120, 200)), (second, (290, 260)), (third, (430, 190))):
        card.setPos(*at)
        card.setSelected(True)
    tab.view.centerOn(QPointF(110, 180))
    shape = [second.pos() - grabbed.pos(), third.pos() - grabbed.pos()]

    drag_card(tab, grabbed, QPoint(-120 + 3, 0))

    assert grabbed.pos().x() == pytest.approx(0, abs=1e-9)
    assert [second.pos() - grabbed.pos(), third.pos() - grabbed.pos()] == shape


def test_a_guide_shows_while_a_snap_holds_and_leaves_the_scene_on_release(snapping, qtbot):
    tab = make_tab(qtbot)
    _, mover = mover_and_still(tab)

    end = press_and_move(tab, mover, QPoint(-120 + 3, 0))

    assert tab.guide_item.scene() is tab.scene
    assert tab.guide_item.guides()
    assert all(not isinstance(card, GuideItem) for card in tab.cards())

    release(tab, end)

    assert tab.guide_item.scene() is None
    assert all(not isinstance(item, GuideItem) for item in tab.scene.items())


def test_a_card_that_lets_go_of_a_snap_draws_no_guide(snapping, qtbot):
    tab = make_tab(qtbot)
    _, mover = mover_and_still(tab)

    end = press_and_move(tab, mover, QPoint(-120 + 3, 0))
    move_to(tab, end + QPoint(-30, 0))

    assert tab.guide_item.guides() == ()
    release(tab, end + QPoint(-30, 0))


def test_a_snap_engaging_does_not_lean_the_cards(snapping, qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    tab.scene.clearSelection()
    still, grabbed, carried = sorted(canvas_cards(tab), key=lambda card: card.pos().x())
    still.setPos(0, 0)
    grabbed.setPos(120, 200)
    carried.setPos(300, 220)
    grabbed.setSelected(True)
    carried.setSelected(True)
    tab.view.centerOn(QPointF(110, 180))

    start = tab.view.mapFromScene(grabbed.mapToScene(QPointF(20.0, 80.0)))
    at = start + QPoint(-120 + 3, 0)
    send_mouse(tab, QMouseEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    move_to(tab, at, ALT)
    before = [(card.pos(), QPointF(card._visual_pos)) for card in (grabbed, carried)]

    # Letting go of Alt without moving engages the snap: the cards jump, the hand doesn't
    move_to(tab, at)

    assert grabbed.pos().x() == pytest.approx(0, abs=1e-9)
    for card, (pos, visual) in zip((grabbed, carried), before, strict=True):
        jump = card.pos() - pos
        assert not jump.isNull()
        assert card._visual_pos - visual == jump
    release(tab, at)


def test_the_guides_take_the_tabs_gilt_on_either_ground(qtbot):
    tab = make_tab(qtbot)
    tab.set_ground(QColor("#202020"))
    assert tab.guide_item.tone() == QColor(GILT_ON_DARK)
    tab.set_ground(QColor("#f0f0f0"))
    assert tab.guide_item.tone() == QColor(GILT_ON_LIGHT)


def test_a_guide_paints_a_gilt_core_over_its_halo(qtbot):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QGraphicsScene

    from tarot_canvas.ui.canvas.guides import Guide

    scene = QGraphicsScene()
    item = GuideItem()
    item.set_tone(QColor(GILT_ON_DARK))
    item.set_guides((Guide(10, 50, 90, 50, ticks=True),))
    scene.addItem(item)
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor("#808080"))
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 100, 100), QRectF(0, 0, 100, 100))
    painter.end()

    column = [image.pixelColor(50, y) for y in range(44, 57)]
    grey = QColor("#808080").lightness()
    assert any(c.red() > 200 and c.green() > 180 for c in column)  # a gilt core
    assert any(c.lightness() < grey for c in column)  # flanked by a dark halo
    assert image.pixelColor(50, 20) == QColor("#808080")  # and nothing off the line


def test_zooming_in_sharpens_the_cards_on_screen_and_only_those(qtbot, tmp_path):
    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtGui import QImage

    image = QImage(1200, 2000, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    path = str(tmp_path / "art.png")
    image.save(path)

    tab = make_tab(qtbot)
    tab.add_specific_card({"id": "near", "image": path}, at=QPointF(0, 0))
    tab.add_specific_card({"id": "far", "image": path}, at=QPointF(50000, 0))
    near, far = sorted(canvas_cards(tab), key=lambda card: card.pos().x())
    tab.view.centerOn(near)

    tab.view.zoom_by_from_center(3.0)
    tab.view.centerOn(near)
    dpr = tab.view.viewport().devicePixelRatioF()
    qtbot.waitUntil(lambda: near.detail() >= min(4, round(3 * dpr)), timeout=5000)

    assert far.detail() <= max(1, round(dpr))
    QThreadPool.globalInstance().waitForDone()
    qtbot.wait(1100)


class CountingTabWidget(DocumentTabs):
    def __init__(self):
        super().__init__()
        self.icons_set = 0

    def setTabIcon(self, index, icon):
        self.icons_set += 1
        super().setTabIcon(index, icon)


def is_plain(tabs):
    page = tabs.widget(0)
    return (
        isinstance(page._tab_icon, CanvasIcon)
        and tabs.tabIcon(0).cacheKey() == page._tab_icon.cacheKey()
    )


def test_the_tab_icon_maps_the_spread(qtbot):
    tabs = CountingTabWidget()
    qtbot.addWidget(tabs)
    tab = CanvasTab()
    tabs.addTab(tab, "Canvas")
    assert tabs.icons_set == 1
    tabs.show()
    assert is_plain(tabs)

    add_cards(tab, 1)
    card = canvas_cards(tab)[0]
    qtbot.waitUntil(lambda: tabs.icons_set == 2)
    assert not is_plain(tabs)

    card.setPos(card.pos() + QPointF(1, 0))
    qtbot.wait(10)
    assert tabs.icons_set == 2

    tab.scene.removeItem(card)
    qtbot.waitUntil(lambda: tabs.icons_set == 3)
    assert is_plain(tabs)
    qtbot.wait(1100)


@pytest.fixture
def minimap_unset():
    get_settings().remove(CANVAS_TAB_MINIMAP_KEY)
    yield
    get_settings().remove(CANVAS_TAB_MINIMAP_KEY)


def test_the_minimap_setting_turns_the_tab_icon_plain(qtbot, minimap_unset):
    get_settings().setValue(CANVAS_TAB_MINIMAP_KEY, False)
    tabs = DocumentTabs()
    qtbot.addWidget(tabs)
    tab = CanvasTab()
    tabs.addTab(tab, "Canvas")
    tabs.show()
    add_cards(tab, 1)
    qtbot.waitUntil(lambda: is_plain(tabs))
    assert not tab.tab_minimap

    get_settings().setValue(CANVAS_TAB_MINIMAP_KEY, True)
    tab.apply_background_settings()
    qtbot.waitUntil(lambda: not is_plain(tabs))
    qtbot.wait(1100)


def test_the_rotate_command_turns_a_card_and_leaves_it_upright(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = only_card(tab)

    tab.commands["canvas.rotate"].trigger()
    assert card.orient == 90
    assert not card.is_reversed()

    tab.commands["canvas.rotate"].trigger()
    assert card.orient == 180
    assert not card.is_reversed()


def card_centre(card):
    return card.sceneBoundingRect().center()


def menu_layout(menu):
    """A menu's entries, as command ids, submenus and None for a separator."""
    rows = []
    for action in menu.actions():
        if action.isSeparator():
            rows.append(None)
        elif action.menu() is not None:
            rows.append("swap")
        else:
            rows.append(action.objectName() or "open")
    return rows


def test_right_clicking_an_unselected_card_selects_only_it(qtbot, stub_deck_manager, minimal_deck):
    tab = make_tab(qtbot)
    other = tab.add_specific_card(minimal_deck.get_all_cards()[1], card_deck=minimal_deck)
    first = tab.add_specific_card(
        minimal_deck.get_all_cards()[0], card_deck=minimal_deck, at=other.pos() + QPointF(900, 0)
    )
    first.setSelected(False)
    other.setSelected(True)

    menu = tab.card_menu(card_centre(first))

    assert tab.selected_cards() == [first]
    assert menu_layout(menu) == [
        "open",
        None,
        "canvas.flip",
        "canvas.rotate",
        "swap",
        None,
        "canvas.delete",
    ]


def test_right_clicking_inside_a_selection_keeps_it(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    card = tab.cards()[1]

    menu = tab.card_menu(card_centre(card))

    assert len(tab.selected_cards()) == 3
    assert "swap" not in menu_layout(menu)


def test_right_clicking_the_empty_canvas_builds_no_menu(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    assert tab.card_menu(QPointF(5000, 5000)) is None
    assert len(tab.selected_cards()) == 1


def test_the_menu_is_for_the_topmost_card(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 2)
    below, above = tab.cards()
    above.setPos(below.pos())
    above.setZValue(below.zValue() + 10)
    tab.scene.clearSelection()

    tab.card_menu(card_centre(above))

    assert tab.selected_cards() == [above]


def test_a_context_menu_leaves_no_press_behind(qtbot, monkeypatch):
    # The menu swallows the release, which would leave the card lifted and grabbing the mouse
    monkeypatch.setattr("tarot_canvas.ui.tabs.canvas_tab.QMenu.exec", lambda *_: None)
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = only_card(tab)
    pos = tab.view.mapFromScene(card_centre(card))

    send_mouse(tab, QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.RightButton)
    assert tab.scene.mouseGrabberItem() is card

    QApplication.sendEvent(
        tab.view.viewport(),
        QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, pos, tab.view.viewport().mapToGlobal(pos)
        ),
    )

    assert tab.scene.mouseGrabberItem() is None
    assert not card._pressed


def swap_rows(menu):
    swap = next(action.menu() for action in menu.actions() if action.menu() is not None)
    return swap, swap.actions()


def test_swap_lists_the_decks_that_have_the_card(qtbot, minimal_deck, other_deck):
    tab = make_tab(qtbot)
    card = tab.add_specific_card(minimal_deck.get_all_cards()[0], card_deck=minimal_deck)

    swap, (here, there) = swap_rows(tab.card_menu(card_centre(card)))

    assert swap.isEnabled()
    assert here.isChecked() and not here.isEnabled()
    assert there.isEnabled() and not there.isChecked()


def test_swap_is_disabled_with_no_other_deck(qtbot, stub_deck_manager, minimal_deck):
    tab = make_tab(qtbot)
    card = tab.add_specific_card(minimal_deck.get_all_cards()[0], card_deck=minimal_deck)

    swap, rows = swap_rows(tab.card_menu(card_centre(card)))

    assert not swap.isEnabled()
    assert len(rows) == 1


def test_swap_keeps_the_card_exactly_where_it_lay(qtbot, minimal_deck, other_deck):
    tab = make_tab(qtbot)
    cards = minimal_deck.get_all_cards()
    tab.add_specific_card(cards[1], card_deck=minimal_deck)
    card = tab.add_specific_card(cards[0], card_deck=minimal_deck, at=QPointF(900, 0))
    card.set_orient(90)
    card.set_reversed(True)
    tab.on_bring_to_front()
    place, stack = card.pos(), card.zValue()

    _, (_, there) = swap_rows(tab.card_menu(card_centre(card)))
    there.trigger()

    swapped = tab.selected_cards()
    assert len(swapped) == 1
    assert len(tab.cards()) == 2
    swapped = swapped[0]
    assert swapped is not card
    assert card.scene() is None
    assert swapped.deck is other_deck
    assert swapped.pos() == place
    assert swapped.zValue() == stack
    assert swapped.orient == 90
    assert swapped.is_reversed()


def test_swap_turns_nothing_on_screen(qtbot, minimal_deck, other_deck):
    tab = make_tab(qtbot)
    card = tab.add_specific_card(minimal_deck.get_all_cards()[0], card_deck=minimal_deck)
    card.set_orient(90)
    card.settle_motion()

    swapped = tab.swap_card(card, other_deck, other_deck.get_card_by_id(card.card_data["id"]))

    assert swapped.motion.orient_lag == 0.0
    assert swapped.motion.drawn_angle() == card.motion.drawn_angle()
    assert swapped.marks.level == 1.0


def test_a_card_taking_anothers_place_keeps_its_centre_when_the_art_differs(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    card = only_card(tab)
    card.set_orient(90)
    wider = QPixmap(140, 200)
    wider.fill()
    replacement = DraggableCardItem(wider, {"id": "card-0"})

    replacement.take_place_of(card)

    assert (
        replacement.pos() + replacement.boundingRect().center()
        == card.pos() + card.boundingRect().center()
    )


def slots_and_cards(tab):
    """Two slots and two cards the same size, each pair in the same starting places."""
    size = tab.add_slot(1, "p1", at=QPointF(0, 0)).pixmap().size()
    tab.add_slot(2, "p2", at=QPointF(150, 40))
    slots = list(tab.cards())
    pixmap = QPixmap(size)
    pixmap.fill()
    cards = []
    for slot in slots:
        card = DraggableCardItem(pixmap, {"id": slot.position_id}, tab)
        card.setPos(slot.pos())
        tab.scene.addItem(card)
        cards.append(card)
    return slots, cards


def select_only(tab, items):
    tab.scene.clearSelection()
    for item in items:
        item.setSelected(True)


def test_add_slot_puts_slots_among_the_cards(qtbot):
    tab = make_tab(qtbot)
    first = tab.add_slot(1, "p1", at=QPointF(10, 20), label="Past", meaning="Before")
    second = tab.add_slot(2, "p2")
    assert tab.cards() == (first, second)
    assert first.sceneBoundingRect().center() == QPointF(10, 20)
    assert (first.number, first.position_id, first.label, first.meaning, first.deck) == (
        1,
        "p1",
        "Past",
        "Before",
        None,
    )
    qtbot.wait(1100)


def test_a_slot_given_a_place_does_not_pop_in(qtbot):
    tab = make_tab(qtbot)
    assert tab.add_slot(1, "p1", at=QPointF(0, 0)).motion.lift == LIFT_REST
    qtbot.wait(1100)


@pytest.mark.parametrize(
    "arrange",
    [
        lambda tab, items: align_items_vertically(items, "top"),
        lambda tab, items: align_items_horizontally(items, "left"),
        lambda tab, items: distribute_items_horizontally(items),
        lambda tab, items: tab.on_bring_to_front(),
        lambda tab, items: tab.on_rotate_card(),
        lambda tab, items: arrange_items_on_arc(tab.arrange_order(items)),
    ],
)
def test_a_slot_arranges_exactly_as_a_card_does(qtbot, arrange):
    tab = make_tab(qtbot)
    slots, cards = slots_and_cards(tab)
    for group in (slots, cards):
        select_only(tab, group)
        arrange(tab, group)
    assert [s.pos() for s in slots] == [c.pos() for c in cards]
    assert [s.orient for s in slots] == [c.orient for c in cards]
    assert slots[0].zValue() < slots[1].zValue()
    qtbot.wait(1100)


def test_flip_leaves_a_slot_alone(qtbot):
    tab = make_tab(qtbot)
    slot = tab.add_slot(1, "p1", at=QPointF(0, 0))
    before = slot.transform()
    tab.on_flip_card()
    assert not slot.is_reversed()
    assert slot.transform() == before
    qtbot.wait(1100)


def test_a_selection_with_a_slot_in_it_cannot_be_copied_or_cut(qtbot):
    tab = make_tab(qtbot)
    slots, cards = slots_and_cards(tab)
    cards[0].deck = object()
    select_only(tab, [cards[0]])
    assert tab.can_copy_card()

    for selection in ([slots[0]], [slots[0], cards[0]]):
        select_only(tab, selection)
        assert not tab.can_copy_card()
        assert not tab.can_cut_card()
    qtbot.wait(1100)


def test_a_slot_opens_nothing(qtbot):
    tab = make_tab(qtbot)
    slot = tab.add_slot(1, "p1", at=QPointF(0, 0))
    requests = []
    tab.navigation_requested.connect(lambda *args: requests.append(args))
    double_click(tab, tab.view.mapFromScene(slot.sceneBoundingRect().center()))
    tab.open_card_view(slot)
    assert requests == []
    qtbot.wait(1100)


def test_a_slots_menu_offers_no_deck_to_swap_to(qtbot):
    tab = make_tab(qtbot)
    slot = tab.add_slot(1, "p1", at=QPointF(0, 0))
    menu = tab.card_menu(slot.sceneBoundingRect().center())
    qtbot.addWidget(menu)
    _, rows = swap_rows(menu)
    assert rows == []
    qtbot.wait(1100)


def test_zooming_sharpens_a_slot_without_the_loader(qtbot, monkeypatch):
    from tarot_canvas.ui.canvas import detail

    monkeypatch.setattr(detail, "art_loader", lambda: pytest.fail("a slot loaded art"))
    tab = make_tab(qtbot)
    slot = tab.add_slot(1, "p1", at=QPointF(0, 0))
    size = slot.boundingRect().size()
    tab.view.centerOn(slot)

    tab.view.zoom_by_from_center(4.0)
    tab.view.centerOn(slot)
    qtbot.waitUntil(lambda: slot.detail() >= 4, timeout=5000)

    assert slot.pixmap().devicePixelRatio() == slot.detail()
    assert slot.boundingRect().size() == size
    qtbot.wait(1100)


def test_renumbering_a_slot_repaints_it_at_its_level(qtbot):
    tab = make_tab(qtbot)
    slot = tab.add_slot(1, "p1", at=QPointF(0, 0))
    slot.set_detail(3)
    before = slot.pixmap().toImage()
    slot.set_number(2)
    assert slot.pixmap().devicePixelRatio() == 3
    assert slot.pixmap().toImage() != before
    qtbot.wait(1100)


def test_the_tab_icon_paints_a_slot_in_its_colour(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    tab.add_slot(1, "p1", at=QPointF(500, 0))
    tab.tab_minimap = True
    tab.refresh_tab_icon()
    (card, slot) = sorted(tab._tab_marks, key=lambda mark: mark.x)
    assert card.colour == CARD_COLOURS["default"]
    assert slot.colour == SLOT_COLOUR
    qtbot.wait(1100)


# -- turning by the wheel

CTRL = Qt.KeyboardModifier.ControlModifier
CTRL_ALT = CTRL | Qt.KeyboardModifier.AltModifier


def wheel(tab, viewport_pos, delta, modifiers=CTRL):
    """Turn the wheel over viewport_pos; delta is (x, y) angleDelta."""
    viewport = tab.view.viewport()
    event = QWheelEvent(
        QPointF(viewport_pos),
        QPointF(viewport.mapToGlobal(viewport_pos)),
        QPoint(),
        QPoint(*delta),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(viewport, event)


def over(tab, item):
    return tab.view.mapFromScene(item.sceneBoundingRect().center())


def cards(tab):
    return sorted(
        (item for item in tab.scene.items() if isinstance(item, DraggableCardItem)),
        key=lambda item: item.pos().x(),
    )


def zoom(tab):
    return tab.view.transform().m11()


def test_ctrl_wheel_over_a_selected_card_turns_the_whole_selection(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    first, second, third = cards(tab)
    third.setSelected(False)
    before = zoom(tab)

    with qtbot.waitSignal(tab.layout_changed):
        wheel(tab, over(tab, first), (0, 120))

    assert [card.orient for card in (first, second, third)] == [15, 15, 0]
    assert zoom(tab) == before


def test_ctrl_wheel_over_an_unselected_card_turns_only_that_card(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    first, second, third = cards(tab)
    third.setSelected(False)

    wheel(tab, over(tab, third), (0, 120))

    assert [card.orient for card in (first, second, third)] == [0, 0, 15]


def test_wheel_towards_the_user_turns_anticlockwise(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)

    wheel(tab, over(tab, card), (0, -120))

    assert card.orient == 345


def test_a_coarse_notch_lands_on_a_multiple_of_15(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)
    card.set_orient(7)

    wheel(tab, over(tab, card), (0, 120))

    assert card.orient == 15


@pytest.mark.parametrize(
    "orient,notches,turned",
    [(7, 1, 15), (7, -1, 0), (15, 1, 30), (15, -1, 0), (0, -1, -15), (7, 2, 30), (44.9, 1, 45)],
)
def test_coarse_turns_snap_to_15(orient, notches, turned):
    assert wheel_turn(orient, notches, fine=False) == turned


def test_ctrl_alt_turns_by_one_degree_from_a_sideways_delta(qtbot):
    """Qt delivers an Alt-held wheel as angleDelta().x()"""
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)
    card.set_orient(7)

    wheel(tab, over(tab, card), (120, 0), CTRL_ALT)

    assert card.orient == 8


def test_a_fine_wheel_turns_one_step_per_notch(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)
    pos = over(tab, card)

    for _ in range(3):
        wheel(tab, pos, (0, 30))
    assert card.orient == 0
    wheel(tab, pos, (0, 30))
    assert card.orient == 15


def test_a_plain_wheel_over_a_card_still_zooms(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)
    before = zoom(tab)

    wheel(tab, over(tab, card), (0, 120), Qt.KeyboardModifier.NoModifier)

    assert zoom(tab) > before
    assert card.orient == 0


def test_ctrl_wheel_over_empty_canvas_zooms(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)
    before = zoom(tab)

    wheel(tab, QPoint(5, 5), (0, 120))

    assert zoom(tab) > before
    assert card.orient == 0


def test_a_turn_keeps_a_reversed_card_reversed(qtbot):
    tab = make_tab(qtbot)
    add_cards(tab, 1)
    (card,) = cards(tab)
    card.set_reversed(True)

    wheel(tab, over(tab, card), (0, 120))

    assert (card.orient, card.reversed) == (15, True)
