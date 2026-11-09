import pytest
from PyQt6.QtCore import QRect, QSize
from PyQt6.QtGui import QColor, QImage, QPainter

from tarot_canvas.ui.canvas import image_ground

RED = QColor("#c03030")
FILL = QColor("#102040")


def solid(size, colour=RED):
    image = QImage(size, QImage.Format.Format_RGB32)
    image.fill(colour)
    return image


def save(tmp_path, name, image):
    path = tmp_path / name
    assert image.save(str(path))
    return path


@pytest.mark.parametrize(
    ("positioning", "corner"),
    [("crop", RED), ("stretch", RED), ("fit", FILL), ("center", FILL)],
)
def test_each_positioning_places_the_image(qapp, positioning, corner):
    composed = image_ground.compose(solid(QSize(50, 25)), QSize(100, 100), positioning, FILL)

    assert composed.size() == QSize(100, 100)
    assert composed.pixelColor(50, 50) == RED
    assert composed.pixelColor(0, 0) == corner


def test_centered_keeps_the_images_own_size(qapp):
    composed = image_ground.compose(solid(QSize(20, 20)), QSize(100, 100), "center", FILL)

    assert composed.pixelColor(50, 50) == RED
    assert composed.pixelColor(35, 50) == FILL


def test_a_large_image_is_decoded_no_larger_than_covers_the_bound(qapp, tmp_path):
    path = save(tmp_path, "big.png", solid(QSize(400, 200)))

    image = image_ground.load(path, "crop", QSize(100, 100))

    assert image.size() == QSize(200, 100)


def test_centered_decodes_only_the_middle_the_bound_can_show(qapp, tmp_path):
    path = save(tmp_path, "big.png", solid(QSize(400, 200)))

    image = image_ground.load(path, "center", QSize(100, 100))

    assert image.size() == QSize(100, 100)


def test_a_small_image_is_never_scaled_up(qapp, tmp_path):
    path = save(tmp_path, "small.png", solid(QSize(30, 20)))

    assert image_ground.load(path, "crop", QSize(100, 100)).size() == QSize(30, 20)


def test_a_missing_or_broken_file_loads_nothing(qapp, tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_text("no")

    assert image_ground.load(tmp_path / "gone.png", "crop", QSize(10, 10)).isNull()
    assert image_ground.load(broken, "crop", QSize(10, 10)).isNull()


def test_the_average_colour_is_the_images_mean(qapp):
    image = solid(QSize(2, 1), QColor("#000000"))
    image.setPixelColor(1, 0, QColor("#ffffff"))

    average = image_ground.average_colour(image)

    assert 120 <= average.red() <= 135


def test_the_ground_paints_over_the_whole_device_and_recomposes_on_a_new_ratio(qapp):
    ground = image_ground.ImageGround(solid(QSize(50, 50)), "crop", FILL)
    for ratio in (1.0, 2.0):
        target = QImage(QSize(round(40 * ratio), round(30 * ratio)), QImage.Format.Format_RGB32)
        target.setDevicePixelRatio(ratio)
        target.fill(FILL)
        painter = QPainter(target)
        painter.translate(-500, -500)
        assert ground.paint(painter, QRect(0, 0, 40, 30), ratio)
        painter.end()
        assert target.pixelColor(0, 0) == RED
        assert target.pixelColor(target.width() - 1, target.height() - 1) == RED


def test_flatten_lays_transparency_on_the_fill(qapp):
    source = QImage(QSize(2, 1), QImage.Format.Format_ARGB32)
    source.setPixelColor(0, 0, RED)
    source.setPixelColor(1, 0, QColor(0, 0, 0, 0))

    flat = image_ground.flatten(source, FILL)

    assert not flat.hasAlphaChannel()
    assert flat.pixelColor(0, 0) == RED
    assert flat.pixelColor(1, 0) == FILL


def test_flatten_leaves_an_opaque_image_alone(qapp):
    source = solid(QSize(4, 4))
    assert image_ground.flatten(source, FILL) is source
