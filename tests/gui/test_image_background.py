import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPixmap

from tarot_canvas.settings import (
    BACKGROUND_FILL_KEY,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_POSITIONING_KEY,
    BACKGROUND_STYLE_KEY,
    get_settings,
)
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.ground import shadow_for_ground
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


def _shadow_colour(card):
    image = card.shadow.pixmap().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2)


def test_the_shadow_takes_the_images_tone_and_follows_it(qtbot, backgrounds_base):
    store_image_ground(write_image(backgrounds_base, "linen.png", "#f4f0e8"), "crop", "#000000")
    tab = make_tab(qtbot)
    pixmap = QPixmap(120, 200)
    pixmap.fill(Qt.GlobalColor.white)
    card = DraggableCardItem(pixmap, {"id": "card-0"}, tab)
    tab.scene.addItem(card)

    tone, opacity = shadow_for_ground(QColor("#f4f0e8"))
    assert _shadow_colour(card).rgb() == tone.rgb()
    assert card.shadow.opacity() == pytest.approx(opacity)

    store_image_ground(write_image(backgrounds_base, "night.png", "#101018"), "tile")
    tab.apply_background_settings()
    tone, opacity = shadow_for_ground(QColor("#101018"))
    assert _shadow_colour(card).rgb() == tone.rgb()
    assert card.shadow.opacity() == pytest.approx(opacity)


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


def write_half_transparent(base, name):
    """Left half RED, right half fully transparent"""
    image = QImage(QSize(64, 32), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    for x in range(32):
        for y in range(32):
            image.setPixelColor(x, y, RED)
    base.mkdir(parents=True, exist_ok=True)
    assert image.save(str(base / name))
    return name


def test_a_tiled_image_with_transparency_is_laid_on_the_fill(qtbot, backgrounds_base):
    # Transparent texels over an uncleared viewport show the last frame: the canvas flickers
    store_image_ground(write_half_transparent(backgrounds_base, "holes.png"), "tile", "#204060")
    tab = make_tab(qtbot)

    texture = tab.view.backgroundBrush().textureImage()
    assert not texture.hasAlphaChannel()
    assert texture.pixelColor(8, 8) == RED
    assert texture.pixelColor(48, 8) == QColor("#204060")
