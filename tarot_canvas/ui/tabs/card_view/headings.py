"""Headings inside the card view, sized relative to the system font.

The card view predates the HIG being consulted, and had two separate problems with it.

**The card's name was set in fixed pixels** (`font-size: 18px`), which fails the one
accessibility check the HIG names for type: *"Increase the system-wide font size to 14 and
verify that visual relationships are preserved"*
(`vendor/develop-kde-org/content/hig/accessibility.md`). Measured on `main`, at a 10pt
system font the name was 24px against 18px body text; at 14pt the name was still 24px
while the body had grown to 26px, so the card's own title was **smaller than the prose
under it**. The other fixed-pixel headings in this package have the same defect.

**The description heading was not a heading at all.** It was body-sized bold text ending
in a colon — the shape the HIG gives to a label placed in front of a control, which is
what the Type/Suit/Deck rows above it are. A heading over a block of prose takes title
case, no colon, and a size of its own (`text_and_labels.md`).

The newer parts of the app already scale a copy of the inherited font this way —
`ui/widgets/deck_header.py` and `ui/library/deck_details_pane.py` — and these constants are
that ladder expressed for the card view. The HIG's own wording is `Kirigami.Heading` "with
a `level` suitable for the context"; in a QtWidgets app that is a scaled, bolded copy of
the base font.
"""

from tarot_canvas.ui.library import units

# The card's name: the title of the page, one per card view.
TITLE_SCALE = 1.35

# A heading over a block of content within the page, a step below the title.
SECTION_SCALE = 1.2

# A subtitle or caption under a row's title, matching the library's list rows.
SUBTITLE_SCALE = 0.85


def apply_heading(label, scale):
    """Set `label` in a bolded copy of its own font at `scale`."""
    label.setFont(units.scaled_font(label.font(), scale, bold=True))
    return label
