import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from tarot_canvas.settings import DECK_HEADER_EXPANDED_KEY, get_settings
from tarot_canvas.ui.widgets.cover_banner import (
    BANNER_SCRIM_ALPHA,
    BANNER_SUBTEXT,
    BANNER_TEXT,
)
from tarot_canvas.ui.widgets.deck_header import DeckHeader, wrapped_height
from tarot_canvas.ui.widgets.tag_chips import TagChips

FULL_METADATA = {
    "id": "rider-waite-smith",
    "schema_version": "1.0",
    "name": "Rider-Waite-Smith Tarot",
    "version": "1.1",
    "author": "Pamela Colman Smith",
    "license": "Public Domain",
    "attribution": "Original artwork by Pamela Colman Smith (1909).",
    "description": "The classic Rider-Waite-Smith tarot deck.",
    "publisher": "Original: US Games Systems",
    "website": "https://www.usgamesinc.com/rider-waite-tarot-card-deck.html",
    "tags": ["traditional", "classic"],
    "aspect_ratio": 0.569,
}


def make_deck(**overrides):
    """deck stub"""
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


def test_the_disclosure_shows_and_hides_the_details(header):
    header.set_expanded(True)
    assert header.details_widget.isVisibleTo(header)
    assert header.details_button.arrowType() == Qt.ArrowType.DownArrow

    header.set_expanded(False)
    assert not header.details_widget.isVisibleTo(header)
    assert header.details_button.arrowType() == Qt.ArrowType.RightArrow


def test_the_disclosure_state_persists(qtbot):
    first = shown(qtbot)
    first.set_expanded(False)
    assert not get_settings().value(DECK_HEADER_EXPANDED_KEY, True, type=bool)

    second = shown(qtbot)
    assert not second.is_expanded()
    assert not second.details_widget.isVisibleTo(second)


def test_the_details_carry_the_metadata(header):
    header.set_expanded(True)
    assert field_text(header, "description") == FULL_METADATA["description"]
    assert field_text(header, "version") == "1.1"
    assert field_text(header, "license") == "Public Domain"
    assert field_text(header, "attribution") == FULL_METADATA["attribution"]


def test_absent_fields_are_omitted_rather_than_shown_empty(qtbot):
    widget = shown(qtbot, make_deck(publisher=None, tags=None, website=None))
    assert "publisher" not in widget.detail_labels
    assert "tags" not in widget.detail_labels
    assert "license" in widget.detail_labels


def test_the_website_is_a_link_only_when_it_is_a_url(qtbot, header):
    header.set_expanded(True)
    website = header.detail_labels["website"]
    assert website.openExternalLinks()
    assert 'href="https://www.usgamesinc.com' in website.text()

    plain = shown(qtbot, make_deck(website="usgamesinc.com"))
    plain.set_expanded(True)
    assert plain.detail_labels["website"].text() == "usgamesinc.com"
    assert not plain.detail_labels["website"].openExternalLinks()


def test_tags_are_chips_rather_than_a_comma_joined_sentence(header):
    """The one multi-valued field in the form; a sentence read as prose it is not."""
    header.set_expanded(True)
    chips = header.detail_labels["tags"]
    assert isinstance(chips, TagChips)
    assert chips.tags == ("traditional", "classic")


def test_a_minimal_deck_builds_a_header(qtbot, minimal_deck):
    """A deck.toml with only the required keys must not raise."""
    widget = shown(qtbot, minimal_deck)
    assert widget.title_label.text() == "Minimal Test Deck"
    assert widget.subtitle_label.text() == "2 cards"


def test_the_banner_needs_both_a_cover_and_an_expanded_panel(qtbot, header, minimal_deck):
    """The fixture deck has real card art; the stub's cards carry no image."""
    header.set_expanded(True)
    assert header.banner_rect().isEmpty()

    with_cover = shown(qtbot, minimal_deck)
    with_cover.set_expanded(True)
    assert not with_cover.banner_rect().isEmpty()
    with_cover.set_expanded(False)
    assert with_cover.banner_rect().isEmpty()


def test_the_banner_guarantees_a_contrast_floor():
    def relative_luminance(colour):
        channels = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in (colour.redF(), colour.greenF(), colour.blueF())
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def contrast_ratio(one, two):
        lighter, darker = sorted((relative_luminance(one), relative_luminance(two)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    brightest = QColor(*(3 * [255 - BANNER_SCRIM_ALPHA]))
    assert contrast_ratio(BANNER_TEXT, brightest) >= 4.5
    assert contrast_ratio(QColor(BANNER_SUBTEXT.rgb()), brightest) >= 4.5


def test_wrapped_height_grows_with_the_text(qapp):
    font = QApplication.font()
    prose = "wrapping prose " * 20
    assert wrapped_height("", font, 400) == 0
    assert wrapped_height("x", font, 0) == 0
    assert wrapped_height(prose, font, 200) > wrapped_height(prose, font, 600)
