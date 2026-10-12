from tarot_canvas.settings import (
    ANIMATION_INTENSITY_DEFAULT,
    ANIMATION_INTENSITY_KEY,
    ANIMATIONS_ENABLED_DEFAULT,
    ANIMATIONS_ENABLED_KEY,
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    DECK_HEADER_EXPANDED_DEFAULT,
    MOTION_LEVEL_DEFAULT,
    MOTION_LEVEL_KEY,
    get_background_style,
    get_motion_level,
    get_settings,
)


def test_shared_settings_defaults():
    assert BACKGROUND_STYLE_DEFAULT == "gradient"
    assert BACKGROUND_COLOR_DEFAULT == "#1e1432"
    assert ANIMATIONS_ENABLED_DEFAULT is True
    assert ANIMATION_INTENSITY_DEFAULT == 50
    assert DECK_HEADER_EXPANDED_DEFAULT is True
    assert MOTION_LEVEL_DEFAULT == "Full"


def test_motion_level_defaults_to_full_on_clean_settings():
    settings = get_settings()
    settings.clear()
    assert get_motion_level(settings) == "Full"


def test_motion_level_migrates_the_retired_animation_keys():
    for enabled, intensity, expected in (
        (True, 50, "Full"),
        (True, 0, "Off"),
        (False, 50, "Off"),
        (False, 0, "Off"),
    ):
        settings = get_settings()
        settings.clear()
        settings.setValue(ANIMATIONS_ENABLED_KEY, enabled)
        settings.setValue(ANIMATION_INTENSITY_KEY, intensity)

        assert get_motion_level(settings) == expected
        assert settings.value(MOTION_LEVEL_KEY) == expected


def test_motion_level_migration_does_not_override_an_explicit_choice():
    settings = get_settings()
    settings.clear()
    settings.setValue(ANIMATIONS_ENABLED_KEY, False)
    settings.setValue(MOTION_LEVEL_KEY, "Reactive")

    assert get_motion_level(settings) == "Reactive"


def test_background_style_defaults_to_gradient_on_clean_settings():
    settings = get_settings()
    settings.clear()
    assert get_background_style(settings) == "gradient"


def test_background_style_passes_a_stored_key_through():
    settings = get_settings()
    for key in ("checkerboard", "gradient", "solid"):
        settings.setValue(BACKGROUND_STYLE_KEY, key)
        assert get_background_style(settings) == key


def test_background_style_migrates_the_labels_it_used_to_store():
    """Labels were stored as values, so relabelling the combo would have reset them"""
    for label, key in (
        ("Checkerboard", "checkerboard"),
        ("Gradient", "gradient"),
        ("Solid Color", "solid"),
    ):
        settings = get_settings()
        settings.clear()
        settings.setValue(BACKGROUND_STYLE_KEY, label)

        assert get_background_style(settings) == key
        assert settings.value(BACKGROUND_STYLE_KEY) == key


def test_an_unknown_background_style_reads_as_the_default():
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "Plaid")
    assert get_background_style(settings) == BACKGROUND_STYLE_DEFAULT
