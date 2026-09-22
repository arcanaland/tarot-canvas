import os

import pytest

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.coverage import CellState

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


# The ten-note corpus measured on 2026-09-21 held four notes whose content would derive a
# title different from the one the user sees. The title stays in the filename, and these
# assert it: any of them coming back retitled means titles have started reading the file.

AWKWARD = [
    (
        "minor_arcana.swords.ten",
        "1789985333_Lyrics.md",
        '> "Even the longest night must end"\n',
        "Lyrics",
    ),
    ("major_arcana.04", "1747139002_Thoughts.md", "# Thoughts on The Emperor\n", "Thoughts"),
    ("major_arcana.01", "1757950787_Untitled_Note.md", "sdfs\n\n# A heading\n", "Untitled Note"),
    ("major_arcana.15", "1747138034_Untitled_Note.md", "asdasd# Untitled Note\n", "Untitled Note"),
]


@pytest.mark.parametrize(("card_id", "filename", "body", "expected"), AWKWARD)
def test_an_existing_notes_title_is_its_filename_and_never_its_content(
    tmp_path, card_id, filename, body, expected
):
    write_note(tmp_path, card_id, filename, body=body)

    note = notes_model.scan(tmp_path)[card_id][0]

    assert note.title == expected


def test_a_note_that_opens_with_a_blockquote_has_no_heading_to_skip(tmp_path):
    """The bug this fixes: line 0 was assumed to be a heading, dropping the quote."""
    note = one_note(tmp_path, '> "Even the longest night must end"\n\n-- the song\n')

    assert note.has_body is True
    assert notes_model.first_body_line(note) == '> "Even the longest night must end"'
    assert note.first_line == '> "Even the longest night must end"'


def test_a_hash_in_the_middle_of_a_line_is_not_a_heading(tmp_path):
    note = one_note(tmp_path, "asdasd# Untitled Note\n")

    assert note.has_body is True
    assert notes_model.first_body_line(note) == "asdasd# Untitled Note"


def test_a_heading_only_note_still_has_no_body(tmp_path):
    note = one_note(tmp_path, STUB)

    assert note.has_body is False
    assert notes_model.first_body_line(note) == ""
    assert note.first_line == "Untitled Note"


def test_a_nameless_note_has_no_title_and_falls_back_to_its_first_line(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="a line I came with\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert note.title == ""
    assert note.first_line == "a line I came with"
    assert note.has_body is True
    # The row is already labelled by that line; a preview would repeat it
    assert notes_model.first_body_line(note) == ""


def test_an_all_digit_stem_is_an_id_not_a_name():
    assert notes_model.display_name_from_filename("1700000000.md") == ""
    assert notes_model.display_name_from_filename("1700000000_Named.md") == "Named"


def test_an_empty_note_has_neither_title_nor_first_line(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="\n\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert (note.title, note.first_line, note.has_body) == ("", "", False)


# A nameless note is labelled by its own first line, so the preview has to begin after it.
# Getting this wrong printed the same sentence twice in every Overview row.


def test_a_nameless_notes_preview_is_the_line_after_its_label(tmp_path):
    write_note(
        tmp_path,
        "major_arcana.07",
        "1700000000.md",
        body="what can you see on the horizon?\nand what lies beyond it\n",
    )

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert note.first_line == "what can you see on the horizon?"
    assert notes_model.first_body_line(note) == "and what lies beyond it"


def test_a_one_line_nameless_note_has_no_preview_at_all(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="the whole note\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert (note.first_line, notes_model.first_body_line(note)) == ("the whole note", "")


def test_a_named_note_still_previews_its_opening_line(tmp_path):
    """The label came from the filename, so no line of the body is spoken for."""
    write_note(tmp_path, "major_arcana.07", "1700000000_Named.md", body="the opening line\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert note.title == "Named"
    assert notes_model.first_body_line(note) == "the opening line"


def test_a_nameless_note_whose_first_line_repeats_keeps_the_repeat(tmp_path):
    """Only the one line the label took is skipped, not every copy of it."""
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="echo\necho\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert notes_model.first_body_line(note) == "echo"


def test_a_heading_first_line_is_marked_as_one(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="# Lyrics\n\nthe body\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert note.first_line == "Lyrics"
    assert note.first_line_is_heading is True


def test_a_bare_first_line_is_not_marked_as_a_heading(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="just a sentence\n")

    note = notes_model.scan(tmp_path)["major_arcana.07"][0]

    assert note.first_line_is_heading is False


def test_a_hash_mid_line_does_not_make_a_heading(tmp_path):
    write_note(tmp_path, "major_arcana.07", "1700000000.md", body="asdasd# Untitled Note\n")

    assert notes_model.scan(tmp_path)["major_arcana.07"][0].first_line_is_heading is False
