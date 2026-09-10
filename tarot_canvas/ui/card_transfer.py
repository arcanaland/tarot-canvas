"""A card in transit: one QMimeData for the clipboard and for drag-and-drop.

The payload is an identity, (card_id, deck, reversed), not a picture. The image and
text formats ride along for other applications only; paste and drop read our format.
"""

import json
import os

from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QGuiApplication, QImage

from tarot_canvas.utils.logger import logger

CARD_MIME = "application/x-tarot-canvas-card"
PAYLOAD_VERSION = 1


def deck_path_key(deck_path):
    """Normalized deck path, so a Path and a str naming one directory compare equal."""
    if not deck_path:
        return None
    return os.path.normcase(os.path.realpath(os.fspath(deck_path)))


def has_card(mime):
    """Cheap check for enabling a paste: our format is present, resolvable or not."""
    return mime is not None and mime.hasFormat(CARD_MIME)


def card_mime_data(card, deck, is_reversed=False):
    """Build the payload for card as rendered by deck."""
    payload = {
        "v": PAYLOAD_VERSION,
        "card_id": card["id"],
        "deck_path": os.fspath(deck.deck_path),
        "reversed": bool(is_reversed),
    }
    mime = QMimeData()
    mime.setData(CARD_MIME, json.dumps(payload).encode("utf-8"))
    mime.setText(f"{card['name']} \N{EM DASH} {deck.get_name()}")

    image_path = card.get("image")
    if image_path and os.path.exists(image_path):
        image = QImage(image_path)
        if not image.isNull():
            mime.setImageData(image)

    return mime


def card_from_mime(mime, decks):
    """Resolve a payload against decks: (card, deck, is_reversed), or None.

    None for anything that is not ours, a payload version we do not know, a deck that
    is no longer installed, or a card that deck does not have (excluded cards included).
    """
    if not has_card(mime):
        return None

    try:
        payload = json.loads(bytes(mime.data(CARD_MIME)).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        logger.warning("Card payload is not valid JSON")
        return None

    if not isinstance(payload, dict) or payload.get("v") != PAYLOAD_VERSION:
        logger.warning(f"Unknown card payload version: {payload!r}")
        return None

    key = deck_path_key(payload.get("deck_path"))
    deck = next((d for d in decks if key and deck_path_key(d.deck_path) == key), None)
    if deck is None:
        logger.warning(f"Card payload names a deck that is not installed: {key}")
        return None

    card = deck.get_card_by_id(payload.get("card_id"))
    if card is None:
        logger.warning(f"{deck.get_name()} has no card {payload.get('card_id')!r}")
        return None

    return card, deck, bool(payload.get("reversed", False))


def copy_card_to_clipboard(card, deck, is_reversed=False):
    QGuiApplication.clipboard().setMimeData(card_mime_data(card, deck, is_reversed))
