"""Local files carried by a drag or drop, through the document portal under Flatpak

A drag from outside the sandbox names host paths in text/uri-list, which don't exist in
here. A portal-aware source (Dolphin, Files) also puts a key under a portal format, and
FileTransfer.RetrieveFiles trades it for paths under /run/user/N/doc/ that do. Qt does not
do this itself; KF6's KUrlMimeData does, but PyQt doesn't reach it.
"""

import logging
import os

log = logging.getLogger(__name__)

# The second is the name GTK 3 used
PORTAL_FORMATS = ("application/vnd.portal.filetransfer", "application/vnd.portal.files")


def offered_files(mime):
    """The paths a drag names, for deciding whether to take it; under Flatpak they may not exist here"""
    if mime is None or not mime.hasUrls():
        return []
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]


def dropped_files(mime):
    """The paths to read, on drop only: the portal honours a key once, so call this once per drop"""
    if mime is not None and _sandboxed():
        for name in PORTAL_FORMATS:
            if mime.hasFormat(name):
                key = bytes(mime.data(name)).rstrip(b"\0").decode()
                files = _retrieve(key)
                if files is not None:
                    return files
    return offered_files(mime)


def _sandboxed():
    return os.path.exists("/.flatpak-info")


def _retrieve(key):
    """The portal's paths for key, or None when it can't be asked"""
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:  # PyQt6.QtDBus is not guaranteed to be present
        return None
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    portal = QDBusInterface(
        "org.freedesktop.portal.Documents",
        "/org/freedesktop/portal/documents",
        "org.freedesktop.portal.FileTransfer",
        bus,
    )
    if not portal.isValid():
        return None
    reply = portal.call("RetrieveFiles", key, {})
    if reply.errorName():
        log.warning("The portal gave no files for a drop: %s", reply.errorMessage())
        return None
    arguments = reply.arguments()
    return [str(path) for path in arguments[0]] if arguments else None
