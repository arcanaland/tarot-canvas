import os

import pytest

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.coverage import CANONICAL_CARD_IDS, CellState

STUB = "# Untitled Note\n\n"
WRITTEN = "# Untitled Note\n\nThe Chariot is a card about momentum.\n"


def write_note(base, card_id, filename, body=WRITTEN, mtime=None):
    card_dir = base / card_id
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / filename
    path.write_text(body, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_canonical_order_is_the_majors_then_four_suits():
    assert len(CANONICAL_CARD_IDS) == 78
    assert len(set(CANONICAL_CARD_IDS)) == 78
    assert CANONICAL_CARD_IDS[0] == "major_arcana.00"
    assert CANONICAL_CARD_IDS[21] == "major_arcana.21"
    assert CANONICAL_CARD_IDS[22] == "minor_arcana.wands.ace"
    assert CANONICAL_CARD_IDS[-1] == "minor_arcana.pentacles.king"


def test_an_empty_card_directory_is_not_notes(tmp_path):
    (tmp_path / "major_arcana.00").mkdir()
    write_note(tmp_path, "major_arcana.07", "1700000000_Chariot.md")

    index = notes_model.scan(tmp_path)

    assert "major_arcana.00" not in index
    assert list(index) == ["major_arcana.07"]

    states = notes_model.coverage(index)
    assert states[0] is CellState.EMPTY
    assert states[7] is CellState.FILLED


def test_a_note_under_an_unknown_card_id_is_kept_but_lights_no_cell(tmp_path):
    write_note(tmp_path, "major_arcana.99", "1700000000_Ghost.md")

    index = notes_model.scan(tmp_path)

    assert "major_arcana.99" in index
    assert notes_model.coverage(index) == [CellState.EMPTY] * 78


def test_the_same_title_under_two_cards_does_not_collide(tmp_path):
    write_note(tmp_path, "major_arcana.00", "1700000000_Untitled_Note.md")
    write_note(tmp_path, "major_arcana.01", "1700000001_Untitled_Note.md")

    index = notes_model.scan(tmp_path)
    everything = [note for notes in index.values() for note in notes]

    assert [note.title for note in everything] == ["Untitled Note", "Untitled Note"]
    assert len({note.path for note in everything}) == 2
    assert {note.card_id for note in everything} == {"major_arcana.00", "major_arcana.01"}


def test_a_stub_note_is_indexed_and_marked_bodiless(tmp_path):
    write_note(tmp_path, "major_arcana.00", "1700000000_Stub.md", body=STUB)
    write_note(tmp_path, "major_arcana.01", "1700000000_Written.md", body=WRITTEN)

    index = notes_model.scan(tmp_path)

    assert index["major_arcana.00"][0].has_body is False
    assert index["major_arcana.01"][0].has_body is True

    states = notes_model.coverage(index)
    assert states[0] is CellState.FILLED


def test_a_cards_notes_come_back_newest_first(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000_Older.md", mtime=1700000000)
    write_note(tmp_path, "major_arcana.07", "1700000001_Newer.md", mtime=1800000000)

    notes = notes_model.scan(tmp_path)["major_arcana.07"]

    assert [note.title for note in notes] == ["Newer", "Older"]


def test_an_unreadable_note_is_skipped_rather_than_raising(tmp_path):
    readable = write_note(tmp_path, "major_arcana.07", "1700000000_Readable.md")
    unreadable = write_note(tmp_path, "major_arcana.07", "1700000001_Unreadable.md")
    unreadable.chmod(0o000)

    try:
        if os.access(unreadable, os.R_OK):
            pytest.skip("cannot make a file unreadable here (running as root?)")

        notes = notes_model.scan(tmp_path)["major_arcana.07"]

        assert readable in [note.path for note in notes]
        bad = next(note for note in notes if note.path == unreadable)
        assert bad.has_body is False
    finally:
        unreadable.chmod(0o600)


def test_a_missing_base_is_an_empty_index(tmp_path):
    assert notes_model.scan(tmp_path / "nothing-here") == {}


def test_coverage_is_one_state_per_canonical_slot(tmp_path):
    write_note(tmp_path, "minor_arcana.pentacles.king", "1700000000_Last.md")

    states = notes_model.coverage(notes_model.scan(tmp_path))

    assert len(states) == 78
    assert states[-1] is CellState.FILLED
    assert states[:-1] == [CellState.EMPTY] * 77


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("1700000000_Untitled_Note.md", "Untitled Note"),
        ("no_timestamp_here.md", "no timestamp here"),
        ("Plain.md", "Plain"),
    ],
)
def test_display_name_from_filename(filename, expected):
    assert notes_model.display_name_from_filename(filename) == expected


def one_note(base, body):
    write_note(base, "major_arcana.07", "1700000000_Chariot.md", body=body)
    return notes_model.scan(base)["major_arcana.07"][0]


def test_the_first_body_line_skips_the_heading(tmp_path):
    note = one_note(tmp_path, WRITTEN)

    assert notes_model.first_body_line(note) == "The Chariot is a card about momentum."


def test_a_stub_has_no_first_body_line(tmp_path):
    assert notes_model.first_body_line(one_note(tmp_path, STUB)) == ""


def test_a_search_finds_the_line_it_matched(tmp_path):
    note = one_note(tmp_path, "# Chariot\n\nfirst line\nabout MOMENTUM and control\n")

    assert notes_model.matching_line(note, "momentum") == "about MOMENTUM and control"


def test_a_search_never_matches_the_heading(tmp_path):
    """The heading is the title, which the caller has already searched."""
    note = one_note(tmp_path, "# Chariot\n\na body\n")

    assert notes_model.matching_line(note, "Chariot") is None


def test_an_empty_search_matches_nothing(tmp_path):
    assert notes_model.matching_line(one_note(tmp_path, WRITTEN), "") is None


def test_an_unreadable_note_has_no_lines(tmp_path):
    note = one_note(tmp_path, WRITTEN)
    note.path.chmod(0o000)
    try:
        assert notes_model.first_body_line(note) == ""
        assert notes_model.matching_line(note, "momentum") is None
    finally:
        note.path.chmod(0o644)
