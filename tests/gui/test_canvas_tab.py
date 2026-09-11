import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PyQt6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QEnterEvent,
    QMouseEvent,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication

from tarot_canvas.settings import (
    BACKGROUND_COLOR_KEY,
    BACKGROUND_STYLE_KEY,
    MOTION_LEVEL_KEY,
    get_settings,
)
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, GILT_ON_LIGHT
from tarot_canvas.ui.card_transfer import card_mime_data, copy_card_to_clipboard
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
    add_cards(tab, 1)
    card = canvas_cards(tab)[0]
    near = card.marks.corners[0].path().boundingRect()

    tab.view.zoom_by_from_center(0.25)

    assert card.view_scale() == pytest.approx(0.25)
    assert card.marks.corners[0].path().boundingRect().width() > near.width()

    tab.on_reset_view()

    assert card.view_scale() == 1.0
    assert card.marks.corners[0].path().boundingRect() == near


@pytest.mark.parametrize(
    ("style", "tone"),
    [("Gradient", GILT_ON_DARK), ("Checkerboard", GILT_ON_LIGHT)],
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
    settings.setValue(BACKGROUND_STYLE_KEY, "Solid Color")
    settings.setValue(BACKGROUND_COLOR_KEY, "#ffffff")
    settings.sync()

    tab.apply_background_settings()

    assert tab.gilt == QColor(GILT_ON_LIGHT)
