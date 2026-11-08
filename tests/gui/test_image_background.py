from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.settings import (
    BACKGROUND_FILL_KEY,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_POSITIONING_KEY,
    BACKGROUND_STYLE_KEY,
    get_settings,
)
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, GILT_ON_LIGHT
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab

RED = QColor("#c03030")


def write_image(base, name, colour=RED):
    image = QImage(QSize(64, 32), QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    base.mkdir(parents=True, exist_ok=True)
    assert image.save(str(base / name))
    return name


def store_image_ground(name, positioning, fill="#204060"):
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "image")
    settings.setValue(BACKGROUND_IMAGE_KEY, name)
    settings.setValue(BACKGROUND_POSITIONING_KEY, positioning)
    settings.setValue(BACKGROUND_FILL_KEY, fill)
    settings.sync()


def make_tab(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab.resize(400, 300)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def test_a_tiled_image_is_a_scene_brush(qtbot, backgrounds_base):
    store_image_ground(write_image(backgrounds_base, "felt.png"), "tile")

    tab = make_tab(qtbot)

    assert tab.view.backdrop is None
    assert tab.view.backgroundBrush().texture().size() == QSize(64, 32)


def test_a_positioned_image_is_held_over_the_viewport(qtbot, backgrounds_base):
    store_image_ground(write_image(backgrounds_base, "photo.png"), "crop", "#204060")

    tab = make_tab(qtbot)

    assert tab.view.backdrop is not None
    assert tab.view.backgroundBrush().color() == QColor("#204060")
    shown = tab.view.viewport().grab().toImage()
    assert shown.pixelColor(shown.width() // 2, shown.height() // 2) == RED
    assert shown.pixelColor(1, 1) == RED


def test_the_selection_tone_follows_the_images_colour(qtbot, backgrounds_base):
    store_image_ground(write_image(backgrounds_base, "linen.png", "#f4f0e8"), "crop", "#000000")
    tab = make_tab(qtbot)
    assert tab.gilt == QColor(GILT_ON_LIGHT)

    store_image_ground(write_image(backgrounds_base, "night.png", "#101018"), "tile")
    tab.apply_background_settings()
    assert tab.gilt == QColor(GILT_ON_DARK)


def test_a_missing_image_draws_the_gradient(qtbot, backgrounds_base):
    store_image_ground("gone.png", "crop")

    tab = make_tab(qtbot)

    assert tab.view.backdrop is None
    assert tab.view.backgroundBrush().style() == Qt.BrushStyle.RadialGradientPattern


def test_leaving_the_image_type_drops_the_backdrop(qtbot, backgrounds_base):
    store_image_ground(write_image(backgrounds_base, "photo.png"), "fit")
    tab = make_tab(qtbot)
    assert tab.view.backdrop is not None

    get_settings().setValue(BACKGROUND_STYLE_KEY, "gradient")
    tab.apply_background_settings()

    assert tab.view.backdrop is None
