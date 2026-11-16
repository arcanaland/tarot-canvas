import datetime
import logging
import os
import subprocess
import sys

import pytest

from tarot_canvas.utils import logger as logger_module
from tarot_canvas.utils.logger import configure_logging, prune_logs

NOW = datetime.datetime(2026, 11, 13, 12, 0)


def old_log(log_dir, name, days):
    path = log_dir / f"tarot_canvas_{name}.log"
    path.write_text("")
    mtime = (NOW - datetime.timedelta(days=days)).timestamp()
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def configured(monkeypatch):
    """configure_logging's handlers, removed again after the test"""
    root = logging.getLogger(logger_module.LOGGER_NAME)
    handlers, level = list(root.handlers), root.level
    monkeypatch.setattr(logger_module, "_log_file", None)
    yield
    for handler in root.handlers:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


def test_yesterdays_crash_log_survives_the_next_launch(tmp_path, configured):
    crash = old_log(tmp_path, "20261110_104413", days=3)

    log_file = configure_logging(tmp_path)

    assert crash.exists()
    assert log_file.exists()


def test_the_newest_are_kept_however_old(tmp_path):
    logs = [old_log(tmp_path, f"{day:02}", days=30 + day) for day in range(25)]

    prune_logs(tmp_path, keep_newest=20, keep_days=7, now=NOW)

    assert [path.exists() for path in logs] == [True] * 20 + [False] * 5


def test_a_recent_log_is_kept_however_many_are_newer(tmp_path):
    newer = [old_log(tmp_path, f"new{i:02}", days=0) for i in range(20)]
    recent = old_log(tmp_path, "recent", days=6)
    stale = old_log(tmp_path, "stale", days=8)

    prune_logs(tmp_path, keep_newest=20, keep_days=7, now=NOW)

    assert all(path.exists() for path in newer)
    assert recent.exists()
    assert not stale.exists()


def test_importing_the_app_writes_and_deletes_no_log(tmp_path):
    logs = tmp_path / "data" / "tarot-canvas" / "logs"
    logs.mkdir(parents=True)
    ancient = logs / "tarot_canvas_20200101_000000.log"
    ancient.write_text("")
    os.utime(ancient, (0, 0))
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "QT_QPA_PLATFORM": "offscreen",
    }

    subprocess.run([sys.executable, "-c", "import tarot_canvas.main"], env=env, check=True)

    assert list(logs.iterdir()) == [ancient]
