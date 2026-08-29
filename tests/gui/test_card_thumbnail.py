import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.ui.widgets.card_thumbnail import CardThumbnail

# Some aspect ratios from my personal decks
CARD_SIZES = [(600, 1024), (1140, 1140), (2420, 1400)]


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

    painted_width, painted_height = _painted_art_size(thumbnail)
    # Loose tolerance
    assert painted_width / painted_height == pytest.approx(width / height, rel=0.02)


@pytest.mark.parametrize(("width", "height"), CARD_SIZES)
def test_thumbnail_fits_inside_its_box(qtbot, tmp_path, width, height):
    thumbnail = CardThumbnail(_card(tmp_path, width, height), str(tmp_path), size=QSize(150, 240))
    qtbot.addWidget(thumbnail)

    pixmap = thumbnail.image_label.pixmap()
    assert pixmap.width() <= thumbnail.image_size.width()
    assert pixmap.height() <= thumbnail.image_size.height()
    assert (
        pixmap.width() == thumbnail.image_size.width()
        or pixmap.height() == thumbnail.image_size.height()
    )


def test_thumbnail_falls_back_when_image_is_missing(qtbot, tmp_path):
    thumbnail = CardThumbnail(
        {"name": "Test Card", "image": str(tmp_path / "nope.png")}, str(tmp_path)
    )
    qtbot.addWidget(thumbnail)

    assert thumbnail.image_label.pixmap().isNull()
    assert thumbnail.image_label.text() == "Image not found"
