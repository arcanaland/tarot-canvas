import struct

import pytest
from PyQt6.QtCore import QBuffer, QIODevice, QSize
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.ui.canvas.detail import art_size, fit_device_size, load_card_art, read_art
from tarot_canvas.ui.library.cover_cache import CoverCache


@pytest.mark.parametrize(
    ("source", "well", "dpr", "expected"),
    [
        (QSize(1200, 2000), QSize(300, 200), 1, QSize(120, 200)),  # tall in a wide well
        (QSize(2000, 1000), QSize(146, 220), 1, QSize(146, 73)),  # wide in a tall well
        (QSize(1200, 2000), QSize(146, 220), 2, QSize(264, 440)),
        (QSize(100, 150), QSize(146, 220), 1, QSize(100, 150)),  # never upscaled
        (QSize(200, 300), QSize(146, 220), 2, QSize(200, 300)),
    ],
)
def test_fit_device_size(source, well, dpr, expected):
    assert fit_device_size(source, well, dpr) == expected


def test_an_empty_fit_is_empty():
    assert fit_device_size(QSize(100, 100), QSize(0, 0), 1).isEmpty()


@pytest.fixture
def rotated_jpeg(qapp, tmp_path):
    """A 400x200 JPEG whose EXIF orientation turns it upright, 200x400."""
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG")
    data = bytes(buffer.data())
    ifd = struct.pack(">H", 1) + struct.pack(">HHII", 0x0112, 3, 1, 6 << 16) + bytes(4)
    exif = b"Exif\x00\x00MM\x00\x2a\x00\x00\x00\x08" + ifd
    path = tmp_path / "rotated.jpg"
    path.write_bytes(data[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + data[2:])
    return str(path)


def test_rotated_art_is_fitted_and_read_upright(rotated_jpeg):
    source = art_size(rotated_jpeg)
    assert source == QSize(200, 400)
    size = fit_device_size(source, QSize(146, 220), 1)
    assert size == QSize(110, 220)
    assert read_art(rotated_jpeg, size).size() == size
    assert load_card_art(rotated_jpeg)[1] == QSize(200, 400)
    assert CoverCache().get(rotated_jpeg, QSize(146, 220)).size() == size
