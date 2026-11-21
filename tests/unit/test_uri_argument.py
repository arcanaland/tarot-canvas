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


@pytest.fixture
def opened_files():
    paths = []
    return paths, SimpleNamespace(open_deck_file_temporarily=paths.append)


def test_a_tarotdeck_path_or_file_url_opens(opened_files, tmp_path):
    paths, window = opened_files
    container = tmp_path / "My Deck.TarotDeck"
    container.write_bytes(b"PK")

    main.process_uri_argument([str(container)], window)
    main.process_uri_argument([container.as_uri()], window)

    assert paths == [container, container]


@pytest.mark.parametrize("name", ["missing.tarotdeck", "deck.zip"])
def test_a_missing_or_other_file_does_not_open(opened_files, tmp_path, name):
    paths, window = opened_files
    (tmp_path / "deck.zip").write_bytes(b"PK")

    main.process_uri_argument([str(tmp_path / name)], window)

    assert paths == []
