import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform

from tarot_canvas.ui.canvas.reading_marks import badge_centre

CARD = QRectF(0, 0, 120, 200)
REACH = 10.0


def corners_of(transform):
    return [
        transform.map(point)
        for point in (CARD.topLeft(), CARD.topRight(), CARD.bottomRight(), CARD.bottomLeft())
    ]


def laid(angle, reversed=False, mirrored=False):
    """A card at (300, 200), turned about its middle as the canvas turns it"""
    t = QTransform().translate(300, 200).translate(60, 100).rotate(angle)
    if reversed:
        t.rotate(180)
    if mirrored:
        t.scale(-1, 1)
    return t.translate(-60, -100)


def close(a, b):
    return abs(a.x() - b.x()) < 1e-6 and abs(a.y() - b.y()) < 1e-6


def test_upright_card_keeps_the_old_inset():
    assert close(badge_centre(corners_of(laid(0)), 0, REACH), QPointF(310, 210))


@pytest.mark.parametrize("angle", [-25, -10, 15, 30])
def test_a_tilted_card_carries_its_badge_on_its_own_corner(angle):
    expected = laid(angle).map(QPointF(REACH, REACH))
    assert close(badge_centre(corners_of(laid(angle)), angle, REACH), expected)


@pytest.mark.parametrize("angle", [-20, 0, 20])
def test_a_reversed_card_keeps_the_badge_top_left_as_laid(angle):
    expected = laid(angle).map(QPointF(REACH, REACH))
    corners = corners_of(laid(angle, reversed=True))
    assert close(badge_centre(corners, angle, REACH), expected)


def test_a_card_mid_turn_does_not_jump_corners():
    corners = corners_of(laid(15, mirrored=True))
    assert close(badge_centre(corners, 15, REACH), laid(15).map(QPointF(REACH, REACH)))
