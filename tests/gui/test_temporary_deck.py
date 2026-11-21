"""A .tarotdeck opens outside the Library, and its banner adds it"""

import pytest

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.arcana_backend import load_deck
from tarot_canvas.models.deck_container import pack_container
from tarot_canvas.models.deck_install import install_dir_name, install_local
from tarot_canvas.ui import main_window as main_window_module
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import DECK_VIEW, DOWNLOAD
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab


@pytest.fixture
def places(tmp_path, monkeypatch):
    """(decks root, staging), as the window finds them"""
    root, staging = tmp_path / "tarot" / "decks", tmp_path / "tarot" / ".staging"
    root.mkdir(parents=True)
    monkeypatch.setattr(main_window_module, "get_decks_directory", lambda: [str(root)])
    monkeypatch.setattr(main_window_module, "get_staging_directory", lambda: staging)
    return root, staging


@pytest.fixture
def made(tmp_path):
    """The maker's deck, in a folder of its own"""
    return writer.create("Given", decks_root=tmp_path / "maker")


@pytest.fixture
def container(tmp_path, made):
    path = tmp_path / "given.tarotdeck"
    pack_container(made, path)
    return path


@pytest.fixture
def window(qtbot, places):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


@pytest.fixture
def boxes(monkeypatch):
    shown = []
    monkeypatch.setattr(main_window_module.QMessageBox, "exec", lambda box: shown.append(box))
    return shown


def deck_tabs(window):
    tabs = (window.tab_widget.widget(i) for i in range(window.tab_widget.count()))
    return [tab for tab in tabs if isinstance(tab, DeckViewTab)]


def opened(qtbot, window, container):
    window.open_deck_file_temporarily(container)
    qtbot.waitUntil(lambda: any(tab.origin is not None for tab in deck_tabs(window)))
    return next(tab for tab in deck_tabs(window) if tab.origin is not None)


def test_a_file_opens_outside_the_library_with_an_unclosable_banner(
    qtbot, window, places, container
):
    root, staging = places

    tab = opened(qtbot, window, container)

    assert window.tab_widget.currentWidget() is tab
    assert tab.banner.isVisibleTo(tab)
    assert not tab.banner.close_button.isVisibleTo(tab)
    assert tab.banner.label.text() == DECK_VIEW["temporary"].format(file="given.tarotdeck")
    assert tab.banner_action.text() == DECK_VIEW["add_to_library"]
    assert list(root.iterdir()) == []
    assert [path.parent for path in window.temporary_decks] == [staging]
    assert tab.deck_path == str(window.temporary_decks[0])
    # A temporary deck is nobody's handmade deck
    assert tab.editor is None


def test_add_to_library_installs_and_takes_the_temporary_tabs_place(
    qtbot, window, places, container, made, monkeypatch
):
    root, _staging = places
    name = install_dir_name(load_deck(str(made)).metadata.identifier, None)
    toasts = []
    monkeypatch.setattr(window.toast, "show_message", toasts.append)
    tab = opened(qtbot, window, container)
    index = window.tab_widget.indexOf(tab)

    tab.banner_action.trigger()
    qtbot.waitUntil(lambda: tab not in deck_tabs(window))

    installed = window.tab_widget.widget(index)
    assert isinstance(installed, DeckViewTab)
    assert installed.origin is None and installed.banner is None
    assert [path.name for path in root.iterdir()] == [name]
    assert installed.deck_path == str(root / name)
    assert toasts == [DOWNLOAD["installed_toast"].format(name=installed.tab_title())]


def test_a_deck_already_in_the_library_offers_its_copy(
    qtbot, window, container, made, stub_deck_library, minimal_deck
):
    library_copy = load_deck(str(made))
    stub_deck_library.decks = lambda: [minimal_deck, library_copy]

    tab = opened(qtbot, window, container)
    assert tab.banner_action.text() == DECK_VIEW["open_library_copy"]
    assert tab.banner.label.text() == DECK_VIEW["temporary_installed"].format(
        file="given.tarotdeck"
    )

    tab.banner_action.trigger()

    current = window.tab_widget.currentWidget()
    assert current is not tab and current.deck_path == str(made)
    assert tab in deck_tabs(window)


def test_a_failed_install_offers_it_again(qtbot, window, places, container, boxes):
    root, staging = places
    install_local(container, root, staging)
    tab = opened(qtbot, window, container)

    tab.banner_action.trigger()
    assert not tab.banner_action.isEnabled()
    qtbot.waitUntil(lambda: bool(boxes))

    assert tab.banner_action.isEnabled()
    assert tab in deck_tabs(window)


def test_opening_the_same_file_again_goes_to_its_tab(qtbot, window, container):
    tab = opened(qtbot, window, container)
    window.tab_widget.setCurrentIndex(0)

    window.open_deck_file_temporarily(container)

    assert window.tab_widget.currentWidget() is tab
    assert len(window.temporary_decks) == 1


def test_a_bad_file_opens_nothing_and_says_so(qtbot, window, places, tmp_path, boxes):
    _root, staging = places
    bad = tmp_path / "bad.tarotdeck"
    bad.write_bytes(b"not a zip")

    window.open_deck_file_temporarily(bad)
    qtbot.waitUntil(lambda: bool(boxes))

    assert deck_tabs(window) == []
    assert window.temporary_decks == []
    assert list(staging.iterdir()) == []


def test_the_temporary_copy_outlives_its_tab_and_goes_at_quit(qtbot, window, places, container):
    _root, staging = places
    tab = opened(qtbot, window, container)
    copy = window.temporary_decks[0]
    someone_elses = staging / "other.open.abcd"
    someone_elses.mkdir()

    window.close_tab(window.tab_widget.indexOf(tab))
    assert copy.is_dir()

    window.close()

    assert not copy.exists()
    assert someone_elses.is_dir()
