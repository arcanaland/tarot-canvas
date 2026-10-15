"""QPalette parsed from a KDE color scheme file (poor man's KColorScheme)"""

import configparser
from pathlib import Path

from PyQt6.QtGui import QColor, QPalette

from tarot_canvas.ui.palette import blend

SCHEME_DIR = Path("/usr/share/color-schemes")
LIGHT_SCHEME = "BreezeLight.colors"
DARK_SCHEME = "BreezeDark.colors"

Role = QPalette.ColorRole
Group = QPalette.ColorGroup

# (role, section, key)
ROLES = (
    (Role.Window, "Colors:Window", "BackgroundNormal"),
    (Role.WindowText, "Colors:Window", "ForegroundNormal"),
    (Role.Base, "Colors:View", "BackgroundNormal"),
    (Role.Text, "Colors:View", "ForegroundNormal"),
    (Role.AlternateBase, "Colors:View", "BackgroundAlternate"),
    (Role.Button, "Colors:Button", "BackgroundNormal"),
    (Role.ButtonText, "Colors:Button", "ForegroundNormal"),
    (Role.Highlight, "Colors:Selection", "BackgroundNormal"),
    (Role.HighlightedText, "Colors:Selection", "ForegroundNormal"),
    (Role.ToolTipBase, "Colors:Tooltip", "BackgroundNormal"),
    (Role.ToolTipText, "Colors:Tooltip", "ForegroundNormal"),
    (Role.Link, "Colors:View", "ForegroundLink"),
    (Role.LinkVisited, "Colors:View", "ForegroundVisited"),
    (Role.PlaceholderText, "Colors:View", "ForegroundInactive"),
)

# Each foreground with the background its disabled contrast fades towards
FOREGROUNDS = {
    Role.WindowText: Role.Window,
    Role.Text: Role.Base,
    Role.ButtonText: Role.Button,
    Role.HighlightedText: Role.Highlight,
    Role.ToolTipText: Role.ToolTipBase,
    Role.Link: Role.Base,
    Role.LinkVisited: Role.Base,
    Role.PlaceholderText: Role.Base,
}

# [ColorEffects:*] enums
INTENSITY_SHADE, INTENSITY_DARKEN, INTENSITY_LIGHTEN = 1, 2, 3
COLOUR_DESATURATE, COLOUR_FADE, COLOUR_TINT = 1, 2, 3


def _colour(text):
    return QColor(*(int(part) for part in text.split(",")))


def _with_lightness(colour, lightness):
    hue, saturation, _, alpha = colour.getHslF()
    return QColor.fromHslF(max(hue, 0.0), saturation, min(max(lightness, 0.0), 1.0), alpha)


class _Effects:
    """One [ColorEffects:*] section, approximated with HSL lightness where KDE uses HCY luma."""

    def __init__(self, section):
        self.intensity = section.getint("IntensityEffect", 0)
        self.intensity_amount = section.getfloat("IntensityAmount", 0.0)
        self.colour = section.getint("ColorEffect", 0)
        self.colour_amount = section.getfloat("ColorAmount", 0.0)
        self.colour_target = _colour(section.get("Color", "0,0,0"))
        self.contrast = section.getint("ContrastEffect", 0)
        self.contrast_amount = section.getfloat("ContrastAmount", 0.0)

    def background(self, colour):
        lightness = colour.lightnessF()
        amount = self.intensity_amount
        if self.intensity == INTENSITY_SHADE:
            colour = _with_lightness(colour, lightness + amount)
        elif self.intensity == INTENSITY_DARKEN:
            colour = _with_lightness(colour, lightness * (1 - amount))
        elif self.intensity == INTENSITY_LIGHTEN:
            colour = _with_lightness(colour, 1 - (1 - lightness) * (1 - amount))

        if self.colour == COLOUR_DESATURATE:
            hue, saturation, value, alpha = colour.getHsvF()
            colour = QColor.fromHsvF(
                max(hue, 0.0), saturation * (1 - self.colour_amount), value, alpha
            )
        elif self.colour in (COLOUR_FADE, COLOUR_TINT):
            colour = blend(self.colour_target, colour, self.colour_amount)
        return colour

    def foreground(self, colour, background):
        colour = self.background(colour)
        if self.contrast:
            colour = blend(background, colour, self.contrast_amount)
        return colour


def palette_from_scheme(path):
    """The palette the colour scheme file at `path` describes"""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # its keys are CamelCase
    with open(path, encoding="utf-8") as file:
        parser.read_file(file)

    palette = QPalette()
    for role, section, key in ROLES:
        palette.setColor(role, _colour(parser[section][key]))

    button = palette.color(Role.Button)
    palette.setColor(Role.Light, button.lighter(150))
    palette.setColor(Role.Midlight, button.lighter(125))
    palette.setColor(Role.Mid, button.darker(150))
    palette.setColor(Role.Dark, button.darker(200))
    palette.setColor(Role.Shadow, button.darker(300))

    # Both Breeze schemes disable the Inactive effects, so Inactive is Active; QPalette
    # already set the colours above in every group
    if parser.has_section("ColorEffects:Disabled"):
        effects = _Effects(parser["ColorEffects:Disabled"])
        active = QPalette(palette)
        for role in set(FOREGROUNDS.values()) | {Role.AlternateBase}:
            palette.setColor(Group.Disabled, role, effects.background(active.color(role)))
        for role, background in FOREGROUNDS.items():
            palette.setColor(
                Group.Disabled,
                role,
                effects.foreground(active.color(role), palette.color(Group.Disabled, background)),
            )
    return palette
