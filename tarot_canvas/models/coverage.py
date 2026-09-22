from enum import Enum


class CellState(Enum):
    """One cell of a coverage run."""

    FILLED = "filled"
    FAINT = "faint"
    EMPTY = "empty"
