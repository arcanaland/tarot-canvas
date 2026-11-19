import logging
from datetime import datetime

import pytest

from tarot_canvas.models.ground import (
    DESIGNER_CHECKERBOARD_COLOR,
    EVERY_CANVAS,
    KIND_DEFAULTS,
    Ground,
    drawn,
    follows,
    ground_kind,
    kind_ground,
    set_kind_ground,
)
from tarot_canvas.models.readings import Reading
from tarot_canvas.models.spreads import Spread
from tarot_canvas.settings import (
    BACKGROUND_COLOR_KEY,
    BACKGROUND_FILL_KEY,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_POSITIONING_DEFAULT,
    BACKGROUND_POSITIONING_KEY,
    BACKGROUND_STYLE_KEY,
    CHECKERBOARD_COLOR_KEY,
    GROUND_HUE_KEY,
    GROUND_KINDS,
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


# -- which ground draws ----------------------------------------------------


def store_default(ground):
    ground.to_settings()
    get_settings().sync()


def test_no_ground_draws_the_default():
    store_default(OWN["gradient"])
    assert drawn(None, "sandbox") == OWN["gradient"]


def test_an_own_ground_draws_itself():
    store_default(OWN["gradient"])
    assert drawn(OWN["solid"], "sandbox") == OWN["solid"]


def test_an_image_ground_whose_file_is_missing_draws_the_default(backgrounds_base):
    store_default(OWN["checkerboard"])
    assert drawn(Ground(style="image", image="gone.png"), "sandbox") == OWN["checkerboard"]


def test_an_image_ground_whose_file_is_there_draws_itself(backgrounds_base):
    backgrounds_base.mkdir(parents=True)
    (backgrounds_base / "felt.png").write_bytes(b"")
    ground = Ground(style="image", image="felt.png")
    assert drawn(ground, "sandbox") == ground


def picture(backgrounds_base, name):
    backgrounds_base.mkdir(parents=True, exist_ok=True)
    (backgrounds_base / name).write_bytes(b"")
    return Ground(style="image", image=name)


# -- each kind's ground ----------------------------------------------------


def kind_keys(kind):
    return [key for key in get_settings().allKeys() if key.startswith(f"appearance/{kind}/")]


def test_a_reading_from_a_spread_is_the_reading_kind_and_one_without_is_a_sandbox():
    now = datetime(2026, 11, 18)
    assert ground_kind(Reading(date=now, spread=Spread())) == "reading"
    assert ground_kind(Reading(date=now)) == "sandbox"


def test_a_fresh_profile_swirls_readings_checkers_the_designer_and_follows_in_a_sandbox():
    store_default(OWN["solid"])

    assert drawn(None, "reading") == Ground(style="swirl")
    assert drawn(None, "designer") == KIND_DEFAULTS["designer"]
    assert drawn(None, "designer").checkerboard_color == DESIGNER_CHECKERBOARD_COLOR
    assert drawn(None, "sandbox") == OWN["solid"]
    assert [follows(kind) for kind in GROUND_KINDS] == [EVERY_CANVAS, "reading", "designer"]


def test_a_kinds_ground_draws_for_that_kind_only():
    store_default(OWN["gradient"])
    set_kind_ground("reading", OWN["swirl"])

    assert drawn(None, "reading") == OWN["swirl"]
    assert drawn(None, "sandbox") == OWN["gradient"]
    assert follows("reading") == "reading"
    assert drawn(OWN["solid"], "reading") == OWN["solid"]


def test_a_kinds_ground_is_kept_under_the_kind_with_every_canvas_left_alone():
    store_default(OWN["gradient"])
    set_kind_ground("reading", EVERYTHING)

    settings = get_settings()
    assert settings.value("appearance/reading/background_style") == "image"
    assert settings.value("appearance/reading/ground_hue") == "gold"
    assert settings.value("appearance/reading/checkerboard_color") == "#405060"
    assert Ground.from_settings(settings) == OWN["gradient"]
    assert kind_ground("reading") == EVERYTHING


def test_the_designer_set_to_follow_draws_every_canvas():
    store_default(OWN["solid"])
    set_kind_ground("designer", None)

    assert get_settings().value("appearance/designer/background_style") == "follow"
    assert drawn(None, "designer") == OWN["solid"]
    assert follows("designer") == EVERY_CANVAS


def test_follow_clears_the_kinds_other_keys():
    set_kind_ground("sandbox", EVERYTHING)
    set_kind_ground("designer", EVERYTHING)
    set_kind_ground("designer", None)

    assert kind_keys("designer") == ["appearance/designer/background_style"]


@pytest.mark.parametrize("kind", GROUND_KINDS)
def test_a_kinds_built_in_ground_is_stored_as_nothing(kind):
    set_kind_ground(kind, EVERYTHING)
    set_kind_ground(kind, KIND_DEFAULTS.get(kind))

    assert kind_keys(kind) == []


def test_an_unreadable_kind_style_reads_as_its_built_in_ground(caplog):
    get_settings().setValue("appearance/designer/background_style", "plaid")
    get_settings().setValue("appearance/sandbox/background_style", "plaid")

    assert kind_ground("designer") == KIND_DEFAULTS["designer"]
    assert kind_ground("sandbox") is None
    assert len(warnings_in(caplog)) == 2


def test_an_own_picture_missing_falls_to_its_kind_not_every_canvas(backgrounds_base):
    store_default(OWN["gradient"])
    set_kind_ground("reading", OWN["swirl"])

    assert drawn(Ground(style="image", image="gone.png"), "reading") == OWN["swirl"]


def test_a_kinds_picture_missing_falls_to_every_canvas(backgrounds_base):
    store_default(OWN["gradient"])
    set_kind_ground("reading", Ground(style="image", image="gone.png"))

    assert drawn(None, "reading") == OWN["gradient"]
    assert follows("reading") == EVERY_CANVAS


def test_a_kinds_picture_that_is_there_draws(backgrounds_base):
    ground = picture(backgrounds_base, "felt.png")
    set_kind_ground("sandbox", ground)

    assert drawn(None, "sandbox") == ground
