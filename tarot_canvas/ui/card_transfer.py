"""A card in transit: QMimeData for clipboard and drag-and-drop."""

import json
import os

from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QGuiApplication, QImage

from tarot_canvas.utils.logger import logger

CARD_MIME = "application/x-tarot-canvas-card"
PAYLOAD_VERSION = 1


def deck_path_key(deck_path):
    """Normalized deck path."""
    if not deck_path:
        return None
    return os.path.normcase(os.path.realpath(os.fspath(deck_path)))


def has_card(mime):
    return mime is not None and mime.hasFormat(CARD_MIME)


def card_mime_data(card, deck, is_reversed=False):
    """Build the payload for a card."""
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
