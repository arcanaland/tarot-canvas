import math

from PyQt6.QtGui import QColor

# The canvas's default radial gradient, center to edge
GRADIENT_STOPS = (
    (0.0, QColor(50, 30, 80)),
    (0.5, QColor(30, 18, 60)),
    (1.0, QColor(15, 10, 30)),
)

CHECKERBOARD_CONTRAST = 1.35
# Each square's side in scene units
CHECKERBOARD_SQUARE = 80
CHECKERBOARD_DARKEN_FROM = 0.6
_BISECTIONS = 40
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
# Björn Ottosson, "A perceptual color space for image processing" (2020). The cone_* are its
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
