import logging
import sys

import pytest
from PyQt6.QtCore import qInstallMessageHandler, qWarning

from tarot_canvas.utils import crash_log


def raised(error):
    try:
        raise error
    except Exception:
        return sys.exc_info()


def test_an_unhandled_exception_is_logged_with_its_traceback(caplog):
    with caplog.at_level(logging.CRITICAL):
        crash_log.log_unhandled(*raised(OSError(5, "Input/output error")), abort=False)

    (record,) = caplog.records
    assert record.exc_info[0] is OSError
    assert "raised" in caplog.text  # the frame it came from


def test_a_release_build_keeps_running_after_one(monkeypatch, caplog):
    aborts = []
    monkeypatch.setattr(crash_log.os, "abort", lambda: aborts.append(True))

    crash_log.log_unhandled(*raised(ValueError("x")), abort=False)

    assert aborts == []


def test_a_devel_build_aborts_after_logging_one(monkeypatch, caplog):
    aborts = []
    monkeypatch.setattr(crash_log.os, "abort", lambda: aborts.append(caplog.text))
    monkeypatch.setattr(crash_log.logging, "shutdown", lambda: None)

    crash_log.log_unhandled(*raised(ValueError("half-built")), abort=True)

    (logged_before_abort,) = aborts
    assert "half-built" in logged_before_abort


@pytest.mark.parametrize(
    ("flatpak_id", "devel"),
    [
        ("land.arcana.TarotCanvas.Devel", True),
        ("land.arcana.TarotCanvas", False),
        (None, False),
    ],
)
def test_only_the_devel_flatpak_is_devel(flatpak_id, devel):
    environ = {} if flatpak_id is None else {"FLATPAK_ID": flatpak_id}

    assert crash_log.is_devel(environ) is devel


def test_a_qt_warning_reaches_the_log(caplog):
    previous = qInstallMessageHandler(crash_log.qt_message)
    try:
        with caplog.at_level(logging.WARNING, logger=crash_log.qt_log.name):
            qWarning(b"QPainter::begin: Paint device returned engine == 0")
    finally:
        qInstallMessageHandler(previous)

    (record,) = (r for r in caplog.records if r.name == crash_log.qt_log.name)
    assert record.levelno == logging.WARNING
    assert "QPainter::begin" in record.getMessage()
