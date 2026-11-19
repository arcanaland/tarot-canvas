"""What a canvas's ground is: the Background preferences as one value, which a reading can keep"""

import logging
import re
from dataclasses import dataclass, replace

from tarot_canvas.models import backgrounds
from tarot_canvas.settings import (
    APPEARANCE_PREFIX,
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
    GROUND_FOLLOW,
    GROUND_HUE_DEFAULT,
    GROUND_HUE_KEY,
    get_background_positioning,
    get_background_style,
    get_settings,
    ground_kind_prefix,
)

log = logging.getLogger(__name__)

# The types drawn in a GroundHue, which show the hue row
HUED_STYLES = ("gradient", "swirl")

# The positionings that can leave the canvas uncovered, where the fill shows
FILLED_POSITIONINGS = ("fit", "center")

_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")

EVERY_CANVAS = "every"


def _key(prefix, key):
    return prefix + key.removeprefix(APPEARANCE_PREFIX)


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
    def from_settings(cls, settings=None, prefix=APPEARANCE_PREFIX):
        settings = settings or get_settings()
        return cls(
            style=get_background_style(settings, _key(prefix, BACKGROUND_STYLE_KEY)),
            hue=_stored(settings, _key(prefix, GROUND_HUE_KEY), GROUND_HUE_DEFAULT),
            color=_stored(settings, _key(prefix, BACKGROUND_COLOR_KEY), BACKGROUND_COLOR_DEFAULT),
            checkerboard_color=_stored(
                settings, _key(prefix, CHECKERBOARD_COLOR_KEY), CHECKERBOARD_COLOR_DEFAULT
            ),
            image=_stored(settings, _key(prefix, BACKGROUND_IMAGE_KEY), BACKGROUND_IMAGE_DEFAULT),
            positioning=get_background_positioning(
                settings, _key(prefix, BACKGROUND_POSITIONING_KEY)
            ),
            fill=_stored(settings, _key(prefix, BACKGROUND_FILL_KEY), BACKGROUND_FILL_DEFAULT),
        )

    def to_settings(self, settings=None, prefix=APPEARANCE_PREFIX):
        """Make this the default for every canvas without its own, or under prefix a kind's"""
        settings = settings or get_settings()
        for key, value in (
            (BACKGROUND_STYLE_KEY, self.style),
            (GROUND_HUE_KEY, self.hue),
            (BACKGROUND_COLOR_KEY, self.color),
            (CHECKERBOARD_COLOR_KEY, self.checkerboard_color),
            (BACKGROUND_IMAGE_KEY, self.image),
            (BACKGROUND_POSITIONING_KEY, self.positioning),
            (BACKGROUND_FILL_KEY, self.fill),
        ):
            settings.setValue(_key(prefix, key), value)

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
            log.warning("Ignored an unreadable ground, so the canvas takes the default: %s", error)
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
                log.warning("No such positioning %r, so the ground takes the default", positioning)
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


# Defaults for readings and spread designer
KIND_DEFAULTS = {"reading": Ground(style="swirl"), "designer": Ground(style="checkerboard")}


def ground_kind(reading):
    """The kind of canvas a kept reading opens as"""
    return "reading" if reading.spread is not None else "sandbox"


def kind_ground(kind, settings=None):
    """The kind's own ground, or None while it follows every canvas"""
    settings = settings or get_settings()
    prefix = ground_kind_prefix(kind)
    style = settings.value(_key(prefix, BACKGROUND_STYLE_KEY))
    if style is None:
        return KIND_DEFAULTS.get(kind)
    if style == GROUND_FOLLOW:
        return None
    if style not in BACKGROUND_STYLES:
        log.warning("No such style %r for %s canvases, so they take their default", style, kind)
        return KIND_DEFAULTS.get(kind)
    return Ground.from_settings(settings, prefix)


def set_kind_ground(kind, ground, settings=None):
    """Give the kind its own ground, or None to follow every canvas"""
    settings = settings or get_settings()
    prefix = ground_kind_prefix(kind)
    settings.remove(prefix.rstrip("/"))
    if ground == KIND_DEFAULTS.get(kind):
        return
    if ground is None:
        settings.setValue(_key(prefix, BACKGROUND_STYLE_KEY), GROUND_FOLLOW)
    else:
        ground.to_settings(settings, prefix)


def _present(ground):
    if ground is None:
        return False
    if ground.style == "image":
        path = backgrounds.background_path(ground.image)
        if path is None or not path.is_file():
            log.info("No background image %r, so the canvas draws the next ground", ground.image)
            return False
    return True


def _resolved(ground, kind, settings):
    if _present(ground):
        return "own", ground
    ground = kind_ground(kind, settings)
    if _present(ground):
        return kind, ground
    return EVERY_CANVAS, Ground.from_settings(settings)


def drawn(ground, kind, settings=None):
    """The ground a canvas draws: its own, else its kind's, else every canvas's.

    A ground whose picture is missing is passed over for the next.
    """
    return _resolved(ground, kind, settings or get_settings())[1]


def follows(kind, settings=None):
    """The level a canvas of kind without its own draws: the kind, or EVERY_CANVAS"""
    return _resolved(None, kind, settings or get_settings())[0]
