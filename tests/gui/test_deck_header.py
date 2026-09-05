"""The inline deck header that replaced the modal deck-info dialog."""

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QLabel

from tarot_canvas.settings import (
    DECK_HEADER_EXPANDED_DEFAULT,
    DECK_HEADER_EXPANDED_KEY,
    get_settings,
)
from tarot_canvas.ui.widgets.deck_header import (
    BANNER_PADDING,
    BANNER_SCRIM_ALPHA,
    BANNER_SUBTEXT,
    BANNER_TEXT,
    DeckHeader,
    cover_size,
    wrapped_height,
)
from tarot_canvas.ui.widgets.tag_chips import TagChips

DESCRIPTION = (
    "The classic Rider-Waite-Smith tarot deck, first published in 1909 and illustrated "
    "by Pamela Colman Smith under the direction of Arthur Edward Waite. This digital "
    "version features cleaned and formatted images by a tarot afficionado."
)

FULL_METADATA = {
    "id": "rider-waite-smith",
    "schema_version": "1.0",
    "name": "Rider-Waite-Smith Tarot",
    "version": "1.1",
    "author": "Pamela Colman Smith",
    "license": "Public Domain (original artwork), CC0 (digital restoration)",
    "attribution": (
        "Original artwork by Pamela Colman Smith (1909). Digital restoration by an "
        "anonymous user on Anna's Archive."
    ),
    "description": DESCRIPTION,
    "publisher": "Original: US Games Systems",
    "website": "https://www.usgamesinc.com/rider-waite-tarot-card-deck.html",
    "tags": ["traditional", "classic"],
    "aspect_ratio": 0.569,
}


def make_deck(**overrides):
    """A deck stub carrying the accessors the header calls."""
    fields = dict(FULL_METADATA)
    fields.update(overrides)
    fields = {key: value for key, value in fields.items() if value is not None}
    cards = [{"type": "major_arcana", "number": i, "image": None} for i in range(22)]

    def field(key, default=None):
        value = fields.get(key)
        return value if value not in (None, "") else default

    class Deck:
        deck_path = "/decks/rws"

        def get_name(self):
            return field("name", "Unknown Deck")

        def get_version(self):
            return field("version", "Unknown Version")

        def get_description(self):
            return field("description", "")

        def get_author(self):
            return field("author")

        def get_all_cards(self):
            return cards

        def get_cards_by_type(self, card_type):
            return [c for c in cards if c["type"] == card_type]

        def get_metadata_fields(self):
            return dict(fields)

    return Deck()


@pytest.fixture(autouse=True)
def no_stored_disclosure():
    """Qt resolves the QSettings path once per process, so the file outlives a test."""
    get_settings().remove(DECK_HEADER_EXPANDED_KEY)
    yield
    get_settings().remove(DECK_HEADER_EXPANDED_KEY)


def shown(qtbot, deck=None):
    widget = DeckHeader(deck if deck is not None else make_deck())
    qtbot.addWidget(widget)
    widget.resize(700, 400)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.fixture
def header(qtbot):
    return shown(qtbot)


def field_text(header, key):
    return header.detail_labels[key].text()


def test_the_collapsed_rows_carry_the_delegate_grammar(header):
    assert header.title_label.text() == "Rider-Waite-Smith Tarot"
    assert header.subtitle_label.text() == "Pamela Colman Smith · 22 cards"


def test_the_version_is_a_detail_rather_than_part_of_the_identity(header):
    assert "1.1" not in header.subtitle_label.text()
    header.set_expanded(True)
    assert field_text(header, "version") == "1.1"


def test_a_fresh_install_opens_expanded(header):
    """Confirmed better on a fresh install: nothing else advertises what Details holds."""
    assert DECK_HEADER_EXPANDED_DEFAULT is True
    assert header.is_expanded()
    assert header.details_widget.isVisibleTo(header)


def test_details_are_hidden_once_the_disclosure_is_closed(header):
    header.set_expanded(False)
    assert not header.details_widget.isVisibleTo(header)
    header.set_expanded(True)
    assert header.details_widget.isVisibleTo(header)


def test_license_and_attribution_are_shown_and_selectable(header):
    header.set_expanded(True)
    assert field_text(header, "license").startswith("Public Domain")
    assert field_text(header, "attribution").startswith("Original artwork")
    for key in ("license", "attribution"):
        flags = header.detail_labels[key].textInteractionFlags()
        assert flags & Qt.TextInteractionFlag.TextSelectableByMouse


def test_the_website_is_a_real_link(header):
    header.set_expanded(True)
    website = header.detail_labels["website"]
    assert website.openExternalLinks()
    assert 'href="https://www.usgamesinc.com' in website.text()


def test_a_website_that_is_not_a_url_stays_plain_text(qtbot):
    widget = shown(qtbot, make_deck(website="usgamesinc.com"))
    widget.set_expanded(True)
    assert widget.detail_labels["website"].text() == "usgamesinc.com"
    assert not widget.detail_labels["website"].openExternalLinks()


def test_tags_are_chips_rather_than_a_comma_joined_sentence(header):
    """The one multi-valued field in the form; a sentence read as prose it is not."""
    header.set_expanded(True)
    chips = header.detail_labels["tags"]
    assert isinstance(chips, TagChips)
    assert chips.tags == ("traditional", "classic")
    assert chips.width() == header.measure()
    assert chips.minimumHeight() >= chips.chip_height()


def test_absent_fields_are_omitted_rather_than_shown_empty(qtbot):
    widget = shown(qtbot, make_deck(publisher=None, tags=None, website=None))
    assert "publisher" not in widget.detail_labels
    assert "tags" not in widget.detail_labels
    assert "license" in widget.detail_labels


def test_a_minimal_deck_builds_a_header(qtbot, minimal_deck):
    """A deck.toml with only the required keys must not raise."""
    widget = shown(qtbot, minimal_deck)
    assert widget.title_label.text() == "Minimal Test Deck"
    assert widget.subtitle_label.text() == "2 cards"


def test_a_deck_with_nothing_to_disclose_shows_no_details(qtbot):
    bare = make_deck(**dict.fromkeys(FULL_METADATA.keys() - {"name", "author"}))
    widget = shown(qtbot, bare)
    assert widget.detail_labels == {}
    widget.set_expanded(True)
    assert not widget.details_widget.isVisibleTo(widget)


def test_the_disclosure_state_persists(qtbot):
    first = shown(qtbot)
    assert first.is_expanded()
    first.set_expanded(False)
    assert not get_settings().value(DECK_HEADER_EXPANDED_KEY, True, type=bool)

    second = shown(qtbot)
    assert not second.is_expanded()
    assert not second.details_widget.isVisibleTo(second)


def test_the_arrow_follows_the_disclosure(header):
    assert header.details_button.arrowType() == Qt.ArrowType.DownArrow
    header.set_expanded(False)
    assert header.details_button.arrowType() == Qt.ArrowType.RightArrow


def test_the_description_leads_the_disclosure_rather_than_being_elided(header):
    """RFC-021 update: an ellipsis with no affordance became the first detail row."""
    assert "description" not in [label.text() for label in header.findChildren(QLabel)]
    header.set_expanded(True)
    assert field_text(header, "description") == DESCRIPTION
    assert next(iter(header.detail_labels)) == "description"


def test_the_cover_shrinks_when_collapsed(header):
    assert (header.cover_label.width(), header.cover_label.height()) == cover_size(True)
    header.set_expanded(False)
    assert (header.cover_label.width(), header.cover_label.height()) == cover_size(False)
    assert header.cover_label.height() < cover_size(True)[1]


def test_the_collapsed_header_is_not_mostly_cover(header):
    """The nit that prompted the redesign: dead space beside a full-size cover."""
    header.set_expanded(False)
    # The hidden form still counts toward the hint until the layout re-runs.
    header.layout().activate()
    assert header.sizeHint().height() < cover_size(True)[1]


def test_no_hardcoded_colours_or_font_families(header):
    assert header.styleSheet() == ""
    for label in header.findChildren(QLabel):
        assert label.styleSheet() == ""
    base = QApplication.font().family()
    assert header.title_label.font().family() == base
    assert header.subtitle_label.font().family() == base


def test_secondary_text_comes_from_the_palette(header):
    assert header.subtitle_label.foregroundRole() == QPalette.ColorRole.PlaceholderText


# -- the expanded banner ---------------------------------------------------


def relative_luminance(colour):
    """WCAG 2.1 relative luminance of an opaque sRGB colour."""
    channels = []
    for value in (colour.redF(), colour.greenF(), colour.blueF()):
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(one, two):
    lighter, darker = sorted((relative_luminance(one), relative_luminance(two)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.fixture
def banner_header(qtbot, minimal_deck):
    """The fixture deck has real card art, so it renders a banner; the stub does not."""
    widget = shown(qtbot, minimal_deck)
    widget.set_expanded(True)
    return widget


def test_the_banner_is_bounded_to_the_title_and_subtitle(banner_header):
    """Option 3: only two labels ever sit on non-palette colour."""
    rect = banner_header.banner_rect()
    assert rect.width() == banner_header.width()
    subtitle_bottom = banner_header.subtitle_label.mapTo(
        banner_header, QPoint(0, banner_header.subtitle_label.height())
    ).y()
    assert subtitle_bottom <= rect.height() < banner_header.height()


def test_the_form_clears_the_banner_edge(banner_header):
    """Adam's nit: the form used to start exactly where the band ended."""
    band = banner_header.banner_rect().height()
    first = next(iter(banner_header.detail_labels.values()))
    assert first.mapTo(banner_header, QPoint(0, 0)).y() - band >= BANNER_PADDING


def test_the_banner_is_padded_more_than_the_collapsed_strip(banner_header):
    """The strip is tight on purpose; the band needs room to read as a band."""
    assert banner_header.layout().contentsMargins().top() == BANNER_PADDING
    assert banner_header.title_label.mapTo(banner_header, QPoint(0, 0)).y() == BANNER_PADDING
    banner_header.set_expanded(False)
    # Collapsed the column is centred against the cover, so only the margin is comparable.
    assert banner_header.layout().contentsMargins().top() < BANNER_PADDING


def test_there_is_no_banner_until_the_panel_is_expanded(banner_header):
    banner_header.set_expanded(False)
    assert banner_header.banner_rect().isEmpty()
    banner_header.set_expanded(True)
    assert not banner_header.banner_rect().isEmpty()


def test_a_deck_with_no_cover_gets_no_banner_and_keeps_palette_text(header):
    """The stub deck's cards carry no image, which is the no-cover path."""
    header.set_expanded(True)
    assert header.banner_rect().isEmpty()
    assert header.subtitle_label.foregroundRole() == QPalette.ColorRole.PlaceholderText


def test_the_banner_guarantees_a_contrast_floor():
    """Why fixed light text on the banner is defensible rather than a palette violation.

    The scrim is opaque black at `BANNER_SCRIM_ALPHA`, so no channel of the composited
    banner can exceed `255 - BANNER_SCRIM_ALPHA` whatever artwork the deck ships. The
    contrast floor is therefore a property of that constant, not of the deck.
    """
    brightest = QColor(*(3 * [255 - BANNER_SCRIM_ALPHA]))
    assert contrast_ratio(BANNER_TEXT, brightest) >= 4.5
    assert contrast_ratio(QColor(BANNER_SUBTEXT.rgb()), brightest) >= 4.5


def test_the_rendered_banner_respects_that_bound(banner_header):
    pixmap = banner_header._banner_pixmap(banner_header.banner_rect().size())
    image = pixmap.toImage()
    peak = max(
        max(QColor(image.pixel(x, y)).getRgb()[:3])
        for y in range(0, image.height(), 4)
        for x in range(0, image.width(), 8)
    )
    assert peak <= 255 - BANNER_SCRIM_ALPHA


def test_the_banner_text_is_restored_to_the_palette_on_collapse(banner_header):
    assert banner_header.title_label.palette().color(QPalette.ColorRole.WindowText) == BANNER_TEXT
    banner_header.set_expanded(False)
    assert banner_header.subtitle_label.foregroundRole() == QPalette.ColorRole.PlaceholderText
    assert banner_header.title_label.palette().color(
        QPalette.ColorRole.WindowText
    ) == QPalette().color(QPalette.ColorRole.WindowText)


def test_the_title_scales_with_the_system_font(qtbot):
    """The HIG's accessibility check: nothing is pinned to a point size."""
    original = QApplication.font()
    try:
        QApplication.setFont(QFont(original.family(), 14))
        big = shown(qtbot)
        QApplication.setFont(QFont(original.family(), 8))
        small = shown(qtbot)
        assert big.title_label.font().pointSizeF() > small.title_label.font().pointSizeF()
    finally:
        QApplication.setFont(original)


def test_long_values_get_room_to_wrap_rather_than_being_clipped(header):
    """`heightForWidth` does not survive the nested box layouts; heights are measured."""
    header.set_expanded(True)
    attribution = header.detail_labels["attribution"]
    needed = wrapped_height(attribution.text(), attribution.font(), attribution.width())
    assert attribution.minimumHeight() >= needed
    one_line = wrapped_height("short", attribution.font(), attribution.width())
    assert needed > one_line, "the fixture's attribution must be long enough to wrap"


def test_values_are_held_to_the_measure(header):
    header.set_expanded(True)
    assert header.detail_labels["license"].width() == header.measure()
    assert header.detail_labels["description"].width() == header.measure()


def test_wrapped_height_grows_with_the_text(qapp):
    font = QApplication.font()
    assert wrapped_height("", font, 400) == 0
    assert wrapped_height("x", font, 0) == 0
    assert wrapped_height(DESCRIPTION, font, 200) > wrapped_height(DESCRIPTION, font, 600)
