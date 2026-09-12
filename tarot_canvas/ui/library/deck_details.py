"""What the library's details pane shows for one row, installed or not"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt

from tarot_canvas.ui.library.deck_downloads import DeckState, deck_downloads
from tarot_canvas.ui.library.deck_model import (
    CardCountRole,
    CoverPathRole,
    DeckRole,
    EntryRole,
    ProgressRole,
    StateRole,
)


@dataclass(frozen=True)
class DeckDetails:
    """Every field is None when there's nothing to show; the pane hides its row."""

    name: str | None
    artist: str | None
    cover_path: str | None
    card_count: int | None
    version: str | None
    license: str | None
    attribution: str | None
    description: str | None
    size: int | None  # bytes, for a deck not yet downloaded
    state: DeckState
    progress: float | None  # 0.0-1.0, while downloading
    failure: object | None  # the DownloadFailure, when FAILED
    deck: object | None
    entry: object | None


def details_for(index):
    deck = index.data(DeckRole)
    if deck is not None:
        return _installed(index, deck)
    return _available(index, index.data(EntryRole))


def _installed(index, deck):
    return DeckDetails(
        name=_text(index.data(Qt.ItemDataRole.DisplayRole)),
        # Not AuthorRole, which says "Unknown" for a deck that names nobody
        artist=_text(deck.get_author()),
        cover_path=index.data(CoverPathRole),
        card_count=index.data(CardCountRole) or None,
        # Not get_version(), which invents "Unknown Version"
        version=_text(deck.get_metadata_fields().get("version")),
        license=_text(deck.get_license()),
        attribution=_text(deck.get_attribution()),
        description=_text(deck.get_description()),
        size=None,
        state=DeckState.INSTALLED,
        progress=None,
        failure=None,
        deck=deck,
        entry=None,
    )


def _available(index, entry):
    state = index.data(StateRole)
    return DeckDetails(
        name=_text(entry.name),
        artist=_text(entry.artist),
        cover_path=index.data(CoverPathRole),
        card_count=entry.card_count or None,
        version=_text(entry.version),
        license=_text(entry.license),
        attribution=_text(entry.attribution),
        description=_text(entry.description),
        size=entry.package_size or None,
        state=state,
        progress=index.data(ProgressRole) if state is DeckState.DOWNLOADING else None,
        failure=deck_downloads().failure(entry.slug) if state is DeckState.FAILED else None,
        deck=None,
        entry=entry,
    )


def _text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None
