from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QFrame, QListView

from tarot_canvas.settings import LIBRARY_DENSITY_KEY, LIBRARY_SORT_KEY, get_settings
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_model import SORT_AUTHOR, DeckRole
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tests.unit.test_library_model import fake_deck

DECKS = [
    fake_deck("Zodiac", author="Alice", majors=22, minors=56),
    fake_deck("Aurora", author="Zeno", majors=22, minors=0),
]


@pytest.fixture
def library(qtbot, monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(DECKS)),
    )
    tab = LibraryTab()
    qtbot.addWidget(tab)
    return tab


def names(tab):
    return [tab.proxy_model.index(row, 0).data() for row in range(tab.proxy_model.rowCount())]


def test_the_view_draws_no_frame_of_its_own(library):
    assert library.view.frameShape() == QFrame.Shape.NoFrame
    assert library.view.viewMode() == QListView.ViewMode.IconMode


def test_no_stylesheet_hardcodes_colours(library):
    assert library.styleSheet() == ""
    assert library.view.styleSheet() == ""


def test_the_grid_is_not_capped_at_four_columns(library):
    assert library.view.resizeMode() == QListView.ResizeMode.Adjust
    assert library.view.isWrapping()


def test_search_filters_the_view(library, qtbot):
    library.search_field.setText("aur")
    assert names(library) == ["Aurora"]

    library.search_field.setText("alice")
    assert names(library) == ["Zodiac"]

    library.search_field.clear()
    assert sorted(names(library)) == ["Aurora", "Zodiac"]


def test_empty_search_result_shows_a_message_instead_of_a_blank_grid(library):
    library.search_field.setText("nothing matches this")
    assert library.empty_label.isVisibleTo(library)
    assert not library.view.isVisibleTo(library)

    library.search_field.clear()
    assert not library.empty_label.isVisibleTo(library)


def test_selection_emits_deck_selected(library, qtbot):
    index = library.proxy_model.index(0, 0)
    with qtbot.waitSignal(library.deck_selected, timeout=1000) as blocker:
        library.view.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
    assert blocker.args[0] is index.data(DeckRole)


def test_activation_opens_the_deck_in_a_tab(library, monkeypatch):
    opened = []
    monkeypatch.setattr(
        library,
        "window",
        lambda: SimpleNamespace(new_deck_view_tab=lambda deck_path: opened.append(deck_path)),
    )

    index = library.proxy_model.index(0, 0)
    library.view.activated.emit(index)
    assert opened == [index.data(DeckRole).deck_path]


def test_activation_records_recency(library, monkeypatch):
    from tarot_canvas.settings import get_recent_decks

    monkeypatch.setattr(library, "window", lambda: SimpleNamespace())
    index = library.proxy_model.index(0, 0)
    library.view.activated.emit(index)

    assert index.data(DeckRole).deck_path in get_recent_decks()


def test_sort_and_density_persist(library, qtbot):
    library.sort_combo.setCurrentIndex(library.sort_combo.findData(SORT_AUTHOR))
    library.density_combo.setCurrentIndex(library.density_combo.findData(units.DENSITY_LARGE))

    settings = get_settings()
    assert settings.value(LIBRARY_SORT_KEY, type=str) == SORT_AUTHOR
    assert settings.value(LIBRARY_DENSITY_KEY, type=str) == units.DENSITY_LARGE
    assert library.delegate.density == units.DENSITY_LARGE
    assert names(library) == ["Zodiac", "Aurora"]


def test_saved_density_is_restored_on_a_new_tab(library, qtbot, monkeypatch):
    library.density_combo.setCurrentIndex(library.density_combo.findData(units.DENSITY_SMALL))

    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(DECKS)),
    )
    reopened = LibraryTab()
    qtbot.addWidget(reopened)
    assert reopened.delegate.density == units.DENSITY_SMALL


def test_refresh_keeps_the_selected_deck_selected(library):
    index = library.proxy_model.index(0, 0)
    library.view.selectionModel().setCurrentIndex(
        index, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )
    selected = library.current_deck()

    library.refresh()
    assert library.current_deck() is selected


def test_keyboard_navigation_reaches_the_grid(library, qtbot):
    library.show()
    qtbot.waitExposed(library)
    library.view.setFocus()
    library.view.setCurrentIndex(library.proxy_model.index(0, 0))
    qtbot.keyClick(library.view, Qt.Key.Key_Right)
    assert library.view.currentIndex().row() == 1
