from types import SimpleNamespace

import pytest

from tarot_canvas.models import deck_choices as module
from tarot_canvas.models import library_curation as curation
from tarot_canvas.models.deck_choices import deck_choices
from tests.unit.test_library_model import fake_deck


def deck(name, identifier="", path=None, **fields):
    if identifier == "":
        identifier = f"x/deck/{name.lower()}"
    return fake_deck(name, identifier=identifier, path=path, **fields)


def names(decks):
    return [each.metadata.name for each in decks]


@pytest.fixture
def library(monkeypatch):
    shelf = SimpleNamespace(decks=())

    def decks_containing(card_id):
        return [
            (each, card)
            for each in shelf.decks
            for card in each.cards
            if card.canonical_id == card_id
        ]

    stub = SimpleNamespace(decks=lambda: shelf.decks, decks_containing=decks_containing)
    monkeypatch.setattr(module, "deck_library", stub)
    return shelf


def test_both_groups_go_by_name_and_the_reference_deck_has_no_place_of_its_own(library):
    # The library lists the reference deck first
    library.decks = (deck("Rider"), deck("cedar"), deck("Aurora"), deck("Birch"), deck("dune"))
    curation.set_deck_pinned("x/deck/rider", True)
    curation.set_deck_pinned("x/deck/dune", True)

    pinned, rest = deck_choices()

    assert names(pinned) == ["dune", "Rider"]
    assert names(rest) == ["Aurora", "Birch", "cedar"]


def test_one_name_is_ordered_by_path(library):
    library.decks = (deck("Same", path="/b"), deck("Same", path="/a"))

    _, rest = deck_choices()

    assert [each.root_path for each in rest] == ["/a", "/b"]


def test_a_hidden_deck_is_left_out_unless_it_is_current(library):
    hidden = deck("Birch")
    library.decks = (deck("Aurora"), hidden)
    curation.set_deck_hidden("x/deck/birch", True)

    assert names(deck_choices()[1]) == ["Aurora"]
    assert names(deck_choices(current=hidden)[1]) == ["Aurora", "Birch"]
    assert names(deck_choices(current=hidden.root_path)[1]) == ["Aurora", "Birch"]


def test_a_current_deck_keeps_its_pin(library):
    pinned_deck = deck("Birch")
    library.decks = (deck("Aurora"), pinned_deck)
    curation.set_deck_pinned("x/deck/birch", True)

    pinned, rest = deck_choices(current=pinned_deck)

    assert names(pinned) == ["Birch"]
    assert names(rest) == ["Aurora"]


def test_containing_pairs_each_deck_with_its_card(library):
    library.decks = (deck("Birch", majors=3), deck("Aurora", majors=1), deck("Cedar", majors=3))
    curation.set_deck_pinned("x/deck/cedar", True)

    pinned, rest = deck_choices(containing="major_arcana.2")

    assert [(each.metadata.name, card.canonical_id) for each, card in pinned] == [
        ("Cedar", "major_arcana.2")
    ]
    assert [(each.metadata.name, card.canonical_id) for each, card in rest] == [
        ("Birch", "major_arcana.2")
    ]


def test_a_deck_with_no_identifier_is_never_pinned_or_hidden(library, curation_file):
    library.decks = (deck("Aurora", identifier=None),)
    # By hand: the app refuses to write an empty identifier
    curation_file.write_text('[decks]\npinned = [""]\nhidden = [""]\n')

    pinned, rest = deck_choices()

    assert pinned == []
    assert names(rest) == ["Aurora"]
