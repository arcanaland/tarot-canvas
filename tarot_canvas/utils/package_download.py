"""Download one deck package, verify it, and install it off the GUI thread.

The consumer rescans (`deck_manager.rescan()`) on `succeeded`; this module does
not import the deck manager, whose import builds a singleton that touches disk.
It logs nothing either: `DownloadFailure.detail` is for the consumer to log.
"""

import contextlib
import enum
import hashlib
import os
import traceback
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from tarot_canvas.models.deck_container import ContainerError
from tarot_canvas.models.deck_install import InstallError, InstallReason, install_container


class FailureKind(enum.Enum):
    NETWORK = "network"
    HTTP = "http"
    INTEGRITY = "integrity"
    CONTAINER = "container"
    DESTINATION_EXISTS = "destination exists"
    FILESYSTEM = "filesystem"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DownloadFailure:
    kind: FailureKind
    detail: str  # for the log only; never shown to a user


def failure_for(exc):
    """The FailureKind an exception from `install_container` stands for."""
    if isinstance(exc, ContainerError):
        return DownloadFailure(FailureKind.CONTAINER, str(exc))
    if isinstance(exc, InstallError):
        if exc.reason is InstallReason.DESTINATION_EXISTS:
            return DownloadFailure(FailureKind.DESTINATION_EXISTS, str(exc))
        return DownloadFailure(FailureKind.FILESYSTEM, str(exc))
    if isinstance(exc, OSError):
        return DownloadFailure(FailureKind.FILESYSTEM, str(exc))
    # The container is the only untrusted input, so blame it, with the evidence.
    detail = "".join(traceback.format_exception(exc))
    return DownloadFailure(FailureKind.CONTAINER, detail)


class _InstallReporter(QObject):
    """Lives on the GUI thread, so signals emitted from the pool queue back to it."""

    succeeded = pyqtSignal(str)
    failed = pyqtSignal(object)


class _InstallJob(QRunnable):
    def __init__(self, container, dest, staging_root, reporter):
        super().__init__()
        self._args = (container, dest, staging_root)
        self._reporter = reporter

    def run(self):
        try:
            path = install_container(*self._args)
        except Exception as e:
            signal, value = self._reporter.failed, failure_for(e)
        else:
            signal, value = self._reporter.succeeded, str(path)
        # RuntimeError: the PackageDownload, and so its reporter, was deleted meanwhile.
        with contextlib.suppress(RuntimeError):
            signal.emit(value)


class _Phase(enum.Enum):
    IDLE = enum.auto()
    DOWNLOADING = enum.auto()
    INSTALLING = enum.auto()


class PackageDownload(QObject):
    """Fetch `url`, check it is exactly `size` bytes hashing to `sha256`, install at `dest`.

    Exactly one of `succeeded` or `failed` follows every `start()`, and never
    from inside it. The `.part` file is gone by the time either is emitted.
    """

    progress = pyqtSignal("qint64", "qint64")  # received, total
    succeeded = pyqtSignal(str)  # the installed deck root
    failed = pyqtSignal(object)  # a DownloadFailure

    def __init__(self, url, size, sha256, dest, staging_root, network=None, parent=None):
        super().__init__(parent)
        self._url = QUrl(url)
        self._size = int(size)
        self._sha256 = sha256.lower()
        self._dest = Path(dest)
        self._staging_root = Path(staging_root)
        self._network = network
        self._reporter = _InstallReporter(self)
        self._reporter.succeeded.connect(self._on_installed)
        self._reporter.failed.connect(self._fail)
        self._phase = _Phase.IDLE
        self._reply = None
        self._file = None

    @property
    def part_path(self):
        return self._staging_root / f"{self._dest.name}.tarotdeck.part"

    def is_running(self):
        return self._phase is not _Phase.IDLE

    def start(self):
        if self.is_running():
            return
        self._phase = _Phase.DOWNLOADING
        self._received = 0
        self._hash = hashlib.sha256()
        self._cancelled = False
        self._failure = None

        # Checked again at install; this saves downloading only to be refused.
        if os.path.lexists(self._dest):
            self._fail_soon(FailureKind.DESTINATION_EXISTS, str(self._dest))
            return
        try:
            self._staging_root.mkdir(parents=True, exist_ok=True)
            self._file = open(self.part_path, "wb")  # noqa: SIM115 - closed in _close_file
        except OSError as e:
            self._fail_soon(FailureKind.FILESYSTEM, str(e))
            return

        if self._network is None:
            self._network = QNetworkAccessManager(self)
        request = QNetworkRequest(self._url)
        # Release assets redirect to a signed objects host; never https -> http.
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        self._reply = self._network.get(request)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.finished.connect(self._on_finished)

    def cancel(self):
        """Abort the download. Once installing has begun it runs to its end."""
        if self._phase is _Phase.DOWNLOADING and self._reply is not None:
            self._cancelled = True
            self._reply.abort()

    # --- download -----------------------------------------------------------------

    def _on_ready_read(self):
        reply = self._reply
        if reply is None or self._failure is not None:
            return
        data = reply.readAll().data()
        if not data or _http_status(reply) >= 400:
            return  # an error page is not the package
        self._received += len(data)
        if self._received > self._size:
            self._abort(FailureKind.INTEGRITY, f"more than the declared {self._size} bytes")
            return
        try:
            self._file.write(data)
        except OSError as e:
            self._abort(FailureKind.FILESYSTEM, str(e))
            return
        self._hash.update(data)
        self.progress.emit(self._received, self._size)

    def _abort(self, kind, detail):
        self._failure = DownloadFailure(kind, detail)
        self._reply.abort()

    def _on_finished(self):
        self._on_ready_read()  # anything that arrived with finished
        reply, self._reply = self._reply, None
        reply.deleteLater()
        self._close_file()

        failure = self._failure or self._transport_failure(reply)
        if failure is None and self._cancelled:
            # A file:// reply aborts with NoError, so the flag decides, not the code.
            failure = DownloadFailure(FailureKind.CANCELLED, "cancelled")
        if failure is None and self._received != self._size:
            detail = f"{self._received} bytes, expected {self._size}"
            failure = DownloadFailure(FailureKind.INTEGRITY, detail)
        if failure is None and self._hash.hexdigest() != self._sha256:
            detail = f"sha256 {self._hash.hexdigest()}, expected {self._sha256}"
            failure = DownloadFailure(FailureKind.INTEGRITY, detail)
        if failure is not None:
            self._fail(failure)
            return

        self._phase = _Phase.INSTALLING
        job = _InstallJob(self.part_path, self._dest, self._staging_root, self._reporter)
        QThreadPool.globalInstance().start(job)

    def _transport_failure(self, reply):
        error = reply.error()
        if error == QNetworkReply.NetworkError.NoError:
            return None
        if self._cancelled and error == QNetworkReply.NetworkError.OperationCanceledError:
            return DownloadFailure(FailureKind.CANCELLED, "cancelled")
        status = _http_status(reply)
        if status >= 400:
            return DownloadFailure(FailureKind.HTTP, f"HTTP {status}: {reply.errorString()}")
        return DownloadFailure(FailureKind.NETWORK, f"{error.name}: {reply.errorString()}")

    # --- outcomes -----------------------------------------------------------------

    def _fail_soon(self, kind, detail):
        failure = DownloadFailure(kind, detail)
        QTimer.singleShot(0, lambda: self._fail(failure))

    def _fail(self, failure):
        self._end()
        self.failed.emit(failure)

    def _on_installed(self, path):
        self._end()
        self.succeeded.emit(path)

    def _end(self):
        self._close_file()
        self.part_path.unlink(missing_ok=True)
        self._phase = _Phase.IDLE

    def _close_file(self):
        if self._file is not None:
            self._file.close()
            self._file = None


def _http_status(reply):
    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    return int(status) if status is not None else 0
