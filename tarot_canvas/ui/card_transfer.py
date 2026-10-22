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
    return cards_mime_data([card], deck, is_reversed)


def cards_mime_data(cards, deck, is_reversed=False):
    """Build one payload for cards of one deck, in order.

    card_id names the first card, so a reader that knows only one still reads it.
    """
    first = cards[0]
    payload = {
        "v": PAYLOAD_VERSION,
        "card_id": first["id"],
        "deck_path": os.fspath(deck.deck_path),
        "reversed": bool(is_reversed),
    }
    if len(cards) > 1:
        payload["card_ids"] = [card["id"] for card in cards]
    mime = QMimeData()
    mime.setData(CARD_MIME, json.dumps(payload).encode("utf-8"))
    mime.setText("\n".join(f"{card['name']} \N{EM DASH} {deck.get_name()}" for card in cards))

    image_path = first.get("image")
    if len(cards) == 1 and image_path and os.path.exists(image_path):
        image = QImage(image_path)
        if not image.isNull():
            mime.setImageData(image)

    return mime


def card_from_mime(mime, decks):
    """(card, deck, reversed) for the first card mime carries, or None"""
    resolved = cards_from_mime(mime, decks)
    return resolved[0] if resolved else None


def cards_from_mime(mime, decks):
    """[(card, deck, reversed), ...] for every card mime carries that resolves"""
    if not has_card(mime):
        return []

    try:
        payload = json.loads(bytes(mime.data(CARD_MIME)).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        logger.warning("Card payload is not valid JSON")
        return []

    if not isinstance(payload, dict) or payload.get("v") != PAYLOAD_VERSION:
        logger.warning(f"Unknown card payload version: {payload!r}")
        return []

    key = deck_path_key(payload.get("deck_path"))
    deck = next((d for d in decks if key and deck_path_key(d.deck_path) == key), None)
    if deck is None:
        logger.warning(f"Card payload names a deck that is not installed: {key}")
        return []

    card_ids = payload.get("card_ids")
    if not isinstance(card_ids, list):
        card_ids = [payload.get("card_id")]

    is_reversed = bool(payload.get("reversed", False))
    resolved = []
    for card_id in card_ids:
        card = deck.get_card_by_id(card_id)
        if card is None:
            logger.warning(f"{deck.get_name()} has no card {card_id!r}")
            continue
        resolved.append((card, deck, is_reversed))
    return resolved


def copy_card_to_clipboard(card, deck, is_reversed=False):
    copy_cards_to_clipboard([card], deck, is_reversed)


def copy_cards_to_clipboard(cards, deck, is_reversed=False):
    QGuiApplication.clipboard().setMimeData(cards_mime_data(cards, deck, is_reversed))
