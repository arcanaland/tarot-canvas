from dataclasses import replace

from tarot_canvas.models.esoterica import Entry, SourceReading
from tarot_canvas.models.esoterica_registry import PASSAGES, Role
from tarot_canvas.ui.tabs.card_view.overview_tab import headline_of

KEYWORDS = Entry(PASSAGES, "keywords", Role.KEYWORDS, ("a", "b"))
EPITHET = Entry(PASSAGES, "x_subtitle", Role.EPITHET, "The Turning")
PROSE = Entry(PASSAGES, "text", Role.PRINCIPAL, "Prose.")


def reading(name, *entries, about_deck=False):
    return SourceReading(name, None, entries, (), about_deck=about_deck)


def test_keywords_beat_an_epithet_from_an_earlier_source():
    readings = [reading("epithet", EPITHET), reading("keywords", KEYWORDS)]

    assert headline_of(readings) == (readings[1], (KEYWORDS,))


def test_an_epithet_from_a_source_about_the_deck_beats_another_sources_keywords():
    readings = [reading("keywords", KEYWORDS), reading("mine", EPITHET, about_deck=True)]

    assert headline_of(readings) == (readings[1], (EPITHET,))


def test_a_source_about_the_deck_leads_with_its_keywords_before_its_epithet():
    mine = reading("mine", EPITHET, KEYWORDS, about_deck=True)

    assert headline_of([mine]) == (mine, (KEYWORDS,))


def test_the_first_source_about_the_deck_with_a_lead_wins():
    readings = [
        reading("prose only", PROSE, about_deck=True),
        reading("epithet", EPITHET, about_deck=True),
        reading("keywords", KEYWORDS, about_deck=True),
    ]

    assert headline_of(readings) == (readings[1], (EPITHET,))


def test_with_no_lead_about_the_deck_the_headline_is_as_before():
    readings = [
        reading("prose only", PROSE, about_deck=True),
        reading("epithet", EPITHET),
        reading("keywords", KEYWORDS),
    ]

    assert headline_of(readings) == headline_of([replace(r, about_deck=False) for r in readings])
    assert headline_of(readings) == (readings[2], (KEYWORDS,))


def test_no_lead_anywhere_is_no_headline():
    assert headline_of([reading("prose only", PROSE, about_deck=True)]) is None
    assert headline_of([]) is None
