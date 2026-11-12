"""What a canvas's ground is: the Background preferences as one value, which a reading can keep"""

import re
from dataclasses import dataclass, replace

from tarot_canvas.models import backgrounds
from tarot_canvas.settings import (
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    BACKGROUND_FILL_DEFAULT,
    BACKGROUND_FILL_KEY,
    BACKGROUND_IMAGE_DEFAULT,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_POSITIONING_DEFAULT,
    BACKGROUND_POSITIONING_KEY,
    BACKGROUND_POSITIONINGS,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    BACKGROUND_STYLES,
    CHECKERBOARD_COLOR_DEFAULT,
    CHECKERBOARD_COLOR_KEY,
    GROUND_HUE_DEFAULT,
    GROUND_HUE_KEY,
    get_background_positioning,
    get_background_style,
    get_settings,
)
from tarot_canvas.utils.logger import logger

# The types drawn in a GroundHue, which show the hue row
HUED_STYLES = ("gradient", "swirl")

# The positionings that can leave the canvas uncovered, where the fill shows
FILLED_POSITIONINGS = ("fit", "center")

_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")


def _stored(settings, key, default):
    value = settings.value(key, default)
    return value if isinstance(value, str) else default


@dataclass(frozen=True)
class Ground:
    style: str = BACKGROUND_STYLE_DEFAULT
    # An id in ui.canvas.ground.GROUND_HUES, resolved when drawn
    hue: str = GROUND_HUE_DEFAULT
    # Solid's
    color: str = BACKGROUND_COLOR_DEFAULT
    checkerboard_color: str = CHECKERBOARD_COLOR_DEFAULT
    # A file name under the backgrounds directory, or "" for none
    image: str = BACKGROUND_IMAGE_DEFAULT
    positioning: str = BACKGROUND_POSITIONING_DEFAULT
    fill: str = BACKGROUND_FILL_DEFAULT

    # -- the default, in QSettings -----------------------------------------

    @classmethod
    def from_settings(cls, settings=None):
        settings = settings or get_settings()
        return cls(
            style=get_background_style(settings),
            hue=_stored(settings, GROUND_HUE_KEY, GROUND_HUE_DEFAULT),
            color=_stored(settings, BACKGROUND_COLOR_KEY, BACKGROUND_COLOR_DEFAULT),
            checkerboard_color=_stored(
                settings, CHECKERBOARD_COLOR_KEY, CHECKERBOARD_COLOR_DEFAULT
            ),
            image=_stored(settings, BACKGROUND_IMAGE_KEY, BACKGROUND_IMAGE_DEFAULT),
            positioning=get_background_positioning(settings),
            fill=_stored(settings, BACKGROUND_FILL_KEY, BACKGROUND_FILL_DEFAULT),
        )

    def to_settings(self, settings=None):
        """Make this the default for every canvas without its own"""
        settings = settings or get_settings()
        settings.setValue(BACKGROUND_STYLE_KEY, self.style)
        settings.setValue(GROUND_HUE_KEY, self.hue)
        settings.setValue(BACKGROUND_COLOR_KEY, self.color)
        settings.setValue(CHECKERBOARD_COLOR_KEY, self.checkerboard_color)
        settings.setValue(BACKGROUND_IMAGE_KEY, self.image)
        settings.setValue(BACKGROUND_POSITIONING_KEY, self.positioning)
        settings.setValue(BACKGROUND_FILL_KEY, self.fill)

    # -- a reading's own, in reading.toml ----------------------------------

    def to_table(self):
        """The style, and only the keys it draws with"""
        table = {"style": self.style}
        if self.style == "solid":
            table["color"] = self.color
        elif self.style == "checkerboard":
            table["color"] = self.checkerboard_color
        elif self.style in HUED_STYLES:
            table["hue"] = self.hue
        elif self.style == "image":
            table["image"] = self.image
            table["positioning"] = self.positioning
            if self.positioning in FILLED_POSITIONINGS:
                table["fill"] = self.fill
        return table

    @classmethod
    def from_table(cls, table, base):
        """The ground table names, its unwritten fields base's; None for one that can't be read"""
        try:
            return cls._from_table(table, base)
        except ValueError as error:
            logger.warning(
                f"Ignored an unreadable ground, so the canvas takes the default: {error}"
            )
            return None

    @classmethod
    def _from_table(cls, table, base):
        if not isinstance(table, dict):
            raise ValueError(f"not a table: {table!r}")
        style = table.get("style")
        if style not in BACKGROUND_STYLES:
            raise ValueError(f"no such style: {style!r}")
        fields = {"style": style}
        if style == "solid":
            fields["color"] = _colour(table, "color")
        elif style == "checkerboard":
            fields["checkerboard_color"] = _colour(table, "color")
        elif style in HUED_STYLES:
            fields["hue"] = _text(table, "hue")
        elif style == "image":
            fields["image"] = _text(table, "image")
            positioning = _text(table, "positioning", BACKGROUND_POSITIONING_DEFAULT)
            if positioning not in BACKGROUND_POSITIONINGS:
                logger.warning(
                    f"No such positioning {positioning!r}, so the ground takes the default"
                )
                positioning = BACKGROUND_POSITIONING_DEFAULT
            fields["positioning"] = positioning
            if "fill" in table:
                fields["fill"] = _colour(table, "fill")
        return replace(base, **fields)


def _text(table, key, default=None):
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} is not a string: {value!r}")
    return value


def _colour(table, key):
    value = _text(table, key)
    if not _COLOUR.fullmatch(value):
        raise ValueError(f"{key} is not a #rrggbb colour: {value!r}")
    return value


def drawn(ground, settings=None):
    """The ground a canvas draws: its own, else the default; the default too while its image is missing"""
    default = Ground.from_settings(settings or get_settings())
    if ground is None:
        return default
    if ground.style == "image":
        path = backgrounds.background_path(ground.image)
        if path is None or not path.is_file():
            logger.info(f"No background image {ground.image!r}, so the canvas draws the default")
            return default
    return ground
