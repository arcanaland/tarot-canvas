"""The benchmark harness still drives the canvas it measures."""

import pytest
from PyQt6.QtCore import QSize

from bench.canvas import BenchCanvas, synthetic_art
from bench.env import BenchError
from bench.frames import run
from bench.workloads import WORKLOADS


def test_every_workload_paints_frames(qapp, tmp_path):
    canvas = BenchCanvas("raster", QSize(800, 600), synthetic_art(tmp_path))
    try:
        for workload in WORKLOADS:
            result = run(canvas, workload, cards=3, frames=4, warmup=2)

            assert len(result.frame_ms) == 4, workload.name
            assert result.painted > 0, workload.name
    finally:
        canvas.close()


def test_every_run_starts_from_the_same_layout(qapp, tmp_path):
    canvas = BenchCanvas("raster", QSize(800, 600), synthetic_art(tmp_path))
    try:
        canvas.populate(3)
        laid_out = [card.pos() for card in canvas.cards()]
        drag = next(w for w in WORKLOADS if w.name == "drag")
        run(canvas, drag, cards=3, frames=4, warmup=0)
        dragged = [card.pos() for card in canvas.cards()]

        canvas.populate(3)

        assert dragged != laid_out
        assert [card.pos() for card in canvas.cards()] == laid_out
    finally:
        canvas.close()


def test_gl_refuses_the_offscreen_platform(qapp, tmp_path):
    with pytest.raises(BenchError, match="offscreen"):
        BenchCanvas("gl", QSize(800, 600), synthetic_art(tmp_path))
