import gc
import json

import pytest
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QGraphicsScene, QWidget

from tarot_canvas.ui.canvas import renderer
from tarot_canvas.ui.canvas import view as view_module
from tarot_canvas.ui.canvas.gl_marker import GlMarker
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


@pytest.fixture
def marker(tmp_path, monkeypatch):
    marker = GlMarker(tmp_path / "gl-check.json", ["key"])
    monkeypatch.setattr(renderer, "_marker", marker)
    monkeypatch.setattr(renderer, "_canvas_watched", False)
    return marker


def test_a_gl_viewport_that_never_initializes_records_a_failure(qtbot, monkeypatch, marker):
    monkeypatch.setattr(view_module, "canvas_uses_gl", lambda: True)
    view = PannableGraphicsView(QGraphicsScene())
    qtbot.addWidget(view)
    assert json.loads(marker.path.read_text())["stage"] == "canvas"

    view.show()

    qtbot.waitUntil(lambda: marker.path.exists() and "failed" in marker.path.read_text())


def test_only_the_first_gl_canvas_arms_the_marker(qtbot, monkeypatch, marker):
    monkeypatch.setattr(view_module, "canvas_uses_gl", lambda: True)
    qtbot.addWidget(PannableGraphicsView(QGraphicsScene()))
    marker.clear()

    qtbot.addWidget(PannableGraphicsView(QGraphicsScene()))

    assert not marker.path.exists()


def test_the_window_stage_clears_after_the_first_exposure(qtbot, marker):
    window = QWidget()
    qtbot.addWidget(window)
    window.winId()
    renderer.watch_window(window.windowHandle())
    gc.collect()
    assert json.loads(marker.path.read_text())["stage"] == "window"

    window.show()

    qtbot.waitUntil(lambda: not marker.path.exists())
