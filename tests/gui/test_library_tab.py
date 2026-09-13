from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QItemSelectionModel, QPoint, Qt
from PyQt6.QtWidgets import QFrame, QListView

from tarot_canvas.models.catalog import INDEX_URL
from tarot_canvas.settings import (
    LIBRARY_DENSITY_KEY,
    LIBRARY_DETAILS_PANE_KEY,
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
from tarot_canvas.ui.library.download_text import DOWNLOAD_TEXT
from tarot_canvas.ui.tabs.library_tab import LibraryTab
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
def switches_unset(qapp):
    """QSettings is shared across the process, so a test that turns a switch off leaks."""
    for key in (SHOW_AVAILABLE_DECKS_KEY, LIBRARY_DETAILS_PANE_KEY):
        get_settings().remove(key)
    yield
    for key in (SHOW_AVAILABLE_DECKS_KEY, LIBRARY_DETAILS_PANE_KEY):
        get_settings().remove(key)


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


def shown(tab):
    return tab.details_pane.details()


def select(tab, row):
    """Make a row current the way code does, not the way a user does"""
    tab.view.selectionModel().setCurrentIndex(
        tab.proxy_model.index(row, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def click(tab, qtbot, row):
    rect = tab.view.visualRect(tab.proxy_model.index(row, 0))
    qtbot.mouseClick(tab.view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


@pytest.fixture
def shown_library(library, qtbot):
    library.resize(1200, 800)
    # Active, so the grid's hasFocus is true when the keyboard path asks it
    with qtbot.waitActive(library):
        library.show()
        library.activateWindow()
    return library


# -- the details pane ----------------------------------------------------


def test_the_pane_starts_hidden_with_its_toggle_disabled(library):
    assert not library.details_pane_is_open()
    assert not library.details_toggle.isEnabled()


def test_a_click_opens_the_pane_on_the_clicked_deck(shown_library, qtbot):
    click(shown_library, qtbot, 1)
    assert shown_library.details_pane_is_open()
    assert shown(shown_library).deck is shown_library.current_deck()
    assert shown_library.details_toggle.isChecked()


def test_a_keyboard_move_opens_the_pane(shown_library, qtbot):
    shown_library.view.setFocus()
    shown_library.select_deck_path(DECKS[1].deck_path)
    assert not shown_library.details_pane_is_open()

    qtbot.keyClick(shown_library.view, Qt.Key.Key_Left)
    assert shown_library.details_pane_is_open()


def test_focusing_the_grid_does_not_open_the_pane(shown_library, qtbot):
    """The view makes its first deck current on focus in, which selects nothing"""
    shown_library.search_field.setFocus()
    qtbot.keyClick(shown_library.search_field, Qt.Key.Key_Tab)
    shown_library.view.setFocus(Qt.FocusReason.TabFocusReason)
    assert not shown_library.details_pane_is_open()


def test_selection_by_code_never_opens_the_pane(library):
    library.select_deck_path(DECKS[1].deck_path)
    library.refresh()
    assert not library.details_pane_is_open()
    # but it does fill it, and enables the toggle
    assert shown(library).deck is DECKS[1]
    assert library.details_toggle.isEnabled()


def test_the_pane_follows_the_selection_once_open(shown_library, qtbot):
    click(shown_library, qtbot, 0)
    select(shown_library, 1)
    assert shown(shown_library).deck is shown_library.current_deck()


def test_a_close_is_remembered_and_selection_stops_opening_the_pane(
    shown_library, qtbot, monkeypatch
):
    click(shown_library, qtbot, 0)
    shown_library.details_toggle.click()

    assert not shown_library.details_pane_is_open()
    assert get_settings().value(LIBRARY_DETAILS_PANE_KEY, type=bool) is False
    click(shown_library, qtbot, 1)
    assert not shown_library.details_pane_is_open()

    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.library_tab.deck_manager",
        SimpleNamespace(get_all_decks=lambda: list(DECKS)),
    )
    reopened = LibraryTab()
    qtbot.addWidget(reopened)
    with qtbot.waitExposed(reopened):
        reopened.show()
    click(reopened, qtbot, 0)
    assert not reopened.details_pane_is_open()


def test_opening_through_the_toggle_is_remembered(shown_library, qtbot):
    get_settings().setValue(LIBRARY_DETAILS_PANE_KEY, False)
    select(shown_library, 0)
    shown_library.details_toggle.click()
    assert shown_library.details_pane_is_open()
    assert get_settings().value(LIBRARY_DETAILS_PANE_KEY, type=bool) is True


def test_ctrl_i_toggles_the_pane(shown_library, qtbot):
    select(shown_library, 0)
    shown_library.view.setFocus()

    qtbot.keyClick(shown_library.view, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert shown_library.details_pane_is_open()
    qtbot.keyClick(shown_library.view, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert not shown_library.details_pane_is_open()


def test_ctrl_i_does_nothing_with_nothing_to_show(shown_library, qtbot):
    shown_library.search_field.setFocus()
    qtbot.keyClick(shown_library.search_field, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert not shown_library.details_pane_is_open()


def click_nowhere(tab, qtbot):
    viewport = tab.view.viewport()
    spot = QPoint(viewport.width() - 5, viewport.height() - 5)
    assert not tab.view.indexAt(spot).isValid()
    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=spot)


def test_a_click_on_no_deck_deselects_and_the_pane_keeps_the_deck(shown_library, qtbot):
    click(shown_library, qtbot, 0)
    deck = shown_library.current_deck()

    click_nowhere(shown_library, qtbot)

    assert shown_library.view.selectionModel().selectedIndexes() == []
    assert shown_library.current_deck() is None
    assert shown_library.details_pane_is_open()
    assert shown(shown_library).deck is deck
    assert shown_library.details_toggle.isEnabled()


def test_esc_deselects(shown_library, qtbot):
    click(shown_library, qtbot, 0)
    qtbot.keyClick(shown_library.view, Qt.Key.Key_Escape)

    assert shown_library.current_deck() is None
    assert shown_library.details_pane_is_open()


def test_a_deselected_library_stays_deselected_through_a_refresh(shown_library, qtbot):
    click(shown_library, qtbot, 0)
    click_nowhere(shown_library, qtbot)
    shown_library.refresh()
    assert shown_library.current_deck() is None


def test_the_pane_opens_at_a_share_of_the_width_and_keeps_a_resized_width(shown_library):
    select(shown_library, 0)
    shown_library.details_toggle.click()
    grid, pane = shown_library.splitter.sizes()
    assert pane == pytest.approx((grid + pane) * LibraryTab.DETAILS_PANE_SHARE, abs=2)

    shown_library.splitter.setSizes([grid + pane - 400, 400])
    shown_library.details_toggle.click()
    shown_library.details_toggle.click()
    assert shown_library.splitter.sizes()[1] == 400


def test_the_pane_keeps_its_minimum_width(shown_library):
    select(shown_library, 0)
    shown_library.details_toggle.click()
    total = sum(shown_library.splitter.sizes())
    shown_library.splitter.setSizes([total, 0])
    assert shown_library.splitter.sizes()[1] >= LibraryTab.DETAILS_PANE_MIN_WIDTH
    assert not shown_library.splitter.isCollapsible(0)


def test_a_deck_the_search_hides_stays_shown(library):
    select(library, 0)
    deck = library.current_deck()
    library.search_field.setText("nothing matches this")
    assert shown(library).deck is deck
    assert library.details_toggle.isEnabled()


# -- ghosts in the pane --------------------------------------------------


def test_a_catalog_deck_you_lack_trails_the_installed_decks(ghost_library):
    assert names(ghost_library)[-1] == "Aquatic Tarot"
    assert sorted(names(ghost_library)[:-1]) == ["Aurora", "Zodiac"]
    assert ghost_of(ghost_library).data(DeckRole) is None


def test_activating_a_ghost_shows_it_with_download_focused_and_starts_nothing(
    ghost_library, fake_downloads, qtbot
):
    # Only an active window's widgets report hasFocus
    with qtbot.waitActive(ghost_library):
        ghost_library.show()
        ghost_library.activateWindow()
    ghost_library.view.activated.emit(ghost_of(ghost_library))

    assert ghost_library.details_pane_is_open()
    assert shown(ghost_library).entry == AQUATIC
    assert ghost_library.details_pane.action_button.text() == "Download"
    assert ghost_library.details_pane.action_button.hasFocus()
    assert fake_downloads == []


def test_activating_a_ghost_opens_the_pane_the_user_closed(ghost_library, fake_downloads):
    select(ghost_library, 0)
    ghost_library.toggle_details_pane()  # open
    ghost_library.toggle_details_pane()  # and closed, remembered
    assert not ghost_library.details_pane_is_open()

    ghost_library.view.activated.emit(ghost_of(ghost_library))
    assert ghost_library.details_pane_is_open()
    assert fake_downloads == []


def test_download_starts_the_shown_deck(ghost_library, fake_downloads):
    ghost_library.view.activated.emit(ghost_of(ghost_library))
    ghost_library.details_pane.action_button.click()

    (job,) = fake_downloads
    assert job.dest.name == "aquatic-tarot"
    assert ghost_of(ghost_library).data(StateRole) is DeckState.DOWNLOADING
    assert ghost_library.details_pane.action_button.text() == "Cancel"


def test_cancel_asks_nothing(ghost_library, fake_downloads, monkeypatch):
    def no_questions(*args, **kwargs):
        raise AssertionError("cancelling asked a question")

    for name in ("question", "warning", "information", "critical", "exec"):
        monkeypatch.setattr(f"PyQt6.QtWidgets.QMessageBox.{name}", no_questions)
    ghost_library.view.activated.emit(ghost_of(ghost_library))
    ghost_library.details_pane.action_button.click()

    ghost_library.details_pane.action_button.click()

    assert fake_downloads[0].cancelled
    assert ghost_of(ghost_library).data(StateRole) is DeckState.AVAILABLE
    assert ghost_library.details_pane.action_button.text() == "Download"


def test_try_again_restarts_a_failed_download(ghost_library, fake_downloads):
    from tarot_canvas.utils.package_download import DownloadFailure, FailureKind

    ghost_library.view.activated.emit(ghost_of(ghost_library))
    ghost_library.details_pane.action_button.click()
    fake_downloads[0].failed.emit(DownloadFailure(FailureKind.NETWORK, "offline"))

    pane = ghost_library.details_pane
    assert pane.action_button.text() == "Try Again"
    assert pane.failure_label.text() == DOWNLOAD_TEXT["failed: network"]

    pane.action_button.click()
    assert len(fake_downloads) == 2
    assert ghost_of(ghost_library).data(StateRole) is DeckState.DOWNLOADING


def test_open_opens_the_deck_tab(library, monkeypatch):
    opened = []
    monkeypatch.setattr(
        library,
        "window",
        lambda: SimpleNamespace(new_deck_view_tab=lambda deck_path: opened.append(deck_path)),
    )
    select(library, 0)

    assert library.details_pane.action_button.text() == "Open"
    library.details_pane.action_button.click()
    assert opened == [library.current_deck().deck_path]


def test_progress_moves_the_pane_bar(ghost_library, fake_downloads):
    ghost_library.view.activated.emit(ghost_of(ghost_library))
    ghost_library.details_pane.action_button.click()
    cancel = ghost_library.details_pane.action_button

    fake_downloads[0].progress.emit(40, 100)

    assert ghost_library.details_pane.progress_bar.value() == 40
    assert ghost_library.details_pane.action_button is cancel


def test_a_shown_ghost_that_installs_becomes_its_deck(ghost_library, installed, fake_downloads):
    from tarot_canvas.models.deck_events import deck_events

    select(ghost_library, ghost_of(ghost_library).row())
    ghost_library.details_pane.action_button.click()

    installed.append(fake_deck("Aquatic Tarot", identifier=AQUATIC.identifier))
    fake_downloads[0].succeeded.emit(str(fake_downloads[0].dest))
    deck_events().decks_changed.emit()  # the stub deck_manager's rescan emits nothing

    assert ghost_of(ghost_library) is None
    assert ghost_library.current_deck() is installed[-1]
    assert shown(ghost_library).deck is installed[-1]
    assert ghost_library.details_pane.action_button.text() == "Open"


def test_a_ghost_the_search_hides_stays_shown_and_downloadable(ghost_library, fake_downloads):
    ghost_library.view.activated.emit(ghost_of(ghost_library))
    ghost_library.search_field.setText("Zodiac")
    assert ghost_of(ghost_library) is None

    assert shown(ghost_library).entry == AQUATIC
    ghost_library.details_pane.action_button.click()
    assert len(fake_downloads) == 1
    # The source model's row still reaches the pane
    fake_downloads[0].progress.emit(40, 100)
    assert ghost_library.details_pane.progress_bar.value() == 40


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
    qtbot, installed, transport, fake_downloads
):
    first = LibraryTab()  # not qtbot's: it would close the deleted tab at teardown
    transport.reply(INDEX_URL, body=INDEX_BODY)
    first.view.activated.emit(ghost_of(first))
    first.details_pane.action_button.click()
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
    tab.view.activated.emit(ghost_of(tab))  # a ghost in the pane, to be updated
    tab.details_pane.action_button.click()
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
