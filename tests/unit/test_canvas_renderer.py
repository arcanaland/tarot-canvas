import pytest

from tarot_canvas.ui.canvas.renderer import choose

HARDWARE = "AMD Radeon 780M Graphics (radeonsi, gfx1103_r1, LLVM 22.1.8, DRM 3.64)"


def unreachable():
    raise AssertionError("probed")


@pytest.mark.parametrize("platform", ["offscreen", "minimal"])
def test_headless_platforms_paint_raster_without_probing(platform):
    assert not choose(platform, "linux", None, unreachable)
    assert not choose(platform, "linux", "gl", unreachable)


def test_a_forced_renderer_skips_the_probe():
    assert not choose("wayland", "linux", "raster", unreachable)
    assert choose("wayland", "linux", "gl", unreachable)
    assert choose("cocoa", "darwin", "gl", unreachable)


def test_only_linux_probes():
    assert not choose("cocoa", "darwin", None, unreachable)
    assert not choose("windows", "win32", None, unreachable)


@pytest.mark.parametrize(
    "renderer",
    [
        "llvmpipe (LLVM 22.1.8, 256 bits)",
        "softpipe",
        "Mesa X11 swrast",
        "Software Rasterizer",
    ],
)
def test_software_gl_paints_raster(renderer):
    assert not choose("wayland", "linux", None, lambda: renderer)


def test_no_gl_context_paints_raster():
    assert not choose("xcb", "linux", None, lambda: None)


def test_a_hardware_renderer_paints_gl():
    assert choose("wayland", "linux", None, lambda: HARDWARE)
    assert choose("xcb", "linux", None, lambda: HARDWARE)
