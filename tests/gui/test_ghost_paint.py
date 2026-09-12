import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from tarot_canvas.ui.library import ghost_paint
from tarot_canvas.ui.library.ghost_paint import paint_ghost_cover, paint_placeholder_well

RECT = QRect(10, 10, 120, 180)


def art():
    pixmap = QPixmap(120, 180)
    pixmap.fill(QColor("red"))
    return pixmap


def paint(pixmap, background=Qt.GlobalColor.transparent, **kwargs):
    """The image, and the painter's opacity once the call returns."""
    image = QImage(140, 200, QImage.Format.Format_ARGB32)
    image.fill(background)
    painter = QPainter(image)
    paint_ghost_cover(painter, RECT, pixmap, **kwargs)
    opacity = painter.opacity()
    painter.end()
    return image, opacity


@pytest.mark.parametrize("make", [QPixmap, art], ids=["null-pixmap", "art"])
@pytest.mark.parametrize(
    "kwargs",
    [{}, {"progress": 0}, {"progress": 0.5}, {"progress": 1}, {"failed": True}],
    ids=["plain", "progress-0", "progress-half", "progress-1", "failed"],
)
def test_painting_leaves_the_painter_as_it_found_it(qapp, make, kwargs):
    _, opacity = paint(make(), emblem=QIcon.fromTheme("download"), **kwargs)
    assert opacity == 1.0


def test_a_highlight_behind_the_art_does_not_show_through(qapp):
    """A selected tile paints Highlight under the cover; the veil is opaque over it"""
    ground = QColor("white")
    plain, _ = paint(art(), background=QColor("white"), ground=ground)
    selected, _ = paint(art(), background=QColor("blue"), ground=ground)

    colour = selected.pixelColor(RECT.center())
    assert colour == plain.pixelColor(RECT.center())
    # Red art faded towards white, as the old 45% opacity drew it on white
    assert colour.red() == 255
    assert 130 < colour.green() < 150
    assert colour.green() == colour.blue()


@pytest.mark.parametrize("progress", [-0.5, 1.5])
def test_progress_out_of_range_is_clamped_not_raised(qapp, progress):
    paint(art(), progress=progress)


def test_an_emblem_the_theme_lacks_draws_nothing(qapp):
    """Not even the disc it would sit on"""
    bare, _ = paint(art(), emblem=None)
    missing, _ = paint(art(), emblem=QIcon())
    assert missing == bare
    paint(QPixmap(), emblem=None)


def test_failure_asks_the_theme_for_the_error_emblem(qapp, monkeypatch):
    asked = []
    real = QIcon.fromTheme
    monkeypatch.setattr(
        ghost_paint.QIcon, "fromTheme", staticmethod(lambda name: asked.append(name) or real(name))
    )

    paint(art(), emblem=QIcon())
    assert asked == []

    paint(art(), failed=True, emblem=QIcon())
    assert asked == ["dialog-error"]


def test_the_bar_is_painted_across_the_bottom_of_the_cover(qapp):
    """The one pixel check: the bar's bottom row differs from unbarred art."""
    plain, _ = paint(art())
    full, _ = paint(art(), progress=1)

    row = RECT.bottom()
    assert any(plain.pixel(x, row) != full.pixel(x, row) for x in range(RECT.left(), RECT.right()))
    # Above the bar nothing changes
    row = RECT.center().y()
    assert all(plain.pixel(x, row) == full.pixel(x, row) for x in range(RECT.left(), RECT.right()))


def test_the_placeholder_well_leaves_the_painter_as_it_found_it(qapp):
    image = QImage(140, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.setBrush(QColor("blue"))
    paint_placeholder_well(painter, RECT, qapp.palette())
    assert painter.brush().color() == QColor("blue")
    painter.end()
