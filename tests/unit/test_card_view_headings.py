"""Card-view headings hold their relationship to the body text at any font size.

The HIG names exactly one check for type: raise the system font to 14 and verify the
visual relationships survive. A heading set in fixed pixels fails it — the body text
around it grows and the heading does not — so these assert the scaling, not a size.
"""

import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, TITLE_SCALE, apply_heading


def labelled(point_size):
    font = QFont()
    font.setPointSizeF(point_size)
    label = QLabel()
    label.setFont(font)
    return label


@pytest.mark.parametrize("base", [9.0, 11.0, 14.0, 22.0])
@pytest.mark.parametrize("scale", [TITLE_SCALE, SECTION_SCALE])
def test_a_heading_is_a_multiple_of_the_font_it_inherits(qtbot, base, scale):
    label = labelled(base)

    apply_heading(label, scale)

    assert label.font().pointSizeF() == pytest.approx(base * scale)
    assert label.font().bold()


@pytest.mark.parametrize("base", [9.0, 14.0, 22.0])
def test_a_heading_stays_larger_than_its_body_text(qtbot, base):
    """The relationship the HIG's accessibility check is asking about."""
    heading = apply_heading(labelled(base), SECTION_SCALE)
    body = labelled(base)

    assert heading.font().pointSizeF() > body.font().pointSizeF()


def test_the_page_title_outranks_a_section_heading():
    assert TITLE_SCALE > SECTION_SCALE > 1.0
