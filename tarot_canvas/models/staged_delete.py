"""A delete that can still be undone: the path is renamed aside until it's committed."""

import os
import shutil
from pathlib import Path

SUFFIX = ".deleted"


def is_staged(path):
    return Path(path).name.endswith(SUFFIX)


def stage(path):
    """Rename the file or folder at path aside, and return where it went"""
    staged = f"{path}{SUFFIX}"
    os.rename(path, staged)
    return staged


def restore(staged, path):
    os.rename(staged, path)


def commit(staged):
    if Path(staged).is_dir():
        shutil.rmtree(staged)
    else:
        os.remove(staged)
