import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QRadialGradient

from tarot_canvas.settings import BACKGROUND_STYLE_KEY, get_settings
from tarot_canvas.ui.canvas import swirl
from tarot_canvas.ui.canvas.ground import GROUND_HUE_DEFAULT, GROUND_HUES
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab


def make_tab(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def test_without_gl_the_swirl_draws_the_gradient(qtbot, monkeypatch):
    monkeypatch.setattr(swirl, "field", lambda: None)
    get_settings().setValue(BACKGROUND_STYLE_KEY, "swirl")
    tab = make_tab(qtbot)
    assert tab.view.swirl is None
    assert isinstance(tab.view.backgroundBrush().gradient(), QRadialGradient)
    tab.view.viewport().repaint()
    qtbot.wait(1100)


def test_a_failed_render_falls_back_and_never_raises(qtbot, monkeypatch):
    class Broken:
        def render(self, *args):
            raise RuntimeError("driver gone")

    monkeypatch.setattr(swirl, "field", lambda: Broken())
    get_settings().setValue(BACKGROUND_STYLE_KEY, "swirl")
    tab = make_tab(qtbot)
    qtbot.wait(20)
    tab.view.viewport().repaint()
    assert tab.view.swirl.image is None
    assert tab.view.backgroundBrush().color() == GROUND_HUES[GROUND_HUE_DEFAULT].swirl[0]
    get_settings().setValue(BACKGROUND_STYLE_KEY, "gradient")
    tab.apply_background_settings()
    assert tab.view.swirl is None
    qtbot.wait(1100)


def test_the_field_is_a_pixel_factor_of_the_device_size():
    assert swirl.field_size(QSize(1000, 600), 1.0, 3) == QSize(334, 200)
    assert swirl.field_size(QSize(1000, 600), 2.0, 3) == QSize(667, 400)
    assert swirl.field_size(QSize(1, 1), 1.0, 8) == QSize(1, 1)


class Viewport:
    def __init__(self, gl):
        self.gl = gl


class View:
    def __init__(self, gl):
        self._viewport = Viewport(gl)

    def viewport(self):
        return self._viewport


def bare_ground(monkeypatch, gl=True):
    """A ground with no field or view, counting the renders it would make."""
    monkeypatch.setattr(swirl, "_is_gl", lambda viewport: viewport.gl)
    ground = swirl.SwirlGround.__new__(swirl.SwirlGround)
    ground.view = View(gl)
    ground.t = swirl.STILL_T
    ground.ticks = 0
    ground.image = None
    ground.animating = False
    ground.dirty = False
    ground.still = False
    ground.governor = swirl.Governor(2)
    ground._measure = False
    ground._failed = False
    ground.renders = []
    ground.requests = []
    ground.render = lambda: ground.renders.append(ground.t)
    ground.request = lambda: ground.requests.append(ground.t)
    return ground


def test_a_still_ground_keeps_its_time(monkeypatch):
    ground = bare_ground(monkeypatch)
    ground.advance(0.1, False)
    assert ground.t == swirl.STILL_T


def test_the_grounds_time_runs_at_its_pace(monkeypatch):
    ground = bare_ground(monkeypatch)
    ground.advance(0.1, True)
    full = ground.t - swirl.STILL_T
    ground.advance(0.1, True, 0.2)
    assert ground.t - swirl.STILL_T == pytest.approx(1.2 * full)


def test_a_cheap_raster_ground_moves_at_the_base_rate(monkeypatch):
    ground = bare_ground(monkeypatch, gl=False)
    for _ in range(10):
        ground.advance(0.016, True)
        ground._measure = True
        ground.painted(3.0)
    assert ground.t > swirl.STILL_T
    assert len(ground.renders) == 5


def test_a_costly_raster_ground_holds_still_and_probes(monkeypatch):
    ground = bare_ground(monkeypatch, gl=False)
    ground._measure = True
    ground.painted(40.0)
    t = ground.t
    for _ in range(int(swirl.PROBE_S / 0.016) + 1):
        ground.advance(0.016, True)
    assert ground.t == t
    assert ground.renders == []
    assert len(ground.requests) == 1


def test_a_gl_ground_ignores_paint_cost(monkeypatch):
    ground = bare_ground(monkeypatch, gl=True)
    ground._measure = True
    ground.painted(40.0)
    for _ in range(4):
        ground.advance(0.016, True)
    assert len(ground.renders) == 2


def test_with_hardware_acceleration_off_the_ground_is_still(monkeypatch):
    ground = bare_ground(monkeypatch, gl=False)
    ground.still = True
    for _ in range(10):
        ground.advance(0.016, True)
    assert ground.t == swirl.STILL_T


def test_after_a_gl_crash_there_is_no_field(monkeypatch):
    monkeypatch.setattr(swirl, "_field", None)
    monkeypatch.setattr(swirl, "_field_failed", False)
    monkeypatch.setattr(swirl, "canvas_renderer_rule", lambda: "failed before")
    assert swirl.field() is None


def test_the_stride_grows_with_the_repaint_and_stops_at_a_frame():
    assert swirl.stride_for(3.0, 2) == 2
    assert swirl.stride_for(10.0, 2) == 3
    assert swirl.stride_for(15.0, 2) == 4
    assert swirl.stride_for(16.7, 2) is None


def test_the_governor_slows_at_once_and_speeds_up_after_a_while():
    governor = swirl.Governor(2)
    governor.measured(15.0)
    assert governor.stride == 4
    for _ in range(40):
        governor.measured(3.0)
    assert governor.stride == 4
    for _ in range(int(swirl.RECOVER_S / 0.016) + 1):
        governor.tick(0.016)
    assert governor.stride == 2


def test_a_camera_move_while_animating_waits_for_the_tick(monkeypatch):
    ground = bare_ground(monkeypatch)
    ground.advance(0.016, True)
    ground.image = object()
    ground._on_camera_moved()
    assert ground.requests == []
    assert ground.dirty


def test_a_camera_move_on_a_still_ground_renders_once_the_clock_stops(monkeypatch):
    ground = bare_ground(monkeypatch)
    ground.advance(0.016, True)
    ground.image = object()
    ground._on_camera_moved()
    ground.stop()
    assert len(ground.requests) == 1
    ground._on_camera_moved()
    assert len(ground.requests) == 2


def test_the_shader_sources_ship_without_a_version_line():
    for name in ("swirl.vert", "swirl.frag"):
        source = swirl.SHADERS.joinpath(name).read_text(encoding="utf-8")
        assert "void main()" in source
        assert "#version" not in source
