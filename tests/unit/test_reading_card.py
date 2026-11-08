from PyQt6.QtCore import QPointF

from tarot_canvas.settings import (
    READINGS_REVERSALS_KEY,
    get_readings_reversals,
    get_settings,
    set_readings_reversals,
)
from tarot_canvas.ui.canvas.motion import MotionChannels
from tarot_canvas.ui.canvas.reading_card import ReadingMotion

W, H = 100.0, 170.0


def test_a_reading_card_unturned_is_drawn_as_any_card():
    assert ReadingMotion(orient=90.0).compose(W, H) == MotionChannels(orient=90.0).compose(W, H)


def test_the_turn_narrows_the_card_about_its_own_upright_axis():
    edge_on = ReadingMotion(flip=89.9).compose(W, H)
    left, right = edge_on.map(QPointF(0, H / 2)), edge_on.map(QPointF(W, H / 2))

    assert abs(right.x() - left.x()) < 1.0
    assert abs(left.x() - W / 2) < 1.0


def test_a_reversed_face_turns_the_other_way_so_it_doesnt_pop():
    upright = ReadingMotion(flip=-45.0)
    reversed = ReadingMotion(flip=-45.0, reversed=True)

    assert upright.face_turn() == -45.0
    assert reversed.face_turn() == 45.0


def test_a_turn_part_way_is_not_at_rest():
    assert ReadingMotion().at_rest()
    assert not ReadingMotion(flip=10.0).at_rest()
    assert ReadingMotion(flip=10.0).snapshot() != ReadingMotion().snapshot()


def test_reversals_default_on_and_keep_the_last_choice():
    settings = get_settings()
    assert get_readings_reversals(settings) is True

    set_readings_reversals(False, settings)

    assert get_readings_reversals(settings) is False
    assert settings.value(READINGS_REVERSALS_KEY, type=bool) is False
