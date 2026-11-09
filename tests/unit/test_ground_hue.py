import math

import pytest
from PyQt6.QtGui import QColor

from tarot_canvas.settings import GROUND_HUE_KEY, get_settings
from tarot_canvas.ui.canvas.ground import (
    GRADIENT_STOPS,
    GROUND_HUE_DEFAULT,
    GROUND_HUES,
    SHADOW_OPACITY_ON_LIGHT,
    _decode,
    _to_oklab,
    ground_hue_id,
    shadow_for_ground,
)
from tarot_canvas.ui.canvas.motion import SHADOW_OPACITY
from tarot_canvas.ui.strings import PREFERENCES


def test_the_default_preset_is_the_ground_everyone_already_has():
    hue = GROUND_HUES[GROUND_HUE_DEFAULT]
    assert [c.name() for c in hue.swirl] == ["#50396b", "#301f46", "#8671a5"]
    assert [(p, c.getRgb()[:3]) for p, c in hue.aura_stops()] == [
        (0.0, (50, 30, 80)),
        (0.5, (30, 18, 60)),
        (1.0, (15, 10, 30)),
    ]
    assert hue.aura_stops() == GRADIENT_STOPS


def test_every_preset_has_six_colours_and_a_name():
    for hue_id, hue in GROUND_HUES.items():
        assert len(hue.swirl) == 3
        assert len(hue.aura) == 3
        assert all(isinstance(c, QColor) and c.isValid() for c in (*hue.swirl, *hue.aura))
        assert f"hue_{hue_id}" in PREFERENCES


@pytest.mark.parametrize("stored", [None, "", "no-such-hue", 3])
def test_a_stored_hue_we_dont_have_reads_as_the_default(stored):
    settings = get_settings()
    if stored is not None:
        settings.setValue(GROUND_HUE_KEY, stored)
    assert ground_hue_id(settings) == GROUND_HUE_DEFAULT


def test_a_stored_hue_is_read_back():
    settings = get_settings()
    settings.setValue(GROUND_HUE_KEY, GROUND_HUE_DEFAULT)
    assert ground_hue_id(settings) == GROUND_HUE_DEFAULT


def test_aura_is_the_gradients_new_label():
    assert PREFERENCES["background_gradient"] == "Aura"


def _oklab(color):
    rgb = tuple(_decode(c) for c in (color.redF(), color.greenF(), color.blueF()))
    return _to_oklab(rgb)


def test_a_shadow_on_a_warm_ground_keeps_its_hue_and_gains_chroma():
    ground = QColor("#eae0cb")
    tone, _ = shadow_for_ground(ground)
    ground_l, ground_a, ground_b = _oklab(ground)
    tone_l, tone_a, tone_b = _oklab(tone)

    assert tone_l < ground_l / 2
    assert math.hypot(tone_a, tone_b) > math.hypot(ground_a, ground_b)
    hue_shift = math.atan2(tone_b, tone_a) - math.atan2(ground_b, ground_a)
    assert abs(math.remainder(hue_shift, math.tau)) < 0.1


def test_a_shadow_on_grey_stays_grey():
    tone, _ = shadow_for_ground(QColor("#808080"))
    assert tone.red() == tone.green() == tone.blue()


def test_a_light_ground_takes_a_fainter_shadow_than_a_dark_one():
    _, on_dark = shadow_for_ground(QColor("#1e123c"))
    _, on_mid = shadow_for_ground(QColor("#808080"))
    _, on_light = shadow_for_ground(QColor("#eae0cb"))

    assert on_dark == SHADOW_OPACITY
    assert on_light == pytest.approx(SHADOW_OPACITY_ON_LIGHT)
    assert on_light < on_mid < on_dark
