"""Decks read by libarcana's arcana_tarot, copied into deck_types."""

import logging
import os
import random

import arcana_tarot

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS, roman
from tarot_canvas.models.deck_types import (
    Card,
    CardImage,
    CardKind,
    DeckLink,
    DeckLoadError,
    DeckMetadata,
    SuitInfo,
)

log = logging.getLogger(__name__)

UNKNOWN_DECK = "Unknown Deck"
RASTER_EXTENSIONS = (".png", ".webp", ".avif", ".jpg", ".jpeg")
DEFAULT_FACE_HEIGHT = 1200

METADATA_TEXT_FIELDS = (
    "identifier",
    "schema_version",
    "version",
    "artist",
    "description",
    "license",
    "attribution",
    "publisher",
    "website",
    "copyright",
    "created_date",
    "updated_date",
    "published_date",
)


def _text(value):
    if value is None:
        return None
    return str(value).strip() or None


def _links(metadata):
    # A 1.x deck's website comes back as a homepage link too
    synthesized = metadata.website if arcana_tarot.schema_major(metadata) < 2 else None
    out = []
    for link in metadata.links:
        if not link.rel_name or (link.rel_name == "homepage" and link.url == synthesized):
            continue
        url = (link.url or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        out.append(DeckLink(link.rel_name, url, _text(link.title)))
    return tuple(out)


def _pattern(related, root_path):
    targets = [relation.target for relation in related if relation.rel_name == "pattern"]
    if len(targets) > 1:
        log.warning(
            "%s: [deck].related names more than one pattern, so the deck is read as having none",
            root_path,
        )
        return None
    return _text(targets[0]) if targets else None


def _metadata(metadata, root_path):
    return DeckMetadata(
        name=_text(metadata.name) or UNKNOWN_DECK,
        pattern=_pattern(metadata.related, root_path),
        tags=tuple(tag for tag in (_text(tag) for tag in metadata.tags) if tag),
        links=_links(metadata),
        **{field: _text(getattr(metadata, field)) for field in METADATA_TEXT_FIELDS},
    )


def _images(card):
    """The default variant's faces: libarcana's pick at DEFAULT_FACE_HEIGHT, then the other rasters."""
    best = card.best_raster_for_height(DEFAULT_FACE_HEIGHT) or card.scalable_image()
    if best is None:
        return ()
    rest = sorted(
        (
            image
            for image in card.images
            if image.variant_key == card.default_variant
            and image.kind == arcana_tarot.image_kind.raster
            and image.height is not None
            and image.path != best.path
        ),
        key=lambda image: -image.height,
    )
    return tuple(_card_image(image) for image in (best, *rest))


def _card_image(image):
    if image.kind == arcana_tarot.image_kind.scalable:
        return CardImage(os.fspath(image.path), "scalable")
    return CardImage(os.fspath(image.path), "raster", image.height)


def _numeral(card):
    if card.declared.unnumbered:
        return None
    if card.declared.number:
        return card.declared.number
    return roman(card.position).upper() or "0"


def _card(card, rank_names):
    canonical_id = card.canonical_id()
    if card.id.is_major():
        standard = card.id.cls == arcana_tarot.card_class.standard_major
        number = _numeral(card) if standard else card.number or None
        key = canonical_id.removeprefix("major_arcana.")
        return Card(
            canonical_id=canonical_id,
            kind=CardKind.MAJOR,
            display_name=card.display_name or number or key,
            number=number,
            position=card.position,
            alt_text=card.alt_text or None,
            images=_images(card),
        )
    _, suit_key, rank_key = canonical_id.split(".", 2)
    display_rank = card.display_rank or None
    fallback = rank_names.get(rank_key) or rank_key.capitalize()
    return Card(
        canonical_id=canonical_id,
        kind=CardKind.MINOR,
        display_name=card.display_name or fallback,
        suit_key=suit_key,
        rank_key=rank_key,
        display_suit=card.display_suit or None,
        display_rank=display_rank,
        number=card.number or None,
        position=card.position,
        alt_text=card.alt_text or None,
        images=_images(card),
    )


class ArcanaDeck:  # implements deck_types.Deck
    def __init__(self, root_path, deck):
        self.root_path = root_path
        self._metadata = _metadata(deck.metadata, root_path)
        self._rank_names = {rank.key: rank.name for rank in deck.ranks if rank.name}
        self._cards = tuple(_card(card, self._rank_names) for card in deck.cards)
        self._suits = tuple(SuitInfo(s.key, s.name, s.excluded) for s in deck.suits)
        present = {card.canonical_id for card in self._cards}
        self._exclusion_reason = next(
            (
                reason
                for card_id in CANONICAL_CARD_IDS
                if card_id not in present and (reason := deck.exclusion_reason(card_id))
            ),
            None,
        )
        self._backs = {
            back.id: os.fspath(back.image)
            for back in sorted(deck.card_backs, key=lambda back: back.id)
            if back.image and os.path.splitext(os.fspath(back.image))[1] in RASTER_EXTENSIONS
        }
        self._default_back = deck.default_card_back or "classic"
        log.info("Loaded %s cards for deck: %s", len(self._cards), self._metadata.name)

    @property
    def metadata(self):
        return self._metadata

    @property
    def cards(self):
        return self._cards

    @property
    def suits(self):
        return self._suits

    @property
    def exclusion_reason(self):
        return self._exclusion_reason

    def find_card(self, card_id):
        return next((card for card in self._cards if card.canonical_id == card_id), None)

    def cards_of_kind(self, kind):
        return [card for card in self._cards if card.kind is kind]

    def cards_in_suit(self, suit_key):
        return [card for card in self._cards if card.suit_key == suit_key]

    def random_card(self):
        return random.choice(self._cards) if self._cards else None

    def display_rank_name(self, rank_key):
        return self._rank_names.get(rank_key) or rank_key.capitalize()

    def get_card_backs(self):
        return dict(self._backs), self._default_back


def load_deck(path):
    try:
        deck = arcana_tarot.load_deck(path)
    except arcana_tarot.deck_error as e:
        raise DeckLoadError(str(e.code).removeprefix("error_code."), e.message) from e
    return ArcanaDeck(path, deck)
