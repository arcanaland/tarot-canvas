import os

from PyQt6.QtCore import Qt

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui import notes_text
from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_model import PreviewRole
from tarot_canvas.ui.tabs.card_view.notes_section import MAX_ROWS
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tests.conftest import MINIMAL_DECK_PATH


def write_note(notes_base, card_id, filename, body):
    card_dir = notes_base / card_id
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def open_card_view(qtbot, register=True):
    deck = TarotDeck(str(MINIMAL_DECK_PATH))
    card = next(c for c in deck.get_all_cards() if c.get("image"))
    tab = CardViewTab(card=card, deck=deck)
    if register:
        qtbot.addWidget(tab)
    return tab, card


def section(tab):
    return tab.overview_tab.notes_section


def rows(tab):
    """The rows the section shows, as model indexes; none while the ghost stands in."""
    view = section(tab).list_view
    if not view.isVisibleTo(section(tab)):
        return []
    model = view.model()
    return [model.index(row, 0) for row in range(model.rowCount())]


def title(row):
    return row.data(Qt.ItemDataRole.DisplayRole)


def preview(row):
    return row.data(PreviewRole)


def shows_the_ghost(tab):
    return section(tab).ghost.isVisibleTo(section(tab)) and rows(tab) == []


def test_a_card_with_nothing_written_shows_one_ghost_row(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)

    assert shows_the_ghost(tab)


def test_the_ghost_is_how_the_first_note_gets_written(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)

    section(tab).ghost.clicked.emit()

    assert tab.info_tabs.currentWidget() is tab.notes_tab
    assert tab.notes_tab.pending_path is not None


def test_one_note_is_listed_with_its_opening_line(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000_Lyrics.md", "# Lyrics\n\nthe longest night\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    drawn = rows(tab)

    assert len(drawn) == 1
    assert not section(tab).ghost.isVisibleTo(section(tab))
    assert title(drawn[0]) == "Lyrics"
    assert preview(drawn[0]) == "the longest night"


def test_a_stub_is_listed_but_shows_no_preview_line(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000_Stub.md", "# Stub\n\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert title(row) == "Stub"
    assert preview(row) == notes_text.text("stub_note")


def test_five_notes_are_capped_at_three_newest_first(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    for index in range(5):
        path = write_note(
            notes_base, card["id"], f"17000000{index:02d}_N{index}.md", f"# N{index}\n"
        )

        os.utime(path, (1700000000 + index, 1700000000 + index))
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    drawn = rows(tab)
    view = section(tab).list_view

    assert len(drawn) == MAX_ROWS
    assert [title(row) for row in drawn] == ["N4", "N3", "N2"]
    # Every row shows, and none scrolls
    assert view.height() == MAX_ROWS * view.sizeHintForRow(0)


def test_a_nameless_note_is_listed_by_its_first_line(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000.md", "a line I came with\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    assert title(rows(tab)[0]) == "a line I came with"


def test_a_nameless_note_never_shows_the_same_line_twice(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(
        notes_base,
        card["id"],
        "1700000000.md",
        "foo?\nand bar\n",
    )
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert title(row) == "foo?"
    assert preview(row) == "and bar"


def test_a_one_line_nameless_note_is_a_one_line_row(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000.md", "the whole note\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert title(row) == "the whole note"
    assert preview(row) == ""


def test_the_rows_are_the_shared_note_row_and_point_no_hand(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000_Lyrics.md", "# Lyrics\n\nbody\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()
    view = section(tab).list_view

    assert isinstance(view.itemDelegate(), NoteRowDelegate)
    assert view.viewport().cursor().shape() != Qt.CursorShape.PointingHandCursor
    assert section(tab).ghost.cursor().shape() != Qt.CursorShape.PointingHandCursor


def test_a_heading_the_user_wrote_titles_a_nameless_note(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(
        notes_base,
        card["id"],
        "1700000000.md",
        '# Lyrics\n\n"foobar"\n',
    )
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert title(row) == "Lyrics"
    assert preview(row) == '"foobar"'


def test_clicking_a_row_raises_the_notes_tab_with_that_note_open(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    path = write_note(notes_base, card["id"], "1700000000_Lyrics.md", "# Lyrics\n\nbody\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    section(tab).list_view.activated.emit(rows(tab)[0])

    assert tab.info_tabs.currentWidget() is tab.notes_tab
    assert tab.notes_tab.current_file_path == str(path)
    assert tab.notes_tab.stack.currentIndex() == 2


def test_writing_a_note_replaces_the_ghost_without_reloading_the_card(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)
    assert shows_the_ghost(tab)

    tab.notes_tab.create_new_note()
    qtbot.keyClicks(tab.notes_tab.note_editor, "a line I came with")

    # The ghost is gone the moment the note has a file
    assert not shows_the_ghost(tab)

    tab.notes_tab.save_current_note()
    assert title(rows(tab)[0]) == "a line I came with"


def test_the_section_stops_listening_when_its_card_view_is_gone(qtbot, notes_base):
    tab, _ = open_card_view(qtbot, register=False)

    tab.deleteLater()
    qtbot.wait(10)

    # A slot left on the singleton would raise on the next write from anywhere
    note_events().notes_changed.emit()


def test_the_section_is_headed_by_the_name_adam_gave_it(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)

    heading = tab.overview_tab.notes_section.heading

    assert heading.text() == "Personal Notes"
    assert heading.isVisibleTo(tab.overview_tab)
