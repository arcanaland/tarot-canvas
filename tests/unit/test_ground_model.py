import logging

import pytest

from tarot_canvas.models.ground import Ground
from tarot_canvas.settings import (
    BACKGROUND_COLOR_KEY,
    BACKGROUND_FILL_KEY,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_POSITIONING_DEFAULT,
    BACKGROUND_POSITIONING_KEY,
    BACKGROUND_STYLE_KEY,
    CHECKERBOARD_COLOR_KEY,
    GROUND_HUE_KEY,
    get_settings,
)

# Every field away from its default, so a field read from the wrong key shows
EVERYTHING = Ground(
    style="image",
    hue="gold",
    color="#102030",
    checkerboard_color="#405060",
    image="wood.png",
    positioning="center",
    fill="#708090",
)

# One of each style, each written field away from its default
OWN = {
    "solid": Ground(style="solid", color="#112233"),
    "checkerboard": Ground(style="checkerboard", checkerboard_color="#445566"),
    "gradient": Ground(style="gradient", hue="green"),
    "swirl": Ground(style="swirl", hue="cream"),
    "image": Ground(style="image", image="felt.jpg", positioning="tile"),
}

WRITES = {
    "solid": {"style", "color"},
    "checkerboard": {"style", "color"},
    "gradient": {"style", "hue"},
    "swirl": {"style", "hue"},
    "image": {"style", "image", "positioning"},
}


def warnings_in(caplog):
    return [record for record in caplog.records if record.levelno == logging.WARNING]


def test_from_settings_reads_every_key():
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "image")
    settings.setValue(GROUND_HUE_KEY, "gold")
    settings.setValue(BACKGROUND_COLOR_KEY, "#102030")
    settings.setValue(CHECKERBOARD_COLOR_KEY, "#405060")
    settings.setValue(BACKGROUND_IMAGE_KEY, "wood.png")
    settings.setValue(BACKGROUND_POSITIONING_KEY, "center")
    settings.setValue(BACKGROUND_FILL_KEY, "#708090")

    assert Ground.from_settings(settings) == EVERYTHING


def test_empty_settings_read_as_the_defaults():
    assert Ground.from_settings(get_settings()) == Ground()


def test_from_settings_migrates_a_legacy_style():
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "Solid Color")

    assert Ground.from_settings(settings).style == "solid"
    assert settings.value(BACKGROUND_STYLE_KEY) == "solid"


def test_an_unknown_stored_positioning_reads_as_the_default():
    settings = get_settings()
    settings.setValue(BACKGROUND_POSITIONING_KEY, "sideways")
    assert Ground.from_settings(settings).positioning == BACKGROUND_POSITIONING_DEFAULT


def test_to_settings_round_trips():
    settings = get_settings()
    EVERYTHING.to_settings(settings)
    assert Ground.from_settings(settings) == EVERYTHING


@pytest.mark.parametrize("style", sorted(OWN))
def test_to_table_writes_only_the_styles_keys(style):
    assert set(OWN[style].to_table()) == WRITES[style]


@pytest.mark.parametrize("positioning", ["fit", "center"])
def test_an_image_that_can_leave_the_canvas_uncovered_writes_its_fill(positioning):
    ground = Ground(style="image", image="wood.png", positioning=positioning, fill="#abcdef")
    assert ground.to_table() == {
        "style": "image",
        "image": "wood.png",
        "positioning": positioning,
        "fill": "#abcdef",
    }


def test_the_checkerboards_colour_is_written_as_color():
    assert OWN["checkerboard"].to_table() == {"style": "checkerboard", "color": "#445566"}


@pytest.mark.parametrize("style", sorted(OWN))
def test_from_table_round_trips_each_style(style):
    assert Ground.from_table(OWN[style].to_table(), Ground()) == OWN[style]


def test_from_table_takes_the_unwritten_fields_from_base():
    ground = Ground.from_table({"style": "solid", "color": "#112233"}, EVERYTHING)
    assert ground.color == "#112233"
    assert ground.hue == EVERYTHING.hue
    assert ground.image == EVERYTHING.image
    assert ground.fill == EVERYTHING.fill


@pytest.mark.parametrize(
    "table",
    [
        "solid",
        ["style", "solid"],
        {"color": "#112233"},
        {"style": "plaid"},
        {"style": 3},
        {"style": "solid", "color": 0x112233},
        {"style": "solid", "color": "plum"},
        {"style": "checkerboard"},
        {"style": "swirl", "hue": True},
        {"style": "image", "image": ["wood.png"]},
        {"style": "image", "image": "wood.png", "positioning": 2},
        {"style": "image", "image": "wood.png", "positioning": "fit", "fill": "black"},
    ],
)
def test_a_table_that_cant_be_read_is_none_and_logged(table, caplog):
    assert Ground.from_table(table, Ground()) is None
    assert len(warnings_in(caplog)) == 1


def test_an_unknown_positioning_takes_the_default_and_is_logged(caplog):
    table = {"style": "image", "image": "wood.png", "positioning": "sideways"}
    base = Ground(positioning="tile")

    ground = Ground.from_table(table, base)

    assert ground == Ground(
        style="image", image="wood.png", positioning=BACKGROUND_POSITIONING_DEFAULT
    )
    assert len(warnings_in(caplog)) == 1


def test_a_hue_id_is_kept_as_written():
    assert (
        Ground.from_table({"style": "swirl", "hue": "ultraviolet"}, Ground()).hue == "ultraviolet"
    )
