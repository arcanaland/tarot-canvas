"""What the notes pane shows for the selected card."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CardNotesDetails:
    card_id: str
    name: str | None
    cover_path: str | None
    notes: tuple  # of models.notes.Note, newest first
