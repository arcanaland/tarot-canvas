"""Our app's stored TOML files in ~/.local/share/tarot-canvas"""

import os
import tempfile
import time
import tomllib
from pathlib import Path

import tomli_w

APP_TABLE = "land.arcana.tarotcanvas"
MAX_NUMBER = 1e9
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
    """The TOML file as a dict"""
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
    """Replace file with text"""
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


def write_toml(file, table):
    """Replace file with table as TOML, atomically"""
    write_atomically(file, tomli_w.dumps(table, multiline_strings=True))


# -- the app's own table: [app."land.arcana.tarotcanvas"] ---------------------------------


def app_table(table):
    """The app's own table in the TOML file"""
    apps = table.get("app")
    if apps is None:
        return {}
    if not isinstance(apps, dict):
        raise ValueError("app is not a table")
    ours = apps.get(APP_TABLE)
    if ours is None:
        return {}
    if not isinstance(ours, dict):
        raise ValueError(f"app.{APP_TABLE} is not a table")
    return ours


def version_of(ours):
    """The version in the app's own table (absent is 1), else ValueError"""
    version = ours.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError(f"bad version: {version!r}")
    return version


def with_app_table(table, fields):
    """A copy of table whose app table holds fields, over what it held; other apps' tables are kept"""
    apps = dict(table.get("app", {}))
    ours = apps.get(APP_TABLE)
    apps[APP_TABLE] = {**(ours if isinstance(ours, dict) else {}), **fields}
    return {**table, "app": apps}
