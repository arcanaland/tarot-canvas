from PyQt6.QtCore import QMimeData, QUrl

from tarot_canvas.ui import dropped_files as module
from tarot_canvas.ui.dropped_files import dropped_files, offered_files

HOST_PATH = "/home/someone/Pictures/00.png"
PORTAL_PATH = "/run/user/1000/doc/abc123/00.png"


def _mime(portal_key=None, name=module.PORTAL_FORMATS[0]):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(HOST_PATH), QUrl("https://example.org/x.png")])
    if portal_key is not None:
        mime.setData(name, portal_key.encode() + b"\0")
    return mime


def _sandbox(monkeypatch, inside, retrieved=None):
    asked = []
    monkeypatch.setattr(module, "_sandboxed", lambda: inside)

    def retrieve(key):
        asked.append(key)
        return retrieved

    monkeypatch.setattr(module, "_retrieve", retrieve)
    return asked


def test_offered_files_are_the_local_urls(qapp):
    assert offered_files(_mime()) == [HOST_PATH]
    assert offered_files(QMimeData()) == []
    assert offered_files(None) == []


def test_sandboxed_drop_trades_the_key_for_portal_paths(qapp, monkeypatch):
    asked = _sandbox(monkeypatch, inside=True, retrieved=[PORTAL_PATH])
    assert dropped_files(_mime("key-1")) == [PORTAL_PATH]
    assert asked == ["key-1"]


def test_gtk3_format_name_is_also_read(qapp, monkeypatch):
    asked = _sandbox(monkeypatch, inside=True, retrieved=[PORTAL_PATH])
    assert dropped_files(_mime("key-2", name=module.PORTAL_FORMATS[1])) == [PORTAL_PATH]
    assert asked == ["key-2"]


def test_portal_failure_falls_back_to_the_uri_list(qapp, monkeypatch):
    _sandbox(monkeypatch, inside=True, retrieved=None)
    assert dropped_files(_mime("key-3")) == [HOST_PATH]


def test_unsandboxed_drop_never_asks_the_portal(qapp, monkeypatch):
    asked = _sandbox(monkeypatch, inside=False, retrieved=[PORTAL_PATH])
    assert dropped_files(_mime("key-4")) == [HOST_PATH]
    assert asked == []
