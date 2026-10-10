import threading

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSize, QThreadPool
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from tarot_canvas.ui.canvas import detail
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.widgets.card_thumbnail import CardThumbnail
from tests.conftest import MINIMAL_DECK_PATH

# Some aspect ratios from my personal decks
CARD_SIZES = [(600, 1024), (1140, 1140), (2420, 1400)]


@pytest.fixture(autouse=True)
def drained_pool():
    """No decode from one test may land in the next."""
    yield
    QThreadPool.globalInstance().waitForDone()


def _has_art(thumbnail):
    pixmap = thumbnail.image_label.pixmap()
    return pixmap is not None and not pixmap.isNull()


def _card(tmp_path, width, height):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    path = tmp_path / f"card-{width}x{height}.png"
    assert image.save(str(path))
    return {"name": "Test Card", "image": str(path)}


def _painted_art_size(thumbnail):
    """Size of the card art as actually painted"""
    image = thumbnail.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    red = QColor("red").rgb()
    columns = [
        x for x in range(image.width()) for y in range(image.height()) if image.pixel(x, y) == red
    ]
    rows = [
        y for y in range(image.height()) for x in range(image.width()) if image.pixel(x, y) == red
    ]
    assert columns and rows, "card art was not painted"
    return max(columns) - min(columns) + 1, max(rows) - min(rows) + 1


@pytest.mark.parametrize(("width", "height"), CARD_SIZES)
def test_thumbnail_preserves_card_aspect_ratio(qtbot, tmp_path, width, height):
    thumbnail = CardThumbnail(_card(tmp_path, width, height), str(tmp_path), size=QSize(150, 240))
    qtbot.addWidget(thumbnail)
    qtbot.waitUntil(lambda: _has_art(thumbnail))

    painted_width, painted_height = _painted_art_size(thumbnail)
    # Loose tolerance
    assert painted_width / painted_height == pytest.approx(width / height, rel=0.02)


@pytest.mark.parametrize(("width", "height"), CARD_SIZES)
def test_thumbnail_fits_inside_its_box(qtbot, tmp_path, width, height):
    thumbnail = CardThumbnail(_card(tmp_path, width, height), str(tmp_path), size=QSize(150, 240))
    qtbot.addWidget(thumbnail)
    qtbot.waitUntil(lambda: _has_art(thumbnail))

    pixmap = thumbnail.image_label.pixmap()
    assert pixmap.width() <= thumbnail.image_size.width()
    assert pixmap.height() <= thumbnail.image_size.height()
    assert (
        pixmap.width() == thumbnail.image_size.width()
        or pixmap.height() == thumbnail.image_size.height()
    )


def test_thumbnail_falls_back_when_image_is_missing(qtbot, tmp_path, monkeypatch):
    requests = []
    monkeypatch.setattr(detail.ArtLoader, "request", lambda *args: requests.append(args))
    thumbnail = CardThumbnail(
        {"name": "Test Card", "image": str(tmp_path / "nope.png")}, str(tmp_path)
    )
    qtbot.addWidget(thumbnail)

    assert thumbnail.image_label.pixmap().isNull()
    assert thumbnail.image_label.text() == "Image not found"
    assert requests == []


def test_a_thumbnail_deleted_before_its_art_lands_is_skipped(qtbot, tmp_path, monkeypatch):
    release = threading.Event()
    read_art = detail.read_art

    def held_read_art(*args):
        release.wait(5)
        return read_art(*args)

    monkeypatch.setattr(detail, "read_art", held_read_art)
    thumbnail = CardThumbnail(_card(tmp_path, 600, 1024), str(tmp_path))
    sip.delete(thumbnail)

    release.set()
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()


def test_the_deck_view_appears_before_its_art_is_decoded(qtbot, monkeypatch):
    release = threading.Event()
    read_art = detail.read_art

    def held_read_art(*args):
        release.wait(5)
        return read_art(*args)

    monkeypatch.setattr(detail, "read_art", held_read_art)
    tab = DeckViewTab(str(MINIMAL_DECK_PATH))
    qtbot.addWidget(tab)
    thumbnails = tab.findChildren(CardThumbnail)

    assert thumbnails
    assert not any(_has_art(t) for t in thumbnails)

    release.set()
    QThreadPool.globalInstance().waitForDone()
    qtbot.waitUntil(lambda: all(_has_art(t) for t in thumbnails))


def test_the_context_menu_offers_open_and_copy(qtbot, tmp_path):
    thumbnail = CardThumbnail(_card(tmp_path, 600, 1024), str(tmp_path))
    qtbot.addWidget(thumbnail)
    actions = {a.text().replace("&", ""): a for a in thumbnail.card_menu().actions()}

    assert list(actions) == ["Open Card", "Copy Card"]
    with qtbot.waitSignal(thumbnail.copy_requested, timeout=1000):
        actions["Copy Card"].trigger()
    with qtbot.waitSignal(thumbnail.double_clicked, timeout=1000):
        actions["Open Card"].trigger()
