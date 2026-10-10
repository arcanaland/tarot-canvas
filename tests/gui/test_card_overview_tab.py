from dataclasses import replace
from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from tarot_canvas.models.esoterica import Entry, SourceReading
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.esoterica_registry import PASSAGES, Role
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import muted_text
from tarot_canvas.ui.tabs.card_view import overview_tab
from tarot_canvas.ui.tabs.card_view.overview_tab import OverviewTab

MAJOR = {
    "name": "Wheel of Fortune",
    "id": "major_arcana.10",
    "type": "major_arcana",
    "number": 10,
    "alt_text": "A large, ornate wheel bearing esoteric symbols.",
}

MINOR = {
    "name": "Three of Cups",
    "id": "minor_arcana.cups.3",
    "type": "minor_arcana",
    "suit": "cups",
    "rank": "three",
}


MCELROY = SourceReading(
    "A Guide to Tarot Card Meanings",
    "Mark McElroy",
    (Entry(PASSAGES, "keywords", Role.KEYWORDS, ("fortune", "cycles", "fate")),),
    (),
)

# A user's source with only an epithet, read ahead of the bundled root
EPITHET_ONLY = SourceReading(
    "A user's own deck notes",
    None,
    (Entry(PASSAGES, "x_subtitle", Role.EPITHET, "The Turning"),),
    (),
)


@pytest.fixture(autouse=True)
def readings(monkeypatch):
    """What the enabled sources say about every card; nothing reads the user's directory"""
    current = []
    manager = SimpleNamespace(read_card=lambda card_id, deck=None: list(current))
    monkeypatch.setattr(overview_tab, "get_esoterica_manager", lambda: manager)
    return current


def make_tab(qtbot, card, deck=None, parent=None):
    tab = OverviewTab(card, deck, parent)
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


class FakeCardView(QWidget):
    """What the deck link asks of the tab it sits in"""

    navigation_requested = pyqtSignal(str, object)

    def __init__(self, reference_deck):
        super().__init__()
        self.id = "card_1"
        self.deck_manager = SimpleNamespace(get_reference_deck=lambda: reference_deck)


def test_a_broken_link_to_the_reference_deck_survives_a_rescan(qtbot):
    """A rescan swaps every deck object, so the tab's deck is the old one, at the same path"""
    reference = SimpleNamespace(deck_path="/decks/rider-waite-smith")
    before_the_rescan = SimpleNamespace(deck_path="/decks/rider-waite-smith")
    card_view = FakeCardView(reference)
    qtbot.addWidget(card_view)
    tab = OverviewTab(MAJOR, None, card_view)
    tab.deck = before_the_rescan
    asked = []
    card_view.navigation_requested.connect(lambda action, args: asked.append((action, args)))

    tab.on_deck_link_clicked("deck:None")

    assert asked == [
        ("open_deck_view", {"deck_path": reference.deck_path, "source_tab_id": "card_1"})
    ]


class FakeDeck:
    deck_path = "/decks/rider-waite-smith"

    def get_name(self):
        return "Rider-Waite-Smith"


def test_a_major_arcanum_has_its_type_and_number_then_its_deck_under_the_name(qtbot):
    tab = make_tab(qtbot, MAJOR, FakeDeck())

    assert tab.subtitle.text() == "Major Arcana · 10"
    assert tab.deck_value.text() == (
        "<a href='deck:/decks/rider-waite-smith'>Rider-Waite-Smith</a>"
    )
    # Its own line, directly under the facts
    assert tab.deck_value.y() == tab.subtitle.geometry().bottom() + 1


def test_a_minor_arcanum_has_its_type_suit_and_rank_under_the_name(qtbot):
    tab = make_tab(qtbot, {**MINOR, "display_suit": "Chalices"}, FakeDeck())

    assert tab.subtitle.text() == "Minor Arcana · Chalices · Three"


def test_without_a_deck_there_is_no_deck_line(qtbot):
    tab = make_tab(qtbot, MAJOR)

    assert not tab.deck_value.isVisible()


def test_switching_card_type_redraws_the_subtitle(qtbot):
    tab = make_tab(qtbot, MAJOR)

    tab.update_card_info(MINOR, None)
    assert tab.subtitle.text() == "Minor Arcana · Cups · Three"

    tab.update_card_info(MAJOR, None)
    assert tab.subtitle.text() == "Major Arcana · 10"


def test_no_frame_or_grid_is_left(qtbot):
    tab = make_tab(qtbot, MAJOR)

    assert not [frame for frame in tab.findChildren(QFrame) if type(frame) is QFrame]
    assert not tab.findChildren(QGridLayout)


def test_the_keywords_lead_with_their_source_under_them(qtbot, readings):
    readings.append(MCELROY)
    tab = make_tab(qtbot, MAJOR)

    assert tab.headline.isVisible()
    assert tab.lead.text() == "fortune · cycles · fate"
    assert tab.lead.font().bold()
    assert ">Mark McElroy</a>" in tab.headline_source.text()
    assert tab.headline_source.toolTip() == "A Guide to Tarot Card Meanings"
    # Muted, as the source line is in a passage's frame
    assert muted_text(tab.palette()).name() in tab.headline_source.text()


def test_keywords_beat_an_epithet_from_an_earlier_source(qtbot, readings):
    readings += [EPITHET_ONLY, MCELROY]
    tab = make_tab(qtbot, MAJOR)

    assert tab.lead.text() == "fortune · cycles · fate"
    assert ">Mark McElroy</a>" in tab.headline_source.text()


def test_an_epithet_leads_when_no_source_has_keywords(qtbot, readings):
    readings.append(EPITHET_ONLY)
    tab = make_tab(qtbot, MAJOR)

    assert tab.lead.text() == "The Turning"
    # No author, so the source's name, and no tooltip repeating it
    assert ">A user's own deck notes</a>" in tab.headline_source.text().replace("&#x27;", "'")
    assert tab.headline_source.toolTip() == ""


def test_the_headline_follows_the_sources_without_reopening_the_tab(qtbot, readings):
    readings.append(MCELROY)
    tab = make_tab(qtbot, MAJOR)

    readings.clear()
    esoterica_events().sources_changed.emit()
    assert not tab.headline.isVisible()
    assert tab.lead is None

    readings.append(MCELROY)
    esoterica_events().sources_changed.emit()
    assert tab.headline.isVisible()
    assert tab.lead.text() == "fortune · cycles · fate"


def test_a_destroyed_tab_no_longer_follows_notes_or_sources(qtbot, readings):
    tab = OverviewTab(MAJOR, None)
    sip.delete(tab)

    note_events().notes_changed.emit()
    esoterica_events().sources_changed.emit()


class EsotericaCardView(QWidget):
    def __init__(self):
        super().__init__()
        self.raised = 0

    def show_esoterica_tab(self):
        self.raised += 1


def test_the_source_line_raises_the_esoterica_tab(qtbot, readings):
    readings.append(MCELROY)
    card_view = EsotericaCardView()
    qtbot.addWidget(card_view)
    tab = OverviewTab(MAJOR, None, card_view)

    tab.headline_source.linkActivated.emit("esoterica:")

    assert card_view.raised == 1


def test_the_description_has_no_heading_and_the_card_id_is_not_shown(qtbot):
    tab = make_tab(qtbot, MAJOR)

    assert tab.description_label.text() == MAJOR["alt_text"]
    texts = [label.text() for label in tab.findChildren(QLabel) if label.isVisible()]
    assert "Description" not in texts
    assert not [text for text in texts if MAJOR["id"] in text]


def test_without_alt_text_there_is_no_description(qtbot):
    tab = make_tab(qtbot, MINOR)

    assert not tab.description_label.isVisible()


def test_the_notes_heading_is_quiet(qtbot):
    tab = make_tab(qtbot, MAJOR)
    heading = tab.notes_section.heading

    assert heading.font().pointSizeF() == tab.description_label.font().pointSizeF()
    assert heading.palette().color(QPalette.ColorRole.WindowText) == muted_text(tab.palette())


def test_the_description_is_set_apart_from_the_keywords(qtbot, readings):
    readings.append(MCELROY)
    tab = make_tab(qtbot, MAJOR)

    assert tab.description_label.contentsMargins().top() == units.GRID_UNIT


# A headline written at another seat

MARSEILLE = SimpleNamespace(
    deck_path="/decks/marseille",
    get_name=lambda: "Marseille",
    get_identifier=lambda: None,
    get_pattern=lambda: "land.arcana/pattern/tarot-de-marseille",
    get_card_by_id=lambda card_id: {"major_arcana.11": {"name": "La Force"}}.get(card_id),
)


def test_a_reseated_headline_has_an_info_icon_tipped_with_the_note(qtbot, readings):
    readings.append(
        replace(
            MCELROY, written_at="major_arcana.11", pattern="land.arcana/pattern/rider-waite-smith"
        )
    )

    tab = make_tab(qtbot, MAJOR, MARSEILLE)
    tab.show()

    icon = tab.headline_reseated
    assert icon.isVisible()
    assert not icon.pixmap().isNull()
    assert (
        icon.pixmap().deviceIndependentSize().height() == tab.headline_source.fontMetrics().height()
    )
    assert "La Force (<code>major_arcana.11</code>)" in icon.toolTip()
    assert "Marseille deck" in icon.toolTip()
    assert "Rider-Waite-Smith" in icon.toolTip()
    assert tab.headline_source.toolTip() == "A Guide to Tarot Card Meanings"


def test_a_headline_read_where_it_is_has_no_icon(qtbot, readings):
    readings.append(MCELROY)

    tab = make_tab(qtbot, MAJOR, MARSEILLE)
    tab.show()

    assert not tab.headline_reseated.isVisible()
    assert tab.headline_reseated.toolTip() == ""


def test_the_icon_goes_when_the_next_card_is_read_where_it_is(qtbot, readings):
    readings.append(
        replace(
            MCELROY, written_at="major_arcana.11", pattern="land.arcana/pattern/rider-waite-smith"
        )
    )
    tab = make_tab(qtbot, MAJOR, MARSEILLE)
    tab.show()

    readings[:] = [MCELROY]
    tab.update_card_info(MAJOR, MARSEILLE)

    assert not tab.headline_reseated.isVisible()
