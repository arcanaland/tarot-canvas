import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.ui.covers.cache import CoverCache


def write(path, colour, modified_ns):
    image = QImage(20, 30, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    assert image.save(os.fspath(path), "PNG")
    os.utime(path, ns=(modified_ns, modified_ns))


def test_a_file_rewritten_in_place_is_decoded_again(tmp_path, qapp):
    path = tmp_path / "00.png"
    write(path, "red", 1_000_000_000)
    cache = CoverCache()
    size = QSize(20, 30)
    assert cache.get(path, size).toImage().pixelColor(5, 5) == QColor("red")

    write(path, "blue", 2_000_000_000)

    assert cache.get(path, size).toImage().pixelColor(5, 5) == QColor("blue")


def test_a_missing_file_has_no_pixmap(tmp_path, qapp):
    assert CoverCache().get(tmp_path / "gone.png", QSize(20, 30)) is None
