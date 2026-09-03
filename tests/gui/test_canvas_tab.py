from PyQt6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PyQt6.QtGui import QEnterEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

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


def make_tab(qtbot):
    QSettings("ArcanaLand", "TarotCanvas").setValue("appearance/enable_animations", False)
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
