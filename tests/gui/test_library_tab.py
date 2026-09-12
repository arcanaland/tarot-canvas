from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QDialog, QFrame, QListView, QMessageBox

from tarot_canvas.models.catalog import INDEX_URL
from tarot_canvas.settings import (
    LIBRARY_DENSITY_KEY,
    LIBRARY_SORT_KEY,
    SHOW_AVAILABLE_DECKS_KEY,
    get_settings,
)
from tarot_canvas.ui.library import catalog_client, units
from tarot_canvas.ui.library.catalog_client import DeckCatalog, deck_catalog
from tarot_canvas.ui.library.deck_downloads import DeckState, deck_downloads
from tarot_canvas.ui.library.deck_model import (
    SORT_AUTHOR,
    CoverPathRole,
    DeckRole,
    EntryRole,
    ProgressRole,
    StateRole,
)
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.windows.deck_download_dialog import DOWNLOAD_TEXT
from tests.gui.test_catalog_client import FakeTransport
from tests.unit.test_catalog import index, raw_entry
from tests.unit.test_library_model import catalog_entry, fake_deck

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


def test_decks_changed_refreshes_an_open_library(qtbot, monkeypatch):
    from tarot_canvas.models.deck_events import deck_events

    decks = list(DECKS)
    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(decks)),
    )
    tab = LibraryTab()
    qtbot.addWidget(tab)
    assert tab.proxy_model.rowCount() == 2

    decks.append(fake_deck("Aquatic", author="Andreas", majors=22, minors=56))
    deck_events().decks_changed.emit()

    assert "Aquatic" in names(tab)


def test_decks_changed_after_a_library_is_deleted_does_not_crash(qtbot, monkeypatch):
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent

    from tarot_canvas.models.deck_events import deck_events

    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(DECKS)),
    )
    tab = LibraryTab()
    tab.show()
    tab.close()
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(tab)

    deck_events().decks_changed.emit()
    qtbot.wait(10)


def test_decks_changed_after_a_library_is_closed_does_not_crash(qtbot, monkeypatch):
    """A closed tab is removeTab'd, not deleted, so it lives on hidden and refreshes."""
    from tarot_canvas.models.deck_events import deck_events

    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(DECKS)),
    )
    tab = LibraryTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.close()

    deck_events().decks_changed.emit()
    assert tab.proxy_model.rowCount() == 2


# -- ghosts --------------------------------------------------------------

AQUATIC = catalog_entry("aquatic-tarot")
INDEX_BODY = index(raw_entry("aquatic-tarot"))


@pytest.fixture(autouse=True)
def switch_unset(qapp):
    """QSettings is shared across the process, so a test that turns the switch off leaks."""
    get_settings().remove(SHOW_AVAILABLE_DECKS_KEY)
    yield
    get_settings().remove(SHOW_AVAILABLE_DECKS_KEY)


@pytest.fixture
def installed(monkeypatch):
    decks = list(DECKS)
    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(decks)),
    )
    return decks


@pytest.fixture
def transport(monkeypatch, tmp_path):
    """The app-wide catalog, answering from a transport the test drives."""
    fake = FakeTransport()
    catalog = DeckCatalog(transport=fake, cache_dir=tmp_path / "catalog")
    monkeypatch.setattr(catalog_client, "_instance", catalog)
    return fake


@pytest.fixture
def ghost_library(qtbot, installed, transport):
    tab = LibraryTab()
    qtbot.addWidget(tab)
    transport.reply(INDEX_URL, body=INDEX_BODY, etag='"v1"')
    return tab


def ghost_of(tab):
    for row in range(tab.proxy_model.rowCount()):
        index = tab.proxy_model.index(row, 0)
        if index.data(EntryRole) is not None:
            return index
    return None


def delete(tab):
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent

    tab.close()
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(tab)


@pytest.fixture
def dialog_answers(monkeypatch):
    """What DeckDownloadDialog.exec returns, set per test; the dialogs it was shown."""
    answers = SimpleNamespace(result=QDialog.DialogCode.Accepted, shown=[])

    def fake_exec(dialog):
        answers.shown.append(dialog.entry)
        return answers.result

    monkeypatch.setattr("tarot_canvas.ui.tabs.library_tab.DeckDownloadDialog.exec", fake_exec)
    return answers


def test_a_catalog_deck_you_lack_trails_the_installed_decks(ghost_library):
    assert names(ghost_library)[-1] == "Aquatic Tarot"
    assert sorted(names(ghost_library)[:-1]) == ["Aurora", "Zodiac"]
    assert ghost_of(ghost_library).data(DeckRole) is None


def test_activating_a_ghost_downloads_it_once_the_dialog_is_accepted(
    ghost_library, dialog_answers, fake_downloads
):
    ghost_library.view.activated.emit(ghost_of(ghost_library))

    assert dialog_answers.shown == [AQUATIC]
    (job,) = fake_downloads
    assert job.dest.name == "aquatic-tarot"
    assert ghost_of(ghost_library).data(StateRole) is DeckState.DOWNLOADING


def test_a_rejected_dialog_starts_nothing(ghost_library, dialog_answers, fake_downloads):
    dialog_answers.result = QDialog.DialogCode.Rejected
    ghost_library.view.activated.emit(ghost_of(ghost_library))

    assert dialog_answers.shown == [AQUATIC]
    assert fake_downloads == []
    assert ghost_of(ghost_library).data(StateRole) is DeckState.AVAILABLE


@pytest.mark.parametrize(
    ("answer", "cancelled"),
    [(QMessageBox.StandardButton.Yes, True), (QMessageBox.StandardButton.No, False)],
)
def test_activating_a_downloading_ghost_asks_before_cancelling(
    ghost_library, dialog_answers, fake_downloads, monkeypatch, answer, cancelled
):
    deck_downloads().start(AQUATIC)
    asked = []
    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.QMessageBox.question",
        lambda parent, title, text, *args: asked.append(text) or answer,
    )

    ghost_library.view.activated.emit(ghost_of(ghost_library))

    assert asked == [DOWNLOAD_TEXT["cancel_question"].format(name=AQUATIC.name)]
    assert dialog_answers.shown == []
    assert fake_downloads[0].cancelled is cancelled
    expected = DeckState.AVAILABLE if cancelled else DeckState.DOWNLOADING
    assert ghost_of(ghost_library).data(StateRole) is expected


def test_activating_a_failed_ghost_offers_the_dialog_again(
    ghost_library, dialog_answers, fake_downloads
):
    from tarot_canvas.utils.package_download import DownloadFailure, FailureKind

    deck_downloads().start(AQUATIC)
    fake_downloads[0].failed.emit(DownloadFailure(FailureKind.NETWORK, "offline"))
    assert ghost_of(ghost_library).data(StateRole) is DeckState.FAILED

    ghost_library.view.activated.emit(ghost_of(ghost_library))
    assert dialog_answers.shown == [AQUATIC]
    assert len(fake_downloads) == 2


def test_the_switch_off_shows_no_ghosts_and_asks_nothing(qtbot, installed, transport):
    get_settings().setValue(SHOW_AVAILABLE_DECKS_KEY, False)
    tab = LibraryTab()
    qtbot.addWidget(tab)

    assert transport.requests == []
    assert ghost_of(tab) is None


def test_the_switch_changes_an_open_library(qtbot, installed, transport):
    get_settings().setValue(SHOW_AVAILABLE_DECKS_KEY, False)
    tab = LibraryTab()
    qtbot.addWidget(tab)

    deck_catalog().set_enabled(True)
    transport.reply(INDEX_URL, body=INDEX_BODY)
    assert ghost_of(tab) is not None

    deck_catalog().set_enabled(False)
    assert ghost_of(tab) is None


def test_an_installed_deck_replaces_its_ghost(ghost_library, installed):
    from tarot_canvas.models.deck_events import deck_events

    installed.append(fake_deck("Aquatic Tarot", identifier=AQUATIC.identifier))
    deck_events().decks_changed.emit()

    assert names(ghost_library).count("Aquatic Tarot") == 1
    assert ghost_of(ghost_library) is None


def test_reopening_a_library_asks_for_the_index_only_once(qtbot, installed, transport):
    first = LibraryTab()  # not qtbot's: it would close the deleted tab at teardown
    transport.reply(INDEX_URL, body=INDEX_BODY)
    delete(first)

    reopened = LibraryTab()
    qtbot.addWidget(reopened)

    assert len(transport.index_requests()) == 1
    assert ghost_of(reopened) is not None


def test_a_download_outlives_the_library_that_started_it(
    qtbot, installed, transport, dialog_answers, fake_downloads
):
    first = LibraryTab()  # not qtbot's: it would close the deleted tab at teardown
    transport.reply(INDEX_URL, body=INDEX_BODY)
    first.view.activated.emit(ghost_of(first))
    fake_downloads[0].progress.emit(40, 100)
    delete(first)

    reopened = LibraryTab()
    qtbot.addWidget(reopened)
    ghost = ghost_of(reopened)
    assert ghost.data(StateRole) is DeckState.DOWNLOADING
    assert ghost.data(ProgressRole) == pytest.approx(0.4)


def test_a_fetched_cover_repaints_the_ghost(ghost_library, transport):
    changed = []
    ghost_library.proxy_model.dataChanged.connect(lambda top, *_: changed.append(top.row()))
    assert ghost_of(ghost_library).data(CoverPathRole) is None

    transport.reply(AQUATIC.cover, body=b"jpeg bytes")

    assert changed == [ghost_of(ghost_library).row()]
    assert ghost_of(ghost_library).data(CoverPathRole) is not None


def test_every_app_wide_signal_is_safe_after_a_library_is_deleted(
    qtbot, installed, transport, fake_downloads
):
    from tarot_canvas.models.deck_events import deck_events

    tab = LibraryTab()
    tab.show()
    transport.reply(INDEX_URL, body=INDEX_BODY)
    delete(tab)

    deck_events().decks_changed.emit()
    deck_catalog().entries_changed.emit()
    deck_catalog().cover_ready.emit(AQUATIC.cover)
    deck_downloads().changed.emit(AQUATIC.slug)
    qtbot.wait(10)


def test_a_finished_download_raises_the_main_window_toast(qtbot, fake_downloads):
    from tarot_canvas.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    deck_downloads().start(AQUATIC)
    fake_downloads[0].succeeded.emit(str(fake_downloads[0].dest))

    assert window.toast.text() == DOWNLOAD_TEXT["installed_toast"].format(name=AQUATIC.name)
    assert window.toast.isVisibleTo(window)
