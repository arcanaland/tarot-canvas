from tarot_canvas.ui.library import units

# card's name
TITLE_SCALE = 1.35

# A heading  within the page
SECTION_SCALE = 1.2

SUBTITLE_SCALE = 0.85


def apply_heading(label, scale):
    """Set label in a bolded copy of its own font at scale."""
    label.setFont(units.scaled_font(label.font(), scale, bold=True))
    return label
