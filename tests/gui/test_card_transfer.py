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
    copy_card_to_clipboard,
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
