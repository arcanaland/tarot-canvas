import contextlib
import os
import tempfile
from pathlib import Path


@contextlib.contextmanager
def atomic_path(path):
    """A temporary path beside path, renamed over it once written"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        yield temporary
        with open(temporary, "rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_atomic(path, data):
    """Replace path with data, str as UTF-8"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    with atomic_path(path) as temporary:
        temporary.write_bytes(data)
