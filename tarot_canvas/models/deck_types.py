import enum
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
