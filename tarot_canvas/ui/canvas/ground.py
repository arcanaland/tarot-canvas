import math
from dataclasses import dataclass

from PyQt6.QtGui import QColor

from tarot_canvas.settings import GROUND_HUE_DEFAULT, GROUND_HUE_KEY, get_settings
from tarot_canvas.ui.canvas.motion import SHADOW_OPACITY


@dataclass(frozen=True)
class GroundHue:
    """preset shared by Swirl and Aura"""

    # The swirl shader's colour_1, colour_2, colour_3
    swirl: tuple
    # Aura's radial stops: centre, middle, edge
    aura: tuple

    def aura_stops(self):
        return tuple(zip((0.0, 0.5, 1.0), self.aura, strict=True))


GROUND_HUES = {
    "violet": GroundHue(
        swirl=(QColor("#50396b"), QColor("#301f46"), QColor("#8671a5")),
        aura=(QColor(50, 30, 80), QColor(30, 18, 60), QColor(15, 10, 30)),
    ),
    "green": GroundHue(
        swirl=(QColor("#23512f"), QColor("#0c3217"), QColor("#5d8966")),
        aura=(QColor("#023514"), QColor("#00230b"), QColor("#031206")),
    ),
    "orange": GroundHue(
        swirl=(QColor("#6e3214"), QColor("#471901"), QColor("#a96b4f")),
        aura=(QColor("#4a1a01"), QColor("#330f00"), QColor("#1d0700")),
    ),
    "blue": GroundHue(
        swirl=(QColor("#234773"), QColor("#0d294b"), QColor("#5b7fad")),
        aura=(QColor("#042a56"), QColor("#011b3d"), QColor("#030e1f")),
    ),
    "red": GroundHue(
        swirl=(QColor("#6e302c"), QColor("#471715"), QColor("#aa6863")),
        aura=(QColor("#501111"), QColor("#390507"), QColor("#1d0605")),
    ),
    "cream": GroundHue(
        swirl=(QColor("#e9ddc4"), QColor("#d7c9ae"), QColor("#fbf4e6")),
        aura=(QColor("#f6eedc"), QColor("#eae0cb"), QColor("#d2c6ae")),
    ),
    "gold": GroundHue(
        swirl=(QColor("#714a20"), QColor("#4c2e0c"), QColor("#ab835c")),
        aura=(QColor("#522e01"), QColor("#3c2000"), QColor("#251506")),
    ),
    "grey": GroundHue(
        swirl=(QColor("#464646"), QColor("#292929"), QColor("#7d7d7d")),
        aura=(QColor("#2b2b2b"), QColor("#1c1c1c"), QColor("#0e0e0e")),
    ),
}


def ground_hue_id(settings=None):
    """The stored preset's id"""
    stored = (settings or get_settings()).value(GROUND_HUE_KEY)
    return stored if stored in GROUND_HUES else GROUND_HUE_DEFAULT


# The default preset's Aura, center to edge
GRADIENT_STOPS = GROUND_HUES[GROUND_HUE_DEFAULT].aura_stops()

CHECKERBOARD_CONTRAST = 1.35
# Each square's side in scene units
CHECKERBOARD_SQUARE = 80
CHECKERBOARD_DARKEN_FROM = 0.6
_BISECTIONS = 40

# A shadow is the ground with less light on it: its own hue, darker and a little richer
SHADOW_TONE_LIGHTNESS = 0.35
SHADOW_TONE_CHROMA = 1.5
# Black at a fixed alpha takes far more off a light ground than a dark one,
# so the shadow fades between these OKLab lightnesses
SHADOW_OPACITY_ON_LIGHT = 0.22
SHADOW_DARK_GROUND = 0.3
SHADOW_LIGHT_GROUND = 0.9
_GAMUT_EPSILON = 1e-6


def _decode(channel):
    """sRGB transfer function, encoded to linear"""
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _encode(channel):
    if channel <= 0.0031308:
        return channel * 12.92
    return 1.055 * channel ** (1 / 2.4) - 0.055


def _luminance(rgb):
    """WCAG 2 relative luminance of linear sRGB"""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(y1, y2):
    return (max(y1, y2) + 0.05) / (min(y1, y2) + 0.05)


# The clanker provided the following citation for this mess of floats:
# Björn Ottosson, "A perceptual color space for image processing" (2020).
def _to_oklab(rgb):
    r, g, b = rgb
    cone_l = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    cone_m = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    cone_s = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * cone_l + 0.7936177850 * cone_m - 0.0040720468 * cone_s,
        1.9779984951 * cone_l - 2.4285922050 * cone_m + 0.4505937099 * cone_s,
        0.0259040371 * cone_l + 0.7827717662 * cone_m - 0.8086757660 * cone_s,
    )


def _from_oklab(lab):
    lightness, a, b = lab
    cone_l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    cone_m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    cone_s = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * cone_l - 3.3077115913 * cone_m + 0.2309699292 * cone_s,
        -1.2684380046 * cone_l + 2.6097574011 * cone_m - 0.3413193965 * cone_s,
        -0.0041960863 * cone_l - 0.7034186147 * cone_m + 1.7076147010 * cone_s,
    )


def _in_gamut(rgb):
    return all(-_GAMUT_EPSILON <= channel <= 1 + _GAMUT_EPSILON for channel in rgb)


def _fit(lightness, chroma, hue):
    """Linear sRGB at this OKLCH, chroma reduced until it fits"""

    def at(c):
        return _from_oklab((lightness, c * math.cos(hue), c * math.sin(hue)))

    rgb = at(chroma)
    if not _in_gamut(rgb):
        low, high = 0.0, chroma
        for _ in range(_BISECTIONS):
            mid = (low + high) / 2
            if _in_gamut(at(mid)):
                low = mid
            else:
                high = mid
        rgb = at(low)
    return tuple(min(max(channel, 0.0), 1.0) for channel in rgb)


def checkerboard_partner(color, contrast=CHECKERBOARD_CONTRAST):
    """The checkerboard's other square (lighter or darker)"""
    color = QColor(color)
    rgb = tuple(_decode(channel) for channel in (color.redF(), color.greenF(), color.blueF()))
    y = _luminance(rgb)
    lightness, a, b = _to_oklab(rgb)
    chroma = math.hypot(a, b)
    if chroma < 1e-4:  # grey has no hue to hold
        chroma = 0.0
    hue = math.atan2(b, a)

    can_darken = (y + 0.05) / contrast - 0.05 >= 0
    can_lighten = (y + 0.05) * contrast - 0.05 <= 1
    darken = can_darken and (lightness >= CHECKERBOARD_DARKEN_FROM or not can_lighten)

    # The partner's luminance rises with its lightness, so bisect lightness for the contrast
    low, high = (0.0, lightness) if darken else (lightness, 1.0)
    for _ in range(_BISECTIONS):
        mid = (low + high) / 2
        reached = _contrast(y, _luminance(_fit(mid, chroma, hue))) >= contrast
        if reached == darken:
            low = mid
        else:
            high = mid

    partner = _fit((low + high) / 2, chroma, hue)
    return QColor(*(round(_encode(channel) * 255) for channel in partner))


def shadow_for_ground(color):
    """(tone, opacity) for a card's shadow cast on a ground of this colour"""
    color = QColor(color)
    rgb = tuple(_decode(channel) for channel in (color.redF(), color.greenF(), color.blueF()))
    lightness, a, b = _to_oklab(rgb)
    chroma = math.hypot(a, b)
    if chroma < 1e-4:
        chroma = 0.0
    hue = math.atan2(b, a)

    tone = _fit(lightness * SHADOW_TONE_LIGHTNESS, chroma * SHADOW_TONE_CHROMA, hue)
    tone = QColor(*(round(_encode(channel) * 255) for channel in tone))

    t = (lightness - SHADOW_DARK_GROUND) / (SHADOW_LIGHT_GROUND - SHADOW_DARK_GROUND)
    t = min(max(t, 0.0), 1.0)
    t = t * t * (3.0 - 2.0 * t)
    opacity = SHADOW_OPACITY + (SHADOW_OPACITY_ON_LIGHT - SHADOW_OPACITY) * t
    return tone, opacity
