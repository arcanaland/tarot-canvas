"""What the app's own TOML stores share: timestamped folders, bounded reads and atomic writes"""

import os
import tempfile
import time
import tomllib
from pathlib import Path

# Far past any layout, and well inside what the canvas and z's arithmetic can hold
MAX_NUMBER = 1e9
# Far past any file the app writes, and shallow enough that a file that loads can be saved again
MAX_NESTING = 32


def new_timestamped_dir(base):
    """A new folder in base named by the current time, stepping past a taken name"""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    while True:
        path = base / str(stamp)
        try:
            path.mkdir()
        except FileExistsError:
            stamp += 1
        else:
            return path


def _nesting(value):
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return 0
    return 1 + max(map(_nesting, children), default=0)


def load_table(file):
    """The TOML file as a dict; raises OSError, or ValueError when it is malformed or nested too deeply"""
    with open(file, "rb") as handle:
        try:
            table = tomllib.load(handle)
            too_deep = _nesting(table) > MAX_NESTING
        except RecursionError:
            too_deep = True
    if too_deep:
        raise ValueError("nested too deeply")
    return table


def number(table, key, default=0.0):
    """table[key] as a float in range, else ValueError"""
    value = float(table.get(key, default))
    if not abs(value) <= MAX_NUMBER:  # nan compares false
        raise ValueError(f"{key} is out of range: {value}")
    return value


def write_atomically(file, text):
    """Replace file with text, so a reader sees the old file or the new one and never half of one"""
    file = Path(file)
    descriptor, temporary = tempfile.mkstemp(dir=file.parent, prefix=f".{file.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, file)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
