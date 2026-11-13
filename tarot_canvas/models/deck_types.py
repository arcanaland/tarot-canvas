import enum
import typing
from collections.abc import Sequence
from dataclasses import dataclass


class CardKind(enum.Enum):
    MAJOR = "major_arcana"
    MINOR = "minor_arcana"


@dataclass(frozen=True, slots=True)
class CardImage:
    path: str
    kind: str
    height: int | None = None


@dataclass(frozen=True, slots=True)
class Card:
    canonical_id: str
    kind: CardKind
    display_name: str
    suit_key: str | None = None
    rank_key: str | None = None
    display_suit: str | None = None
    display_rank: str | None = None
    number: str | None = None
    position: int | None = None
    alt_text: str | None = None
    images: tuple[CardImage, ...] = ()

    def default_image(self):
        return self.images[0].path if self.images else None

    def raster_for(self, target_height):
        """The smallest raster at or above target_height, else the largest below it."""
        rasters = [i for i in self.images if i.kind == "raster" and i.height is not None]
        if not rasters:
            return None
        covering = [image for image in rasters if image.height >= target_height]
        if covering:
            return min(covering, key=lambda image: image.height).path
        return max(rasters, key=lambda image: image.height).path


@dataclass(frozen=True, slots=True)
class DeckLink:
    rel: str
    url: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class DeckMetadata:
    name: str
    identifier: str | None = None
    schema_version: str | None = None
    version: str | None = None
    artist: str | None = None
    description: str | None = None
    license: str | None = None
    attribution: str | None = None
    publisher: str | None = None
    website: str | None = None
    copyright: str | None = None
    created_date: str | None = None
    updated_date: str | None = None
    published_date: str | None = None
    pattern: str | None = None
    tags: tuple[str, ...] = ()
    links: tuple[DeckLink, ...] = ()


@dataclass(frozen=True, slots=True)
class SuitInfo:
    key: str
    name: str
    excluded: bool = False


class Deck(typing.Protocol):
    root_path: str

    @property
    def metadata(self) -> DeckMetadata: ...

    @property
    def cards(self) -> tuple[Card, ...]: ...

    @property
    def suits(self) -> tuple[SuitInfo, ...]: ...

    @property
    def exclusion_reason(self) -> str | None: ...

    def find_card(self, card_id: str) -> Card | None: ...

    def cards_of_kind(self, kind: CardKind) -> Sequence[Card]: ...

    def cards_in_suit(self, suit_key: str) -> Sequence[Card]: ...

    def random_card(self) -> Card | None: ...

    def display_rank_name(self, rank_key: str) -> str: ...

    def get_card_backs(self) -> tuple[dict[str, str], str]: ...
