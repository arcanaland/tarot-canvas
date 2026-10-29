from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QGraphicsScene

from tarot_canvas.ui.canvas import view as view_module
from tarot_canvas.ui.canvas.view import PannableGraphicsView


def test_offscreen_paints_raster(qtbot):
    scene = QGraphicsScene()
    view = PannableGraphicsView(scene)
    qtbot.addWidget(view)

    assert not isinstance(view.viewport(), QOpenGLWidget)


def test_a_gl_viewport_that_never_initializes_falls_back_to_raster(qtbot, monkeypatch):
    # offscreen cannot show a QOpenGLWidget, so it is never valid here
    monkeypatch.setattr(view_module, "canvas_uses_gl", lambda: True)
    scene = QGraphicsScene()
    view = PannableGraphicsView(scene)
    qtbot.addWidget(view)
    assert isinstance(view.viewport(), QOpenGLWidget)

    view.show()

    qtbot.waitUntil(lambda: not isinstance(view.viewport(), QOpenGLWidget))
