from types import SimpleNamespace

import pytest

from tarot_canvas import main


@pytest.fixture
def opened(monkeypatch, minimal_deck):
    monkeypatch.setattr(main.deck_library, "reference", lambda: minimal_deck)
    cards = []
    return cards, SimpleNamespace(open_card_view=lambda card, deck: cards.append(card))


@pytest.mark.parametrize("uri", ["tarot://major_arcana.00", "tarot://major_arcana.00/"])
def test_a_card_uri_opens_its_card(opened, uri):
    cards, window = opened
    main.process_uri_argument([uri], window)
    assert [card.canonical_id for card in cards] == ["major_arcana.00"]


@pytest.mark.parametrize("args", [[], ["tarot://major_arcana.21"], ["https://example.com"]])
def test_nothing_opens_without_a_card(opened, args):
    cards, window = opened
    main.process_uri_argument(args, window)
    assert cards == []
