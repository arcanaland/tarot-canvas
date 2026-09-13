from dataclasses import replace
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QLocale, QSize, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QPushButton

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_details import DeckDetails
from tarot_canvas.ui.library.deck_details_pane import DeckDetailsPane
from tarot_canvas.ui.library.deck_downloads import DeckState
from tarot_canvas.ui.library.deck_model import deck_cover_path
from tarot_canvas.ui.library.download_text import failure_text
from tarot_canvas.ui.widgets.cover_banner import BANNER_TEXT
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind
from tests.unit.test_library_model import catalog_entry

ENTRY = catalog_entry("aquatic-tarot")
DECK = SimpleNamespace(deck_path="/decks/aquatic-tarot")
FAILURE = DownloadFailure(FailureKind.NETWORK, "offline")

AVAILABLE = DeckDetails(
    name="Aquatic Tarot",
    artist="Andreas",
    cover_path=None,
    card_count=78,
    version="2.0",
    license="CC-BY-NC-SA-3.0",
    attribution="A credit line",
    description="Cards under the sea",
    size=12_534_167,
    state=DeckState.AVAILABLE,
    progress=None,
    failure=None,
    deck=None,
    entry=ENTRY,
)
INSTALLED = replace(AVAILABLE, size=None, state=DeckState.INSTALLED, deck=DECK, entry=None)
DOWNLOADING = replace(AVAILABLE, state=DeckState.DOWNLOADING, progress=0.1)
FAILED = replace(AVAILABLE, state=DeckState.FAILED, failure=FAILURE)


@pytest.fixture
def pane(qtbot):
    widget = DeckDetailsPane()
    qtbot.addWidget(widget)
    return widget


def buttons(pane):
    return pane._actions.findChildren(QPushButton)


@pytest.mark.parametrize(
    ("details", "label"),
    [(INSTALLED, "Open"), (AVAILABLE, "Download"), (DOWNLOADING, "Cancel"), (FAILED, "Try Again")],
)
def test_each_state_shows_exactly_its_action(pane, details, label):
    pane.show_details(details)
    assert [button.text() for button in buttons(pane)] == [label]
    assert (pane.progress_bar is not None) == (details.state is DeckState.DOWNLOADING)
    assert (pane.failure_label is not None) == (details.state is DeckState.FAILED)


@pytest.mark.parametrize(
    ("details", "signal", "argument"),
    [
        (INSTALLED, "open_requested", DECK),
        (AVAILABLE, "download_requested", ENTRY),
        (DOWNLOADING, "cancel_requested", ENTRY.slug),
        (FAILED, "download_requested", ENTRY),
    ],
)
def test_each_action_emits_its_signal(pane, details, signal, argument):
    emitted = []
    getattr(pane, signal).connect(emitted.append)
    pane.show_details(details)
    pane.action_button.click()
    assert emitted == [argument]


def test_it_shows_each_field(pane):
    pane.show_details(AVAILABLE)
    assert pane.heading_label.text() == "Aquatic Tarot"
    assert pane.artist_label.text() == "Andreas"
    assert pane.version_label.text() == "2.0"
    assert pane.size_label.text() == QLocale().formattedDataSize(AVAILABLE.size)
    assert pane.license_label.text() == "CC-BY-NC-SA-3.0"
    assert pane.card_count_label.text() == QLocale().toString(78)
    assert pane.description_label.text() == "Cards under the sea"
    assert pane.attribution_label.text() == "A credit line"


def test_index_text_is_never_read_as_markup(pane):
    pane.show_details(replace(FAILED, description="<b>bold</b>"))
    index_labels = [
        pane.heading_label,
        pane.artist_label,
        pane.version_label,
        pane.size_label,
        pane.license_label,
        pane.card_count_label,
        pane.description_label,
        pane.attribution_label,
        pane.failure_label,
    ]
    for label in index_labels:
        assert label.textFormat() == Qt.TextFormat.PlainText, label.text()
    assert pane.description_label.text() == "<b>bold</b>"


def test_a_missing_field_hides_its_row(pane):
    pane.show_details(replace(AVAILABLE, license=None, attribution=None, artist=None))
    assert not pane.form.isRowVisible(pane.license_label)
    assert pane.form.isRowVisible(pane.version_label)
    assert not pane.attribution_label.isVisibleTo(pane)
    assert not pane.artist_label.isVisibleTo(pane)


def test_an_installed_deck_has_no_size_row(pane):
    pane.show_details(INSTALLED)
    assert not pane.form.isRowVisible(pane.size_label)


def test_a_field_hidden_for_one_deck_returns_for_the_next(pane):
    pane.show_details(replace(AVAILABLE, license=None))
    pane.show_details(INSTALLED)
    assert pane.form.isRowVisible(pane.license_label)


def test_a_failure_shows_its_text(pane):
    pane.show_details(FAILED)
    assert pane.failure_label.text() == failure_text(FAILURE)


def test_progress_moves_the_bar_without_a_rebuild(pane):
    pane.show_details(DOWNLOADING)
    cancel = pane.action_button
    assert pane.progress_bar.value() == 10

    pane.show_details(replace(DOWNLOADING, progress=0.5))
    assert pane.action_button is cancel
    assert pane.progress_bar.value() == 50


def test_a_new_state_rebuilds_the_action(pane):
    pane.show_details(AVAILABLE)
    download = pane.action_button
    pane.show_details(DOWNLOADING)
    assert pane.action_button is not download


def test_the_action_keeps_focus_through_a_rebuild(pane, qtbot):
    # Only an active window's widgets report hasFocus
    with qtbot.waitActive(pane):
        pane.show()
        pane.activateWindow()
    pane.show_details(AVAILABLE)
    pane.focus_action()
    assert pane.action_button.hasFocus()

    pane.show_details(DOWNLOADING)
    assert pane.action_button.hasFocus()


def window_text(label):
    return label.palette().color(QPalette.ColorRole.WindowText)


def test_a_cover_puts_the_name_on_a_band_the_cover_hangs_below(pane, qtbot, minimal_deck):
    pane.resize(360, 900)
    pane.show_details(replace(AVAILABLE, cover_path=deck_cover_path(minimal_deck)))
    with qtbot.waitExposed(pane):
        pane.show()

    header = pane.header
    assert header.is_on_banner()
    assert window_text(pane.heading_label) == BANNER_TEXT
    band = header.banner_rect()
    assert band.width() == header.width()
    assert band.bottom() > pane.artist_label.geometry().bottom()
    assert band.bottom() < header.cover.geometry().bottom()
    assert not header.grab().isNull()


def test_the_cover_is_the_deck_views_small_size(pane):
    assert pane.header.cover.size() == QSize(*units.cover_size(units.DENSITY_SMALL))


def test_no_cover_means_no_band_and_palette_text(pane, minimal_deck):
    pane.show_details(replace(AVAILABLE, cover_path=deck_cover_path(minimal_deck)))
    pane.show_details(INSTALLED)  # another deck, with no cover

    assert not pane.header.is_on_banner()
    assert pane.header.banner_rect().isEmpty()
    assert window_text(pane.heading_label) == QPalette().color(QPalette.ColorRole.WindowText)
    assert not pane.header.cover.grab().isNull()


def test_a_cover_arriving_raises_the_band(pane, minimal_deck):
    pane.show_details(AVAILABLE)
    assert not pane.header.is_on_banner()

    pane.show_details(replace(AVAILABLE, cover_path=deck_cover_path(minimal_deck)))
    assert pane.header.is_on_banner()


def test_a_long_description_scrolls_and_the_action_stays(pane, qtbot):
    long = " ".join(["Cards under the sea, painted in water colour."] * 40)
    pane.resize(320, 400)
    pane.show_details(replace(AVAILABLE, description=long))
    with qtbot.waitExposed(pane):
        pane.show()
    assert pane.scroll_area.verticalScrollBar().maximum() > 0
    assert pane.action_button.isVisible()
    bottom = pane.action_button.mapTo(pane, pane.action_button.rect().bottomLeft()).y()
    assert bottom < pane.height()
