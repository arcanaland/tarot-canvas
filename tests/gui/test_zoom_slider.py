"""A slider between zoom-out and zoom-in buttons"""

import pytest

from tarot_canvas.ui.widgets.zoom_slider import ZoomSlider

KEYS = ("small", "medium", "large")


@pytest.fixture
def zoom(qtbot):
    widget = ZoomSlider(KEYS, "Cover size", "medium")
    qtbot.addWidget(widget)
    return widget


def test_the_buttons_step_and_stop_at_the_ends(zoom, qtbot):
    zoom.set_key("medium")
    with qtbot.waitSignal(zoom.key_changed) as changed:
        zoom.in_button.click()
    assert changed.args == ["large"]
    assert not zoom.in_button.isEnabled()

    zoom.out_button.click()
    zoom.out_button.click()
    assert zoom.key() == "small"
    assert not zoom.out_button.isEnabled()
    assert zoom.in_button.isEnabled()


def test_setting_a_key_says_nothing(zoom, qtbot):
    with qtbot.assertNotEmitted(zoom.key_changed):
        zoom.set_key("large")
    assert zoom.key() == "large"
    assert not zoom.in_button.isEnabled()


def test_an_unknown_key_is_ignored(zoom):
    zoom.set_key("small")
    zoom.set_key("enormous")
    assert zoom.key() == "small"


def test_the_buttons_say_what_view_zoom_says(zoom):
    assert zoom.in_button.toolTip() == "Zoom In"
    assert zoom.out_button.toolTip() == "Zoom Out"
    assert zoom.slider.accessibleName() == "Cover size"
