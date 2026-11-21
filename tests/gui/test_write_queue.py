"""Writes to a created deck, one at a time off the GUI thread"""

import os

import pytest
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.deck_writer import DeckWriteError, DeckWriteReason
from tarot_canvas.ui.deck_view.write_queue import WriteQueue


@pytest.fixture
def deck(tmp_path, curation_file):
    return writer.create("Edited", majors_only=True, decks_root=tmp_path / "decks")


def picture(tmp_path, name):
    image = QImage(60, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    path = tmp_path / name
    assert image.save(os.fspath(path))
    return path


def test_queued_places_run_in_order_one_at_a_time(deck, tmp_path, qtbot, monkeypatch):
    calls = []
    place = writer.place

    def recording(path, card_id, image, progress=None):
        calls.append(("start", card_id))
        place(path, card_id, image, progress)
        calls.append(("end", card_id))

    monkeypatch.setattr(writer, "place", recording)
    queue = WriteQueue(deck)
    finished = []
    queue.finished.connect(lambda: finished.append(1))

    queue.place("major_arcana.00", picture(tmp_path, "a.png"))
    queue.place("major_arcana.01", picture(tmp_path, "b.png"))
    assert queue.is_busy()
    qtbot.waitUntil(lambda: len(finished) == 2)

    assert calls == [
        ("start", "major_arcana.00"),
        ("end", "major_arcana.00"),
        ("start", "major_arcana.01"),
        ("end", "major_arcana.01"),
    ]
    assert not queue.is_busy()


def test_an_unreadable_image_fails_and_the_next_job_still_runs(deck, tmp_path, qtbot):
    text = tmp_path / "notes.txt"
    text.write_text("not an image")
    queue = WriteQueue(deck)
    failures, finished = [], []
    queue.failed.connect(failures.append)
    queue.finished.connect(lambda: finished.append(1))

    queue.place("major_arcana.00", text)
    queue.place("major_arcana.01", picture(tmp_path, "b.png"))
    qtbot.waitUntil(lambda: finished == [1])

    assert len(failures) == 1
    assert isinstance(failures[0], DeckWriteError)
    assert failures[0].reason is DeckWriteReason.UNREADABLE_IMAGE
    assert [path.stem for path in (deck / "source" / "major_arcana").iterdir()] == ["01"]
