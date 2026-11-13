"""Unhandled exceptions, native crashes and Qt's own messages go to the log file.

Without these, each of them reaches only stderr, which is gone when the app was started
from a launcher or from a terminal that has since closed.
"""

import faulthandler
import logging
import os
import sys
from functools import partial

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

log = logging.getLogger(__name__)
qt_log = logging.getLogger("tarot_canvas.qt")

QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}

# faulthandler writes to this file's descriptor, so it must stay open
_fault_file = None


def is_devel(environ=os.environ):
    """The Devel Flatpak, where a crash should stay loud."""
    return environ.get("FLATPAK_ID", "").endswith(".Devel")


def log_unhandled(exc_type, exc, tb, *, abort):
    """sys.excepthook: log the traceback, then abort or carry on.

    PyQt aborts on an exception that leaves a slot only while sys.excepthook is the
    default, so installing this one is what lets the app keep running.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
    if abort:
        logging.shutdown()
        os.abort()


def qt_message(mode, context, message):
    """Qt's message handler: its warnings go where ours do."""
    category = context.category
    if category and category != "default":
        message = f"{category}: {message}"
    qt_log.log(QT_LEVELS.get(mode, logging.WARNING), "%s", message)


def install(log_file, *, abort):
    """Route exceptions, native crashes and Qt messages to log_file."""
    global _fault_file

    sys.excepthook = partial(log_unhandled, abort=abort)

    _fault_file = open(log_file, "a")  # noqa: SIM115 - held open for faulthandler
    faulthandler.enable(file=_fault_file, all_threads=True)

    qInstallMessageHandler(qt_message)
