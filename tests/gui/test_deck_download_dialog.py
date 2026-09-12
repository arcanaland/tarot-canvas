import pytest
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtWidgets import QDialog

from tarot_canvas.ui.windows.deck_download_dialog import (
    DOWNLOAD_TEXT,
    DeckDownloadDialog,
    failure_text,
)
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind
from tests.unit.test_library_model import catalog_entry

ENTRY = catalog_entry(
    "aquatic-tarot",
    license="CC-BY-NC-SA-4.0",
    attribution="Art by a person",
    description="Cards under the sea",
)


def make(qtbot, entry=ENTRY):
    dialog = DeckDownloadDialog(entry)
    qtbot.addWidget(dialog)
    return dialog


def test_it_shows_each_field(qtbot):
    dialog = make(qtbot)
    assert dialog.heading_label.text() == ENTRY.name
    assert dialog.artist_label.text() == ENTRY.artist
    assert dialog.size_label.text() == QLocale().formattedDataSize(ENTRY.package_size)
    assert dialog.license_label.text() == "CC-BY-NC-SA-4.0"
    assert dialog.attribution_label.text() == "Art by a person"
    assert dialog.attribution_label.isVisibleTo(dialog)
    assert dialog.description_label.text() == "Cards under the sea"


def test_attribution_is_hidden_when_the_index_has_none(qtbot):
    dialog = make(qtbot, catalog_entry("aquatic-tarot", attribution=None))
    assert not dialog.attribution_label.isVisibleTo(dialog)


def test_index_text_is_never_read_as_markup(qtbot):
    dialog = make(qtbot, catalog_entry("aquatic-tarot", description="<b>bold</b>"))
    assert dialog.description_label.textFormat() == Qt.TextFormat.PlainText
    assert dialog.heading_label.textFormat() == Qt.TextFormat.PlainText


def test_download_is_the_default_button(qtbot):
    dialog = make(qtbot)
    assert dialog.download_button.text() == "Download"
    assert dialog.download_button.isDefault()


def test_download_accepts_and_cancel_rejects(qtbot):
    dialog = make(qtbot)
    dialog.download_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted

    dialog = make(qtbot)
    dialog.cancel_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_the_dialog_prose_is_the_placeholder(qtbot):
    dialog = make(qtbot)
    assert dialog.windowTitle() == DOWNLOAD_TEXT["title"]
    assert dialog.explanation_label.text() == DOWNLOAD_TEXT["explanation"]


def test_a_cover_not_yet_fetched_paints_the_placeholder(qtbot):
    dialog = make(qtbot)
    assert dialog.cover.size() == DeckDownloadDialog.COVER_SIZE
    assert not dialog.cover.grab().isNull()


@pytest.mark.parametrize("kind", list(FailureKind))
def test_every_failure_has_its_placeholder(kind):
    assert failure_text(DownloadFailure(kind, "detail")).startswith("[failed:")
