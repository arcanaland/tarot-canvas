"""Kirigami's standard units, as plain pixel constants.

The KDE HIG measures everything in these; keeping them named here means the
delegate reads like the guideline it implements and there are no bare numbers
scattered through the paint code.
"""

SMALL_SPACING = 4
LARGE_SPACING = 8
GRID_UNIT = 18

DENSITY_SMALL = "small"
DENSITY_MEDIUM = "medium"
DENSITY_LARGE = "large"

DENSITIES = (DENSITY_SMALL, DENSITY_MEDIUM, DENSITY_LARGE)

# Cover width per density; height follows from the 2:3 well.
COVER_WIDTHS = {
    DENSITY_SMALL: 6 * GRID_UNIT,  # 108
    DENSITY_MEDIUM: 8 * GRID_UNIT,  # 144
    DENSITY_LARGE: 192,
}

COVER_ASPECT = 3 / 2

CORNER_RADIUS = 5
COVER_RADIUS = 4


def cover_size(density):
    """(width, height) of the cover well at the given density."""
    width = COVER_WIDTHS.get(density, COVER_WIDTHS[DENSITY_MEDIUM])
    return width, round(width * COVER_ASPECT)
