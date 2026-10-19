"""A card's reversal is its own flag, apart from how far it is turned"""

import pytest
from PyQt6.QtGui import QPixmap

from tarot_canvas.ui.canvas.card_item import DraggableCardItem


class StubTab:
    def reactive_is_allowed(self):
        return True


def make_card(reactive=False, reversed=False):
    pixmap = QPixmap(120, 200)
    pixmap.fill()
    tab = StubTab() if reactive else None
    return DraggableCardItem(pixmap, {"id": "major_arcana/hermit"}, tab, reversed=reversed)


@pytest.mark.parametrize(("reversed", "drawn"), [(False, 90.0), (True, 270.0)])
def test_a_sideways_card_is_reversed_only_by_its_flag(qapp, reversed, drawn):
    item = make_card(reversed=reversed)

    item.set_orient(90)

    assert item.orient == 90
    assert item.is_reversed() is reversed
    assert item.motion.drawn_angle() == drawn


def test_the_shadow_turns_with_the_drawn_card(qapp):
    item = make_card(reversed=True)

    item.set_orient(90)

    assert item.shadow.rotation() == item.motion.drawn_angle() == 270.0


def test_a_flip_leaves_the_rotation_and_animates_a_half_turn(qapp):
    item = make_card(reactive=True)
    item.set_orient(90)
    item.motion.orient_lag = 0.0

    item.set_reversed(True)

    assert item.orient == 90
    assert item.is_reversed()
    assert abs(item.motion.orient_lag) == pytest.approx(180.0)
    # Drawn where it was a moment ago, trailing toward 270
    assert item.motion.drawn_angle() % 360 == pytest.approx(90.0)


def test_a_reversed_card_turns_without_righting_itself(qapp):
    item = make_card(reactive=True, reversed=True)

    item.set_orient(90)

    assert item.is_reversed()
    assert item.motion.orient_lag == pytest.approx(-90.0)
