import logging
import threading

import pytest

from tarot_canvas.ui.windows.log_viewer import LogViewerDialog, QtLogHandler
from tarot_canvas.utils.logger import LOGGER_NAME


def handlers():
    return [h for h in logging.getLogger(LOGGER_NAME).handlers if isinstance(h, QtLogHandler)]


@pytest.fixture
def viewer(qtbot):
    dialog = LogViewerDialog()
    qtbot.addWidget(dialog)
    yield dialog
    dialog.reject()


def test_a_module_logger_reaches_the_viewer(qtbot, viewer):
    logging.getLogger("tarot_canvas.models.readings").warning("Could not read reading %s", "x")

    qtbot.waitUntil(lambda: "Could not read reading x" in viewer.log_display.toPlainText())
    # Formatted as the file has it, so a line copied from the viewer names its module
    assert "tarot_canvas.models.readings:" in viewer.log_display.toPlainText()


def test_a_record_arrives_on_the_next_event_loop_turn_not_inside_the_log_call(qtbot, viewer):
    logging.getLogger("tarot_canvas.ui").warning("queued")

    assert "queued" not in viewer.log_display.toPlainText()
    qtbot.waitUntil(lambda: "queued" in viewer.log_display.toPlainText())


def test_a_record_from_a_worker_thread_reaches_the_viewer(qtbot, viewer):
    worker = threading.Thread(
        target=lambda: logging.getLogger("tarot_canvas.worker").warning("from a worker")
    )
    worker.start()
    worker.join()

    qtbot.waitUntil(lambda: "from a worker" in viewer.log_display.toPlainText())


def test_a_finished_viewer_takes_its_handler_off_the_logger(qtbot):
    before = len(handlers())
    dialog = LogViewerDialog()
    qtbot.addWidget(dialog)
    assert len(handlers()) == before + 1

    dialog.reject()

    assert len(handlers()) == before
