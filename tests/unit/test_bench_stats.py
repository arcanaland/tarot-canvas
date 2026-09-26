import pytest

from bench.frames import Run, over_budget, percentile, summarize
from bench.report import compare, save


def test_percentile_interpolates_between_ranks():
    values = [4.0, 1.0, 3.0, 2.0]

    assert percentile(values, 0) == 1.0
    assert percentile(values, 50) == 2.5
    assert percentile(values, 100) == 4.0


def test_over_budget_counts_only_frames_that_miss_it():
    assert over_budget([10.0, 16.0, 17.0, 40.0], 1000 / 60) == 0.5


def test_summary_takes_the_median_run_and_reports_their_spread():
    steady = Run(motion_ms=[1.0] * 10, paint_ms=[1.0] * 10, painted=10)
    slow = Run(motion_ms=[1.0] * 10, paint_ms=[3.0] * 10, painted=10)

    summary = summarize([steady, steady, slow])

    assert summary["frame"]["p50"] == 2.0
    assert summary["cov"] == pytest.approx(0.3536, abs=1e-4)


def _results(path, p50, cov):
    frame = {"p50": p50, "p95": p50, "p99": p50, "max": p50, "mean": p50}
    summary = {"frame": frame, "cov": cov}
    save(
        path,
        {"machine": {"commit": "abc"}},
        [{"workload": "ambient", "viewport": "raster", "cards": 16, "summary": summary}],
    )


def test_compare_marks_changes_within_noise(tmp_path):
    _results(tmp_path / "base.json", 10.0, 0.02)
    _results(tmp_path / "small.json", 10.3, 0.02)
    _results(tmp_path / "big.json", 5.0, 0.02)

    small = compare(tmp_path / "base.json", tmp_path / "small.json").splitlines()[2]
    big = compare(tmp_path / "base.json", tmp_path / "big.json").splitlines()[2]

    assert "+3.0%~" in small
    assert "-50.0%" in big
    assert "-50.0%~" not in big
