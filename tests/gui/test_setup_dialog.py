import io
import zipfile
from types import SimpleNamespace

import pytest

from tarot_canvas import main
from tarot_canvas.models import reference_deck
from tarot_canvas.models.reference_deck import ReferenceDeck
from tarot_canvas.ui.strings import SETUP

# Taken before conftest stubs it out for every test
download = ReferenceDeck.download_reference_deck


def deck_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("rider-waite-smith/deck.toml", "")
    return buffer.getvalue()


@pytest.fixture
def reported_keys(tmp_path, monkeypatch):
    """The keys a download reports, run against a fake server."""
    body = deck_zip()
    monkeypatch.setattr(reference_deck, "get_data_directory", lambda name: tmp_path)
    monkeypatch.setattr(
        reference_deck.requests,
        "head",
        lambda url: SimpleNamespace(headers={"content-length": str(len(body))}),
    )
    monkeypatch.setattr(
        reference_deck.requests,
        "get",
        lambda url, stream: SimpleNamespace(
            status_code=200, iter_content=lambda chunk_size: [body]
        ),
    )
    keys = []
    download(progress_callback=lambda percent, key: keys.append(key))
    return keys


def test_a_download_reports_every_step(reported_keys):
    assert reported_keys == ["starting", "downloading", "extracting_start", "extracting", "done"]


def test_the_setup_dialog_shows_each_step(qtbot, monkeypatch, reported_keys):
    monkeypatch.setattr(main.SetupDialog, "start_download", lambda self: None)
    dialog = main.SetupDialog()
    qtbot.addWidget(dialog)
    for key in reported_keys:
        dialog.update_progress(50, key)
        assert dialog.status_label.text() == SETUP[key]
