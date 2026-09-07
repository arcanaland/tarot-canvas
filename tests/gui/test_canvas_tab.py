from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QEnterEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from tarot_canvas.settings import MOTION_LEVEL_KEY, get_settings
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab


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
    """State the precondition rather than inherit it.

    QSettings is not reliably isolated between tests in this suite (the 2-arg QSettings
    resolves a NativeFormat path once per process), so any test whose behaviour depends
    on the motion level has to set it.
    """
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
    """An idle window must genuinely idle: no visible canvas, no timer."""
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
    """A gated canvas is inert, not merely slow: no tilt, no drift, and so no repaints.

    The gate is shut here because an offscreen test window is never the active one, which
    is the same path a backgrounded window takes.
    """
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]
    # add_cards selects what it adds, and selection now carries a resting lift of its own
    # — see test_selection_lifts_the_card_off_the_felt. Rest is the unselected state.
    tab.scene.clearSelection()

    for frame in range(120):
        tab._advance_motion(0.5 + frame / 60.0, 1.0 / 60.0)

    assert tab.ambient_gain == 0.0  # snapped, not merely small
    assert all(card.transform().isIdentity() for card in cards)
    # Exactly identity, so the snapshot stops changing and the repaints stop with it.
    assert not any(card.advance_motion(3.0, 1.0 / 60.0, 0.0) for card in cards)


def test_cards_drift_once_ambient_is_allowed(qtbot):
    """The complement of the test above, and the only automated check that drift exists."""
    set_motion_level("Full")
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]

    for card in cards:
        card.advance_motion(0.0, 1.0 / 60.0, 1.0)
    first = [card.transform() for card in cards]
    assert not any(transform.isIdentity() for transform in first)
    assert not any(transform.isAffine() for transform in first)  # tilt, not a 2-D spin

    # Different cards, different phases: they must not move as one block.
    for card in cards:
        card.advance_motion(2.0, 1.0 / 60.0, 1.0)
    deltas = [
        card.transform().dx() - transform.dx() for card, transform in zip(cards, first, strict=True)
    ]
    assert len(set(deltas)) == len(deltas)


def test_every_card_gets_its_own_depth(qtbot):
    """Cards used to share a z-value of 0 and fall back to insertion order.

    That made "bring to front" a no-op for a second card — both landed on 100 — and left
    no ordering for a shadow to sit inside, which is why a stacked card cast onto nothing.
    """
    tab = make_tab(qtbot)
    add_cards(tab, 3)
    cards = [i for i in tab.scene.items() if isinstance(i, DraggableCardItem)]
    for card in cards:
        card.setZValue(tab.take_top_z())
    depths = [card.zValue() for card in cards]

    assert len(set(depths)) == len(depths)


def test_restacking_a_selection_keeps_its_internal_order(qtbot):
    """Raising three cards together must not shuffle them relative to one another."""
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
    """The middle rung of the ladder finally means something.

    TASK-028 shipped the Off/Reactive/Full combo with nothing plugged into the reactive
    tier, so two of its three entries behaved identically. Reactive keeps the clock and
    the response to the pointer, and drops only the ambient drift.
    """
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
    """Selection is reinforced by height rather than by a drawn outline.

    Qt's own dashed rectangle is a flat annotation over a card that now has perspective,
    and the corner brackets that would replace it cannot be painted from Python without
    crashing this suite (TASK-028). A resting lift and the shadow separation that follows
    from it say "picked up" without painting anything.
    """
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
    assert card.orient == 180
    assert card.card_data["reversed"] is True
    assert not card.transform().isIdentity()  # the channel really reaches the transform

    tab.on_flip_card()
    assert card.orient == 0
    assert card.card_data["reversed"] is False

    tab.on_rotate_card()
    assert card.orient == 90
    tab.on_rotate_card()
    tab.on_rotate_card()
    tab.on_rotate_card()
    assert card.orient == 0  # wraps rather than accumulating


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
