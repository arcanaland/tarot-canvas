import pytest
from PyQt6.QtCore import QPointF, QRectF, QSize, QThreadPool
from PyQt6.QtGui import QColor, QImage, QPixmap

from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.detail import (
    CARD_MAX_SIZE,
    DETAIL_MAX_PX,
    detail_level,
    load_card_art,
    logical_size,
    top_level,
)

ART_W, ART_H = 1200, 2000  # four times the size a card is placed at


@pytest.fixture(autouse=True)
def drained_pool():
    """No decode from one test may land in the next."""
    yield
    QThreadPool.globalInstance().waitForDone()


@pytest.fixture
def art(tmp_path):
    image = QImage(ART_W, ART_H, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    for x in range(0, ART_W, 2):  # one-pixel stripes: detail only full resolution keeps
        for y in range(0, ART_H, 50):
            image.setPixelColor(x, y, QColor("black"))
    path = tmp_path / "card.png"
    image.save(str(path))
    return str(path)


@pytest.fixture
def card(qapp, art):
    pixmap, source = load_card_art(art)
    item = DraggableCardItem(pixmap, {"id": "major_arcana/moon", "image": art})
    item.set_art_source(art, source)
    return item


def wait_for_level(qtbot, item, level):
    qtbot.waitUntil(lambda: item.detail() == level, timeout=5000)


# Choosing a level


def test_art_is_placed_fitted_and_never_enlarged():
    assert logical_size(QSize(ART_W, ART_H)) == QSize(300, 500)
    assert logical_size(QSize(2420, 1400)).width() == CARD_MAX_SIZE.width()
    assert logical_size(QSize(40, 64)) == QSize(40, 64)


def test_the_top_level_shows_every_pixel_of_the_art():
    assert top_level(QSize(ART_W, ART_H), QSize(300, 500)) == 4
    assert top_level(QSize(683, 1200), QSize(285, 500)) == 3  # the reference deck
    assert top_level(QSize(40, 64), QSize(40, 64)) == 1


def test_the_top_level_is_capped_for_enormous_art():
    assert top_level(QSize(12000, 20000), QSize(300, 500)) * 500 <= DETAIL_MAX_PX


@pytest.mark.parametrize(
    ("device_scale", "level"),
    [(0.1, 1), (1.0, 1), (1.01, 2), (2.0, 2), (2.3, 3), (8.0, 4), (16.0, 4)],
)
def test_a_level_is_never_magnified_and_never_more_than_the_art_holds(device_scale, level):
    assert detail_level(device_scale, 4) == level


# Swapping levels on a card


def test_a_card_is_placed_at_level_one(card):
    assert card.detail() == 1
    assert card.shape().boundingRect() == QRectF(0, 0, 300, 500)


def test_zooming_in_loads_a_sharper_level_at_the_same_logical_size(qtbot, card):
    placed = card.boundingRect()

    card.set_detail(3.5)
    wait_for_level(qtbot, card, 4)

    assert card.pixmap().size() == QSize(ART_W, ART_H)
    assert card.boundingRect() == placed


def test_a_sharp_card_keeps_its_shape_and_hit_area(qtbot, card):
    card.set_detail(4.0)
    wait_for_level(qtbot, card, 4)

    assert card.shape().boundingRect() == QRectF(0, 0, 300, 500)
    assert card.contains(QPointF(299, 499))
    assert not card.contains(QPointF(301, 250))


def test_coming_back_down_needs_no_load(qtbot, card):
    card.set_detail(4.0)
    wait_for_level(qtbot, card, 4)

    card.set_detail(2.0)
    assert card.detail() == 2  # at once, scaled from the level already shown
    assert card.pixmap().size() == QSize(600, 1000)

    card.set_detail(1.0)
    assert card.detail() == 1


def test_a_level_arriving_after_the_zoom_moved_on_is_dropped(qtbot, card):
    card.set_detail(4.0)
    card.set_detail(1.0)
    QThreadPool.globalInstance().waitForDone()
    qtbot.wait(50)

    assert card.detail() == 1


def test_a_card_with_no_art_file_stays_at_level_one(qapp):
    pixmap = QPixmap(300, 500)
    pixmap.fill()
    item = DraggableCardItem(pixmap, {"id": "card"})

    item.set_detail(8.0)

    assert item.detail() == 1


def test_the_shadow_is_built_from_the_logical_size(card):
    from tarot_canvas.ui.canvas.motion import SHADOW_BLUR_PX

    pad = 2 * round(SHADOW_BLUR_PX)
    assert card.shadow.boundingRect() == QRectF(0, 0, 300 + pad, 500 + pad)
