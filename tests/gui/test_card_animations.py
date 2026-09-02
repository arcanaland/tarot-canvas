from PyQt6 import sip
from PyQt6.QtCore import QAbstractAnimation, QSettings
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsScene

from tarot_canvas.ui.canvas.card_item import DraggableCardItem


def make_card():
    pixmap = QPixmap(100, 160)
    pixmap.fill()
    return DraggableCardItem(pixmap, {"id": "card"})


def test_animation_does_not_drive_a_deleted_card(qtbot):
    """A tick after the card's C++ side is gone must not raise into the event loop."""
    QSettings("ArcanaLand", "TarotCanvas").setValue("appearance/enable_animations", False)
    card = make_card()
    controller = card.anim_controller

    scene = QGraphicsScene()
    scene.addItem(card)
    sip.delete(scene)  # takes the item with it, as tearing down a canvas tab does
    assert sip.isdeleted(card)

    controller.rotation = 12.0  # would raise RuntimeError without the guard
    controller.scale = 1.1
    assert controller.card_item is None


def test_removing_a_card_from_the_scene_stops_its_animation(qtbot):
    QSettings("ArcanaLand", "TarotCanvas").setValue("appearance/enable_animations", True)
    card = make_card()
    scene = QGraphicsScene()
    scene.addItem(card)
    card.start_animations()
    assert card.rotation_anim.state() == QAbstractAnimation.State.Running

    scene.removeItem(card)
    assert card.rotation_anim.state() == QAbstractAnimation.State.Stopped
