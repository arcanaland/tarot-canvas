import os

import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt

from tarot_canvas.models.note_events import note_events
from tarot_canvas.settings import (
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_KEY,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEWS,
    get_settings,
)
from tarot_canvas.ui.library.notes_model import CardIdRole
from tarot_canvas.ui.tabs.library_tab import LibraryTab

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"


def write_note(base, card_id, title="A Note", body="a line of prose\n"):
    card_dir = base / card_id
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / f"1700000000_{title.replace(' ', '_')}.md"
    path.write_text(f"# {title}\n\n{body}", encoding="utf-8")
    return path


@pytest.fixture
def library(qtbot, notes_base):
    tab = LibraryTab()
    qtbot.addWidget(tab)
    return tab


def notes_view(tab):
    tab.show_view(LIBRARY_VIEW_NOTES)
    return tab.notes_page


def select(page, card_id):
    view = page.list_view
    model = view.model()
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(CardIdRole) == card_id:
            view.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            return index
    raise AssertionError(f"no row for {card_id}")


# -- the sidebar ---------------------------------------------------------


def test_the_sidebar_lists_the_views_in_order(library):
    views = [
        library.sidebar.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(library.sidebar.count())
    ]
    assert views == list(LIBRARY_VIEWS)
    assert library.current_view() == LIBRARY_VIEW_DECKS
    assert library.sidebar.currentRow() == 0


def test_selecting_a_row_switches_the_page_and_the_pane(library):
    library.sidebar.setCurrentRow(LIBRARY_VIEWS.index(LIBRARY_VIEW_NOTES))

    assert library.current_view() == LIBRARY_VIEW_NOTES
    assert library.pages.currentWidget() is library.notes_page
    assert library.current_details_pane() is library.notes_page.details_pane


def test_the_sidebar_never_leaves_no_view_selected(library):
    library.show_view(LIBRARY_VIEW_NOTES)

    library.sidebar.clearSelection()

    assert [item.data(Qt.ItemDataRole.UserRole) for item in library.sidebar.selectedItems()] == [
        LIBRARY_VIEW_NOTES
    ]
    assert library.current_view() == LIBRARY_VIEW_NOTES


def test_the_first_sidebar_row_is_level_with_the_search_field(library, qtbot):
    library.show()
    qtbot.waitExposed(library)

    viewport = library.sidebar.viewport()
    row = library.sidebar.visualItemRect(library.sidebar.item(0))
    row_centre = viewport.mapTo(library, row.center()).y()
    field = library.search_field
    field_centre = field.mapTo(library, field.rect().center()).y()

    assert abs(row_centre - field_centre) <= 1


def test_the_chosen_view_is_remembered(library, qtbot, notes_base):
    notes_view(library)
    assert get_settings().value(LIBRARY_VIEW_KEY, type=str) == LIBRARY_VIEW_NOTES

    reopened = LibraryTab()
    qtbot.addWidget(reopened)
    assert reopened.current_view() == LIBRARY_VIEW_NOTES


def test_sort_size_and_open_deck_are_the_deck_views_alone(library, qtbot):
    library.show()
    qtbot.waitExposed(library)
    assert library.sort_combo.isVisible()
    assert library.open_deck_button.isVisible()

    assert library.density_combo.isVisible()

    notes_view(library)

    assert not library.sort_combo.isVisible()
    assert not library.open_deck_button.isVisible()
    # The list has no covers to size; search serves both
    assert not library.density_combo.isVisible()
    assert library.search_field.isVisible()


def test_switching_views_clears_a_search_meant_for_the_other(library, notes_base):
    library.search_field.setText("zodiac")
    notes_view(library)

    assert library.search_field.text() == ""
    assert library.notes_page.list_model.search() == ""


# -- the list ------------------------------------------------------------


def test_search_in_this_view_leaves_the_deck_grid_alone(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings")
    write_note(notes_base, MAGICIAN, title="Tools")
    page = notes_view(library)
    page.refresh()

    library.search_field.setText("beginn")

    assert [
        page.list_model.index(row, 0).data(CardIdRole) for row in range(page.list_model.rowCount())
    ] == [FOOL]
    assert library.proxy_model.filterRegularExpression().pattern() == ""


def test_select_card_selects_its_newest_note(library, notes_base):
    old = write_note(notes_base, FOOL, title="Old")
    new = write_note(notes_base, FOOL, title="New")
    os.utime(old, (1_700_000_000, 1_700_000_000))
    os.utime(new, (1_800_000_000, 1_800_000_000))
    page = notes_view(library)
    page.refresh()

    assert page.select_card(FOOL)
    assert page.list_view.currentIndex().data(Qt.ItemDataRole.DisplayRole) == "New"


def test_a_row_is_activated_by_its_card_id(library, notes_base, qtbot):
    write_note(notes_base, FOOL)
    page = notes_view(library)
    page.refresh()
    index = select(page, FOOL)

    with qtbot.waitSignal(page.card_activated) as caught:
        page.list_view.activated.emit(index)

    assert caught.args == [FOOL]


# -- the pane ------------------------------------------------------------


def test_selecting_a_card_fills_the_pane_and_enables_the_toggle(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings")
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)
    details = page.details_pane.details()

    assert details.card_id == FOOL
    assert details.name == "The Fool"
    assert details.cover_path
    assert [note.title for note in details.notes] == ["Beginnings"]
    assert library.details_toggle.isEnabled()


def test_the_pane_shows_the_first_line_of_each_note(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings", body="a leap into thin air\n")
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)
    rows = page.details_pane.note_widgets()

    assert len(rows) == 1
    assert rows[0].preview_label.full_text == "a leap into thin air"


# -- staying current -----------------------------------------------------


def test_a_write_keeps_the_selection_and_refreshes_the_pane(library, notes_base):
    write_note(notes_base, FOOL, title="Draft")
    page = notes_view(library)
    page.refresh()
    select(page, FOOL)

    write_note(notes_base, FOOL, title="Beginnings")
    note_events().notes_changed.emit()

    assert page.details_pane.details().card_id == FOOL
    assert sorted(note.title for note in page.details_pane.details().notes) == [
        "Beginnings",
        "Draft",
    ]
    assert page.list_view.currentIndex().data(CardIdRole) == FOOL
