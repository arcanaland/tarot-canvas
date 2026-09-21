"""The 78 canonical card slots, and what a source has to say about each one.

Both the notes index and the esoterica reader answer the same question over the same
coordinate space, so the order and the cell vocabulary live here rather than in either.
"""

from enum import Enum

MAJOR_ARCANA_COUNT = 22

SUITS = ("wands", "cups", "swords", "pentacles")

RANKS = (
    "ace",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "page",
    "knight",
    "queen",
    "king",
)


def _canonical_card_ids():
    ids = [f"major_arcana.{i:02d}" for i in range(MAJOR_ARCANA_COUNT)]
    for suit in SUITS:
        ids.extend(f"minor_arcana.{suit}.{rank}" for rank in RANKS)
    return tuple(ids)


CANONICAL_CARD_IDS = _canonical_card_ids()


class CellState(Enum):
    """One cell of a coverage run."""

    FILLED = "filled"
    FAINT = "faint"
    EMPTY = "empty"
