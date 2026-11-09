import pytest
from PyQt6.QtGui import QColor

from tarot_canvas.settings import GROUND_HUE_KEY, get_settings
from tarot_canvas.ui.canvas.ground import (
    GRADIENT_STOPS,
    GROUND_HUE_DEFAULT,
    GROUND_HUES,
    ground_hue_id,
)
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
