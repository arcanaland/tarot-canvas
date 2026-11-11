import pytest
from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from tarot_canvas.models.ground import Ground
from tarot_canvas.ui.canvas import ground_paint, swirl
from tarot_canvas.ui.canvas.ground import GROUND_HUES, checkerboard_partner

SIDE = 64
RED = QColor("#c03030")


@pytest.fixture(autouse=True)
def fresh_stills(qapp, monkeypatch):
    monkeypatch.setattr(ground_paint, "_swirl_stills", {})


def painted(ground, image=None, ratio=1.0):
    target = QImage(SIDE, SIDE, QImage.Format.Format_ARGB32_Premultiplied)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    ground_paint.paint_ground(painter, QRectF(0, 0, SIDE, SIDE), ground, ratio, image)
    painter.end()
    return target


def centre(image):
    return image.pixelColor(SIDE // 2, SIDE // 2)


def close(a, b, tolerance=6):
    a, b = QColor(a), QColor(b)
    return all(abs(x - y) <= tolerance for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


def solid_source(colour=RED, size=None):
    image = QImage(size or QSize(48, 32), QImage.Format.Format_RGB32)
    image.fill(colour)
    return image


def test_solid_is_its_colour():
    assert centre(painted(Ground(style="solid", color="#112233"))) == QColor("#112233")


def test_gradient_is_its_hues_aura_at_the_centre():
    image = painted(Ground(style="gradient", hue="green"))
    assert close(centre(image), GROUND_HUES["green"].aura[0])


def test_checkerboard_shows_both_squares():
    colour = QColor("#445566")
    image = painted(Ground(style="checkerboard", checkerboard_color=colour.name()))
    seen = {image.pixelColor(x, y).name() for x in range(0, SIDE, 4) for y in range(0, SIDE, 4)}
    assert colour.name() in seen
    assert checkerboard_partner(colour).name() in seen


def test_an_image_still_loading_is_its_fill():
    ground = Ground(style="image", image="felt.png", positioning="crop", fill="#204060")
    assert centre(painted(ground, image=None)) == QColor("#204060")


@pytest.mark.parametrize("positioning", ["crop", "stretch", "fit", "tile", "center"])
def test_an_image_paints_its_picture(positioning):
    ground = Ground(style="image", image="felt.png", positioning=positioning, fill="#204060")
    assert close(centre(painted(ground, image=solid_source())), RED)


@pytest.mark.parametrize("positioning", ["tile", "center"])
def test_tile_and_center_cover_the_miniature_as_crop(positioning):
    ground = Ground(style="image", image="felt.png", positioning=positioning, fill="#204060")
    image = painted(ground, image=solid_source(size=QSize(8, 8)))
    assert close(image.pixelColor(1, 1), RED)
    assert close(image.pixelColor(SIDE - 2, SIDE - 2), RED)


def test_an_image_with_alpha_shows_its_fill_through():
    source = QImage(QSize(16, 16), QImage.Format.Format_ARGB32)
    source.fill(Qt.GlobalColor.transparent)
    ground = Ground(style="image", image="felt.png", positioning="stretch", fill="#204060")
    assert close(centre(painted(ground, image=source)), QColor("#204060"))


def test_swirl_without_gl_is_aura_in_its_hue(monkeypatch):
    monkeypatch.setattr(swirl, "field", lambda: None)
    image = painted(Ground(style="swirl", hue="orange"))
    assert close(centre(image), GROUND_HUES["orange"].aura[0])


class FakeField:
    def __init__(self, colour=RED):
        self.colour = colour
        self.calls = []

    def render(self, t, size, values, centre, scale):
        self.calls.append((t, QSize(size), centre, scale))
        return solid_source(self.colour, size)


def test_swirl_is_one_still_render_per_hue_and_size(monkeypatch):
    field = FakeField()
    monkeypatch.setattr(swirl, "field", lambda: field)
    ground = Ground(style="swirl", hue="blue")

    assert close(centre(painted(ground)), RED)
    painted(ground)

    assert len(field.calls) == 1
    t, size, at, scale = field.calls[0]
    assert t == swirl.STILL_T
    assert size == swirl.field_size(QSize(SIDE, SIDE), 1.0, swirl.PARAMS["pixel"])
    assert at == (size.width() / 2, size.height() / 2)
    assert scale == 1.0

    painted(Ground(style="swirl", hue="red"))
    assert len(field.calls) == 2


def test_a_failed_swirl_render_is_aura_and_never_raises(monkeypatch):
    class Broken:
        def render(self, *args):
            raise RuntimeError("driver gone")

    monkeypatch.setattr(swirl, "field", lambda: Broken())
    image = painted(Ground(style="swirl", hue="gold"))
    assert close(centre(image), GROUND_HUES["gold"].aura[0])


def test_a_real_swirl_still_paints_the_rect():
    if swirl.field() is None:
        pytest.skip("no GL context here")
    image = painted(Ground(style="swirl", hue="violet"))
    assert image.pixelColor(SIDE // 2, SIDE // 2).alpha() == 255
    assert image.pixelColor(1, 1).alpha() == 255
