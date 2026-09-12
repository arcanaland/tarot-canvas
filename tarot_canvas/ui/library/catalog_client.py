"""The app-wide deck catalog"""

import hashlib
import json
import logging
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from tarot_canvas._version import __version__
from tarot_canvas.models.catalog import (
    INDEX_TTL,
    INDEX_URL,
    IndexAction,
    IndexMeta,
    index_action,
    read_index,
)
from tarot_canvas.settings import (
    SHOW_AVAILABLE_DECKS_DEFAULT,
    SHOW_AVAILABLE_DECKS_KEY,
    get_settings,
)
from tarot_canvas.utils.path_helper import get_cache_directory

# for testing
URL_ENV = "TAROT_CANVAS_CATALOG_URL"
TTL_ENV = "TAROT_CANVAS_CATALOG_TTL"

INDEX_FILE = "index.json"
META_FILE = "index.meta.json"
COVERS_DIR = "covers"
COVER_SUFFIXES = frozenset({".jpg", ".webp", ".png"})

TRANSFER_TIMEOUT_MS = 30_000

log = logging.getLogger("TarotCanvas.catalog")


class QtTransport(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._network = None

    def get(self, url, *, etag=None, callback):
        if self._network is None:
            self._network = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(url))
        # Release assets redirect to a signed objects host
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader, f"TarotCanvas/{__version__}"
        )
        request.setTransferTimeout(TRANSFER_TIMEOUT_MS)
        if etag:
            request.setRawHeader(b"If-None-Match", etag.encode("latin-1"))
        reply = self._network.get(request)
        reply.finished.connect(partial(self._finished, reply, callback))

    @staticmethod
    def _finished(reply, callback):
        reply.deleteLater()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status = int(status) if status is not None else None
        etag = reply.rawHeader(b"ETag").data().decode("latin-1") or None
        error = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            error = f"{reply.error().name}: {reply.errorString()}"
        callback(status, reply.readAll().data(), etag, error)


class DeckCatalog(QObject):
    """Which decks the reference-deck index has."""

    entries_changed = pyqtSignal()
    cover_ready = pyqtSignal(str)  # the cover's URL

    def __init__(self, transport=None, cache_dir=None, clock=None, parent=None):
        super().__init__(parent)
        self._transport = transport if transport is not None else QtTransport(self)
        self._dir = Path(cache_dir or get_cache_directory("tarot-canvas/catalog"))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._url = INDEX_URL
        self._ttl = INDEX_TTL
        self._enabled = None  # read from the settings once, when first needed
        self._activated = False
        self._attempted = False  # one index request per session, success or not
        self._meta = None
        self._entries = []
        self._covers_requested = set()

    # --- API ----------------------------------------------------------------------

    def entries(self):
        return list(self._entries) if self.is_enabled() else []

    def cover_path(self, entry):
        path = self._cover_file(entry.cover)
        return str(path) if path is not None and path.is_file() else None

    def is_enabled(self):
        if self._enabled is None:
            value = get_settings().value(
                SHOW_AVAILABLE_DECKS_KEY, SHOW_AVAILABLE_DECKS_DEFAULT, type=bool
            )
            self._enabled = bool(value)
        return self._enabled

    def activate(self):
        """Load the cache and revalidate it if needed."""
        if self._activated:
            return
        self._activated = True
        self._url, self._ttl = _overrides()
        if self.is_enabled():
            self._start()

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        if enabled == self.is_enabled():
            return
        self._enabled = enabled
        if not self._activated:
            return
        if enabled:
            self._start()
        else:
            self.entries_changed.emit()

    # --- index --------------------------------------------------------------------

    def _start(self):
        self._load_cache()
        action = index_action(self._meta, self._clock(), __version__, self._attempted, self._ttl)
        if action is not IndexAction.USE_CACHE:
            self._attempted = True
            etag = self._meta.etag if action is IndexAction.REVALIDATE else None
            self._transport.get(self._url, etag=etag, callback=self._on_index)
        self._fetch_missing_covers()

    def _load_cache(self):
        meta = _read_meta(self._dir / META_FILE)
        # skip if we're testing
        if meta is not None and meta.url != self._url:
            meta = None
        entries = []
        if meta is not None:
            try:
                data = (self._dir / INDEX_FILE).read_bytes()
            except OSError:
                meta = None  # a 304 would leave us with nothing
            else:
                entries = read_index(data) or []
        self._meta = meta
        self._entries = entries
        if entries:
            self.entries_changed.emit()

    def _on_index(self, status, body, etag, error):
        if error is not None or status not in (200, 304, None):
            log.warning("index %s: %s; keeping the cache", self._url, error or f"HTTP {status}")
            return

        now = self._clock()
        if status == 304:
            if self._meta is None:
                log.warning("index %s: 304 to an unconditional request", self._url)
                return
            self._meta = replace(
                self._meta, etag=etag or self._meta.etag, checked_at=now, app_version=__version__
            )
            self._write_meta()
            return

        try:
            _write_atomic(self._dir / INDEX_FILE, body)
        except OSError as e:
            log.warning("could not cache the index: %s", e)
        else:
            self._meta = IndexMeta(self._url, etag, now, __version__)
            self._write_meta()

        entries = read_index(body)
        if (entries or []) != self._entries:
            self._entries = entries or []
            if self.is_enabled():
                self.entries_changed.emit()
        self._fetch_missing_covers()
        if entries is not None:
            self._collect_covers()

    def _write_meta(self):
        data = json.dumps(self._meta.to_dict(), indent=2).encode()
        try:
            _write_atomic(self._dir / META_FILE, data)
        except OSError as e:
            log.warning("could not cache the index metadata: %s", e)

    # --- covers -------------------------------------------------------------------

    def _cover_file(self, url):
        if not url:
            return None
        suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
        if suffix not in COVER_SUFFIXES:
            return None
        name = hashlib.sha256(url.encode()).hexdigest()[:32] + suffix
        return self._dir / COVERS_DIR / name

    def _fetch_missing_covers(self):
        if not self.is_enabled():
            return
        for entry in self._entries:
            url = entry.cover
            if not url or url in self._covers_requested:
                continue
            self._covers_requested.add(url)
            path = self._cover_file(url)
            if path is None:
                log.warning("cover %s is not a .jpg, .webp or .png; skipped", url)
            elif not path.is_file():
                self._transport.get(url, callback=partial(self._on_cover, url, path))

    def _on_cover(self, url, path, status, body, etag, error):
        if error is not None or status not in (200, None) or not body:
            log.warning("cover %s: %s", url, error or f"HTTP {status}")
            return
        try:
            _write_atomic(path, body)
        except OSError as e:
            log.warning("could not cache cover %s: %s", url, e)
            return
        self.cover_ready.emit(url)

    def _collect_covers(self):
        """Delete covers no current entry names."""
        keep = {path.name for e in self._entries if (path := self._cover_file(e.cover))}
        try:
            files = list((self._dir / COVERS_DIR).iterdir())
        except OSError:
            return
        for file in files:
            if file.name in keep:
                continue
            try:
                file.unlink()
            except OSError as e:
                log.warning("could not remove cover %s: %s", file, e)


def _overrides():
    url = os.environ.get(URL_ENV) or INDEX_URL
    ttl = INDEX_TTL
    raw = os.environ.get(TTL_ENV)
    if raw is not None:
        try:
            seconds = int(raw)
        except ValueError:
            seconds = -1
        if seconds < 0:
            log.warning("%s=%r is not a whole number of seconds; ignored", TTL_ENV, raw)
        else:
            ttl = timedelta(seconds=seconds)
    return url, ttl


def _read_meta(path):
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError, RecursionError):
        return None
    return IndexMeta.from_dict(data)


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


_instance = None


def deck_catalog():
    global _instance
    if _instance is None:
        _instance = DeckCatalog()
    return _instance
