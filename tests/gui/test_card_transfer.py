import json
import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QMimeData

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.card_transfer import (
    CARD_MIME,
    card_from_mime,
    card_mime_data,
    cards_from_mime,
    cards_mime_data,
    copy_card_to_clipboard,
    copy_cards_to_clipboard,
)
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture
def card(minimal_deck):
    return minimal_deck.get_card_by_id("major_arcana.00")


def payload(mime):
    return json.loads(bytes(mime.data(CARD_MIME)).decode())


def with_payload(**fields):
    mime = QMimeData()
    mime.setData(CARD_MIME, json.dumps(fields).encode())
    return mime


def test_a_card_survives_the_round_trip(qapp, minimal_deck, card):
    for is_reversed in (False, True):
        resolved = card_from_mime(card_mime_data(card, minimal_deck, is_reversed), [minimal_deck])

        assert resolved is not None
        got_card, got_deck, got_reversed = resolved
        assert got_card["id"] == "major_arcana.00"
        assert got_deck is minimal_deck
        assert got_reversed is is_reversed


def test_the_payload_is_an_identity_not_a_picture(qapp, minimal_deck, card):
    assert payload(card_mime_data(card, minimal_deck)) == {
        "v": 1,
        "card_id": "major_arcana.00",
        "deck_path": str(MINIMAL_DECK_PATH),
        "reversed": False,
    }


def test_a_deck_named_by_path_object_resolves_against_one_named_by_str(qapp, card):
    """The reference deck carries a Path; every other deck a str."""
    by_path = TarotDeck(Path(MINIMAL_DECK_PATH))
    by_str = TarotDeck(str(MINIMAL_DECK_PATH))

    resolved = card_from_mime(card_mime_data(card, by_path), [by_str])
    assert resolved is not None
    assert resolved[1] is by_str


def test_the_copied_deck_is_the_one_resolved(qapp, tmp_path, minimal_deck):
    """Same card_id in two decks: the payload picks the deck, not the first match."""
    shutil.copytree(MINIMAL_DECK_PATH, tmp_path / "other")
    other = TarotDeck(str(tmp_path / "other"))
    mime = card_mime_data(other.get_card_by_id("major_arcana.01"), other)

    _, deck, _ = card_from_mime(mime, [minimal_deck, other])
    assert deck is other


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"v": 2, "card_id": "major_arcana.00"}, id="unknown version"),
        pytest.param({"card_id": "major_arcana.00"}, id="no version"),
        pytest.param({"v": 1, "card_id": "major_arcana.00", "deck_path": "/gone"}, id="no deck"),
        pytest.param({"v": 1, "card_id": "major_arcana.02"}, id="excluded card"),
        pytest.param({"v": 1, "card_id": "not_a_card"}, id="unknown card"),
    ],
)
def test_what_cannot_be_resolved_gives_none(qapp, minimal_deck, fields):
    fields.setdefault("deck_path", str(MINIMAL_DECK_PATH))
    assert card_from_mime(with_payload(**fields), [minimal_deck]) is None


def test_garbage_in_our_format_gives_none(qapp, minimal_deck):
    mime = QMimeData()
    mime.setData(CARD_MIME, b"\xff not json")
    assert card_from_mime(mime, [minimal_deck]) is None


def test_only_our_format_is_ever_a_card(qapp, minimal_deck, card):
    """An image or a line of text from another app has no card_id."""
    ours = card_mime_data(card, minimal_deck)
    foreign = QMimeData()
    foreign.setText(ours.text())
    foreign.setImageData(ours.imageData())

    assert card_from_mime(foreign, [minimal_deck]) is None
    assert card_from_mime(None, [minimal_deck]) is None


def test_other_apps_get_text_and_the_art(qapp, minimal_deck, card):
    mime = card_mime_data(card, minimal_deck)

    assert mime.text() == f"{card['name']} \N{EM DASH} Minimal Test Deck"
    assert mime.hasImage()


def test_a_card_without_art_still_copies(qapp, minimal_deck, card):
    mime = card_mime_data(dict(card, image=None), minimal_deck)

    assert not mime.hasImage()
    assert card_from_mime(mime, [minimal_deck]) is not None


def test_copying_puts_the_card_on_the_clipboard(clipboard, minimal_deck, card):
    copy_card_to_clipboard(card, minimal_deck, is_reversed=True)

    assert clipboard.mimeData().hasFormat(CARD_MIME)
    assert card_from_mime(clipboard.mimeData(), [minimal_deck])[2] is True


THREE_CARDS = ["minor_arcana.cups.two", "major_arcana.00", "minor_arcana.wands.king"]


def test_several_cards_survive_the_round_trip_in_order(qapp, full_deck):
    cards = [full_deck.get_card_by_id(card_id) for card_id in THREE_CARDS]

    resolved = cards_from_mime(cards_mime_data(cards, full_deck), [full_deck])

    assert [card["id"] for card, _, _ in resolved] == THREE_CARDS
    assert all(deck is full_deck for _, deck, _ in resolved)


def test_a_several_card_payload_still_names_its_first_card_alone(qapp, full_deck):
    """A reader that knows only card_id reads the first card."""
    cards = [full_deck.get_card_by_id(card_id) for card_id in THREE_CARDS]
    mime = cards_mime_data(cards, full_deck)

    assert payload(mime)["card_id"] == THREE_CARDS[0]
    assert payload(mime)["card_ids"] == THREE_CARDS
    assert card_from_mime(mime, [full_deck])[0]["id"] == THREE_CARDS[0]
    assert mime.text().splitlines() == [
        f"{card['name']} \N{EM DASH} Full Test Deck" for card in cards
    ]
    assert not mime.hasImage()


def test_a_one_card_payload_reads_as_one_card(qapp, minimal_deck):
    mime = with_payload(v=1, card_id="major_arcana.01", deck_path=str(MINIMAL_DECK_PATH))

    resolved = cards_from_mime(mime, [minimal_deck])
    assert [card["id"] for card, _, _ in resolved] == ["major_arcana.01"]


def test_an_unknown_card_among_several_is_skipped(qapp, minimal_deck):
    mime = with_payload(
        v=1,
        card_id="major_arcana.00",
        card_ids=["major_arcana.00", "major_arcana.02", "major_arcana.01"],
        deck_path=str(MINIMAL_DECK_PATH),
    )

    resolved = cards_from_mime(mime, [minimal_deck])
    assert [card["id"] for card, _, _ in resolved] == ["major_arcana.00", "major_arcana.01"]


def test_copying_several_cards_is_one_clipboard_write(qapp, clipboard, full_deck):
    writes = []
    clipboard.dataChanged.connect(lambda: writes.append(1))
    cards = [full_deck.get_card_by_id(card_id) for card_id in THREE_CARDS]

    copy_cards_to_clipboard(cards, full_deck)

    assert len(writes) == 1
    assert [card["id"] for card, _, _ in cards_from_mime(clipboard.mimeData(), [full_deck])] == (
        THREE_CARDS
    )
