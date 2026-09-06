"""Deck tags drawn as chips instead of a comma-joined sentence."""

import pytest
from PyQt6.QtGui import QColor, QPalette

from tarot_canvas.ui.widgets.tag_chips import (
    CHIP_PADDING_H,
    CHIP_SPACING,
    TagChips,
    normalized_tags,
)

TAGS = ("traditional", "classic", "beginner-friendly", "reference", "public-domain")


def shown(qtbot, tags=TAGS, measure=420):
    widget = TagChips(tags, measure)
    qtbot.addWidget(widget)
    widget.setFixedWidth(measure)
    widget.setMinimumHeight(widget.heightForWidth(measure))
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_normalized_tags_accepts_what_decks_actually_write():
    assert normalized_tags(["classic", "reference"]) == ("classic", "reference")
    # A deck may write a bare string where the spec says array.
    assert normalized_tags("classic") == ("classic",)
    assert normalized_tags(["classic", "", "  ", "reference"]) == ("classic", "reference")
    assert normalized_tags(None) == ()
    assert normalized_tags({"a": 1}) == ()
    assert normalized_tags([1, 2]) == ("1", "2")


def test_tags_wrap_rather_than_overflowing(qtbot):
    narrow = shown(qtbot, measure=200)
    rows = narrow.rows(200)
    assert len(rows) > 1
    for row in rows:
        last_text, last_x, last_width = row[-1]
        assert last_x + last_width <= 200


def test_a_wider_strip_needs_fewer_rows(qtbot):
    widget = shown(qtbot)
    assert len(widget.rows(200)) > len(widget.rows(900))
    assert widget.heightForWidth(200) > widget.heightForWidth(900)


def test_no_tags_takes_no_height(qtbot):
    widget = shown(qtbot, tags=())
    assert widget.rows(420) == []
    assert widget.heightForWidth(420) == 0


def test_a_tag_too_wide_for_the_strip_is_elided_not_overflowed(qtbot):
    monster = "a-" + "very-" * 40 + "long-tag"
    widget = shown(qtbot, tags=(monster,))
    (row,) = widget.rows(420)
    ((text, _x, width),) = row
    assert width <= 420
    assert text.endswith("…")
    assert text != monster


def test_chips_have_room_around_their_text(qtbot):
    widget = shown(qtbot, tags=("classic",))
    (row,) = widget.rows(420)
    ((_, _, width),) = row
    metrics = widget.fontMetrics()
    assert width == metrics.horizontalAdvance("classic") + 2 * CHIP_PADDING_H


def test_rows_are_separated_by_the_spacing_unit(qtbot):
    widget = shown(qtbot, tags=("one", "two"))
    (row,) = widget.rows(900)
    (_, first_x, first_width), (_, second_x, _) = row
    assert second_x == first_x + first_width + CHIP_SPACING


def test_a_screen_reader_gets_the_tags(qtbot):
    """The chips are painted, so nothing is readable without an accessible name."""
    widget = shown(qtbot)
    assert (
        widget.accessibleName()
        == "traditional, classic, beginner-friendly, reference, public-domain"
    )


def test_chips_are_palette_derived_not_hardcoded(qtbot):
    """The HIG's § Color check: change the scheme and the chips must change with it."""
    widget = shown(qtbot)
    assert widget.styleSheet() == ""

    light = widget.grab().toImage()

    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Button, QColor("#31363b"))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor("#fcfcfc"))
    dark.setColor(QPalette.ColorRole.Mid, QColor("#5c6165"))
    widget.setPalette(dark)
    assert widget.grab().toImage() != light


@pytest.mark.parametrize("width", [1, 10, 50])
def test_a_strip_narrower_than_one_chip_does_not_hang(qtbot, width):
    widget = shown(qtbot, measure=max(1, width))
    assert len(widget.rows(width)) == len(TAGS)
