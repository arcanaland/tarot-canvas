import pytest

from tarot_canvas.ui.canvas.renderer import choose

HARDWARE = "AMD Radeon 780M Graphics (radeonsi, gfx1103_r1, LLVM 22.1.8, DRM 3.64)"


def unreachable():
    raise AssertionError("reached")


def uses_gl(platform, system, forced, probe, enabled=True, failed=lambda: False):
    return choose(platform, system, forced, enabled, failed, probe)[0]


@pytest.mark.parametrize("platform", ["offscreen", "minimal"])
def test_headless_platforms_paint_raster_without_probing(platform):
    assert not uses_gl(platform, "linux", None, unreachable, failed=unreachable)
    assert not uses_gl(platform, "linux", "gl", unreachable, failed=unreachable)


def test_a_forced_renderer_skips_the_probe_and_the_marker():
    assert not uses_gl("wayland", "linux", "raster", unreachable, failed=unreachable)
    assert uses_gl("wayland", "linux", "gl", unreachable, failed=unreachable)
    assert uses_gl("wayland", "linux", "gl", unreachable, enabled=False, failed=unreachable)
    assert uses_gl("cocoa", "darwin", "gl", unreachable, failed=unreachable)


def test_only_linux_probes():
    assert not uses_gl("cocoa", "darwin", None, unreachable, failed=unreachable)
    assert not uses_gl("windows", "win32", None, unreachable, failed=unreachable)


def test_the_preference_off_skips_the_marker_and_the_probe():
    assert choose("wayland", "linux", None, False, unreachable, unreachable) == (
        False,
        "preference off",
    )


def test_an_earlier_failure_skips_the_probe():
    assert choose("wayland", "linux", None, True, lambda: True, unreachable) == (
        False,
        "failed before",
    )


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
    assert not uses_gl("wayland", "linux", None, lambda: renderer)


def test_no_gl_context_paints_raster():
    assert not uses_gl("xcb", "linux", None, lambda: None)


def test_a_hardware_renderer_paints_gl():
    assert uses_gl("wayland", "linux", None, lambda: HARDWARE)
    assert uses_gl("xcb", "linux", None, lambda: HARDWARE)
