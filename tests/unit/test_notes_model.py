"""The notes index as a list of notes."""

from types import SimpleNamespace

import pytest

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.notes import Note
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.library.notes_model import (
    CardIdRole,
    NoteRole,
    NotesListModel,
    PreviewRole,
)

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"


def note(tmp_path, card_id, title, body="", modified=1_700_000_000.0):
    card_dir = tmp_path / card_id
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / f"{int(modified)}_{title.replace(' ', '_')}.md"
    path.write_text(f"# {title}\n\n{body}", encoding="utf-8")
    return Note(
        card_id=card_id,
        path=path,
        title=title,
        modified=modified,
        has_body=bool(body.strip()),
        first_line=title,
        first_line_is_heading=True,
    )


@pytest.fixture
def deck():
    names = {FOOL: "The Fool", MAGICIAN: "The Magician"}

    def get_card_by_id(card_id):
        if card_id not in names:
            return None
        return {"id": card_id, "name": names[card_id], "image": f"/art/{card_id}.png"}

    return SimpleNamespace(get_card_by_id=get_card_by_id)


def ids(model):
    return [model.index(row, 0).data(CardIdRole) for row in range(model.rowCount())]


# -- the list ------------------------------------------------------------


def test_the_list_is_one_row_per_note_newest_first(tmp_path, deck):
    old = note(tmp_path, FOOL, "Old", modified=1_700_000_000.0)
    new = note(tmp_path, MAGICIAN, "New", modified=1_800_000_000.0)
    model = NotesListModel({FOOL: [old], MAGICIAN: [new]}, deck)

    assert model.rowCount() == 2
    assert model.index(0, 0).data(NoteRole) == new
    assert model.index(1, 0).data(NoteRole) == old


def test_a_note_under_an_unknown_card_is_still_listed(tmp_path, deck):
    stray = note(tmp_path, "not.a.card", "Stray")
    model = NotesListModel({"not.a.card": [stray]}, deck)

    assert model.rowCount() == 1
    assert model.index(0, 0).data(CardIdRole) == "not.a.card"


def test_a_row_says_which_card_it_hangs_on(tmp_path, deck):
    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "One")]}, deck)

    assert "The Fool" in model.index(0, 0).data(SubtitleRole)


def test_an_unnamed_note_is_listed_by_its_opening_line(tmp_path, deck):
    (tmp_path / FOOL).mkdir()
    (tmp_path / FOOL / "1700000000.md").write_text("a leap into thin air\n", encoding="utf-8")
    model = NotesListModel(notes_model.scan(tmp_path), deck)

    assert model.index(0, 0).data() == "a leap into thin air"

    model.set_search("thin air")
    assert ids(model) == [FOOL]


def test_search_matches_the_card_name(tmp_path, deck):
    index = {
        FOOL: [note(tmp_path, FOOL, "One")],
        MAGICIAN: [note(tmp_path, MAGICIAN, "Two")],
    }
    model = NotesListModel(index, deck)
    model.set_search("magic")

    assert ids(model) == [MAGICIAN]


def test_search_matches_a_note_title(tmp_path, deck):
    index = {FOOL: [note(tmp_path, FOOL, "Beginnings")], MAGICIAN: [note(tmp_path, MAGICIAN, "X")]}
    model = NotesListModel(index, deck)
    model.set_search("beginn")

    assert ids(model) == [FOOL]


def test_clearing_the_search_brings_every_note_back(tmp_path, deck):
    index = {FOOL: [note(tmp_path, FOOL, "One")], MAGICIAN: [note(tmp_path, MAGICIAN, "Two")]}
    model = NotesListModel(index, deck)
    model.set_search("magic")
    model.set_search("")

    assert model.rowCount() == 2


def test_notes_for_a_card_ignores_the_search(tmp_path, deck):
    index = {FOOL: [note(tmp_path, FOOL, "One")]}
    model = NotesListModel(index, deck)
    model.set_search("nothing here")

    assert [n.title for n in model.notes_for(FOOL)] == ["One"]
    assert model.notes_for(MAGICIAN) == []


# -- the preview line ----------------------------------------------------


def test_the_preview_is_the_first_line_of_prose(tmp_path, deck):
    body = "a leap into thin air\nand a second line\n"
    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "Untitled", body=body)]}, deck)

    assert model.index(0, 0).data(PreviewRole) == "a leap into thin air"


def test_a_stub_has_a_blank_preview(tmp_path, deck):
    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "Untitled")]}, deck)

    assert model.index(0, 0).data(PreviewRole) == ""


def test_a_body_match_becomes_the_preview_and_leaves_the_subtitle_alone(tmp_path, deck):
    body = "the opening line\na leap into thin air\n"
    index = {FOOL: [note(tmp_path, FOOL, "Untitled", body=body)]}
    model = NotesListModel(index, deck)
    subtitle = model.index(0, 0).data(SubtitleRole)

    model.set_search("thin air")

    row = model.index(0, 0)
    assert row.data(PreviewRole) == "a leap into thin air"
    assert row.data(SubtitleRole) == subtitle
    assert "The Fool" in subtitle


def test_a_title_match_previews_the_first_line(tmp_path, deck):
    index = {FOOL: [note(tmp_path, FOOL, "Beginnings", body="a leap\n")]}
    model = NotesListModel(index, deck)
    model.set_search("beginn")

    row = model.index(0, 0)
    assert row.data(PreviewRole) == "a leap"
    assert "The Fool" in row.data(SubtitleRole)


def test_the_preview_is_read_with_the_index_not_with_the_row(tmp_path, deck, monkeypatch):
    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "One", body="a leap\n")]}, deck)

    def refuse(*_args):
        raise AssertionError("data() read a note from disk")

    monkeypatch.setattr(notes_model, "first_body_line", refuse)
    monkeypatch.setattr(notes_model, "_body_lines", refuse)

    assert model.index(0, 0).data(PreviewRole) == "a leap"


def test_a_search_that_matches_nothing_empties_the_list(tmp_path, deck):
    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "One")]}, deck)
    model.set_search("nothing here")

    assert model.rowCount() == 0
    assert model.total_rows() == 1
