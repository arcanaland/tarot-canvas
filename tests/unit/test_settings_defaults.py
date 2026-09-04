from tarot_canvas.settings import (
    ANIMATION_INTENSITY_DEFAULT,
    ANIMATIONS_ENABLED_DEFAULT,
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_STYLE_DEFAULT,
)


def test_shared_settings_defaults():
    assert BACKGROUND_STYLE_DEFAULT == "Gradient"
    assert BACKGROUND_COLOR_DEFAULT == "#1e1432"
    assert ANIMATIONS_ENABLED_DEFAULT is True
    assert ANIMATION_INTENSITY_DEFAULT == 50
