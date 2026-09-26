"""The frame loop and what is reported about it."""

import statistics
import time
from dataclasses import dataclass

from PyQt6.QtWidgets import QApplication

from bench.env import BenchError

# The simulated time between frames: the canvas's own tick
DT = 1 / 60
# Frame budgets at 60 and 120 Hz
BUDGETS_MS = (1000 / 60, 1000 / 120)


@dataclass
class Run:
    # Per measured frame: the Python motion step, then Qt's paint of what it dirtied
    motion_ms: list
    paint_ms: list
    # Frames in which the viewport was painted at all
    painted: int

    @property
    def frame_ms(self):
        return [m + p for m, p in zip(self.motion_ms, self.paint_ms, strict=True)]


def run(canvas, workload, cards, frames, warmup):
    """Lay out cards, then time frames frames of workload after warmup untimed ones."""
    canvas.populate(cards)
    canvas.ambient = workload.ambient
    tab = canvas.tab
    tab.ambient_gain = 1.0 if workload.ambient else 0.0
    state = workload.start(canvas)
    app = QApplication.instance()

    motion_ms = []
    paint_ms = []
    painted = 0
    for i in range(warmup + frames):
        t = (i + 1) * DT
        before = canvas.paints.count

        start = time.perf_counter_ns()
        workload.step(canvas, state, t)
        tab._advance_motion(t, DT)
        if workload.repaint:
            canvas.repaint_all()
        stepped = time.perf_counter_ns()
        app.processEvents()
        canvas.fence()
        done = time.perf_counter_ns()

        if i >= warmup:
            motion_ms.append((stepped - start) / 1e6)
            paint_ms.append((done - stepped) / 1e6)
            painted += canvas.paints.count > before

    if painted == 0:
        raise BenchError(f"'{workload.name}' never painted; the frame loop measured nothing")
    return Run(motion_ms, paint_ms, painted)


def percentile(values, p):
    """The p-th percentile of values, interpolated."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p / 100
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def spread(values):
    """What matters about a run of frame times: the typical frame and the bad ones."""
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def over_budget(values, budget_ms):
    """The fraction of frames that would miss a vsync at budget_ms."""
    return sum(v > budget_ms for v in values) / len(values)


def summarize(runs):
    """Each statistic as the median over runs, with how much the runs disagreed."""
    per_run = [
        {
            "frame": spread(r.frame_ms),
            "motion": spread(r.motion_ms),
            "paint": spread(r.paint_ms),
            "over": [over_budget(r.frame_ms, b) for b in BUDGETS_MS],
            "painted": r.painted / len(r.frame_ms),
        }
        for r in runs
    ]

    def median_of(part):
        return {
            key: statistics.median(run[part][key] for run in per_run) for key in per_run[0][part]
        }

    means = [run["frame"]["mean"] for run in per_run]
    return {
        "frame": median_of("frame"),
        "motion": median_of("motion"),
        "paint": median_of("paint"),
        "over": [
            statistics.median(run["over"][i] for run in per_run) for i in range(len(BUDGETS_MS))
        ],
        "painted": statistics.median(run["painted"] for run in per_run),
        # Coefficient of variation of the run means; above ~5% the number is noise
        "cov": statistics.pstdev(means) / statistics.fmean(means) if len(means) > 1 else 0.0,
    }
